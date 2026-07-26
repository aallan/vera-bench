"""The generated Vera caller: literal rendering, comparison, refusal to guess.

Hermetic — these test what the generator EMITS, not what the compiler does
with it. The end-to-end behaviour (wrapper compiles, runs, discriminates)
is exercised by `vera-bench validate` over the canonical solutions, which
CI runs with a real `vera`. What must be pinned here is the reasoning the
validator cannot see: that unsupported shapes decline rather than guess,
because a guessed wrapper that fails to compile is recorded as the model
writing a wrong program — worse than the ungraded status quo.
"""

from __future__ import annotations

import pytest

from vera_bench.vera_wrapper import (
    PROBE_FN,
    Unsupported,
    build_wrapper,
    can_wrap,
    entry_effects,
    parse_signature,
    render_value,
)


class TestParseSignature:
    def test_single_param(self):
        assert parse_signature("public fn f(@Int -> @Int)") == (["@Int"], "@Int")

    def test_multi_param_keeps_order(self):
        params, ret = parse_signature("public fn f(@Array<Int>, @Nat -> @Int)")
        assert params == ["@Array<Int>", "@Nat"]
        assert ret == "@Int"

    def test_generic_commas_do_not_split(self):
        # A future @Map<Int, Int> must stay one parameter, not two.
        params, _ = parse_signature("fn f(@Map<Int, Int>, @Int -> @Int)")
        assert params == ["@Map<Int, Int>", "@Int"]

    def test_unit_param_drops_out(self):
        assert parse_signature("public fn f(@Unit -> @Nat)") == ([], "@Nat")

    def test_garbage_declines(self):
        with pytest.raises(Unsupported):
            parse_signature("not a signature at all")


class TestRenderValue:
    def test_ints_and_negatives(self):
        assert render_value(7, "@Int") == "7"
        assert render_value(-7, "@Int") == "-7"

    def test_bools_including_json_int_form(self):
        assert render_value(True, "@Bool") == "true"
        assert render_value(0, "@Bool") == "false"

    def test_string_escaping_via_json(self):
        assert render_value('say "hi"\n', "@String") == '"say \\"hi\\"\\n"'

    def test_array_of_ints(self):
        assert render_value([1, -2, 3], "@Array<Int>") == "[1, -2, 3]"

    def test_empty_array(self):
        assert render_value([], "@Array<Int>") == "[]"

    def test_type_mismatch_declines(self):
        with pytest.raises(Unsupported):
            render_value("nope", "@Int")
        with pytest.raises(Unsupported):
            render_value(3, "@Array<Int>")

    def test_bool_is_not_an_int(self):
        # bool is an int subclass in Python; a True smuggled into @Int
        # would render as "True" and fail to compile.
        with pytest.raises(Unsupported):
            render_value(True, "@Int")

    def test_unknown_type_declines(self):
        with pytest.raises(Unsupported):
            render_value({"x": 1}, "@Tree")


class TestEntryEffects:
    SRC = """
private fn helper(@Int -> @Int)
  requires(true) ensures(true) effects(pure)
{ @Int.0 }

public fn target(@Array<Int> -> @Int)
  requires(true)
  ensures(true)
  effects(<IO>)
{ 0 }
"""

    def test_mirrors_the_entry_points_own_clause(self):
        assert entry_effects(self.SRC, "target") == "effects(<IO>)"

    def test_does_not_borrow_another_functions_clause(self):
        assert entry_effects(self.SRC, "helper") == "effects(pure)"

    def test_defaults_to_pure_when_absent(self):
        assert entry_effects("nothing here", "target") == "effects(pure)"


class TestBuildWrapper:
    SIG_SCALAR = "public fn sum_array(@Array<Int> -> @Int)"
    SIG_ARRAY = "public fn doubles(@Array<Int> -> @Array<Int>)"

    def test_scalar_return_passes_expected_through(self):
        wrapper, expected = build_wrapper("", "sum_array", self.SIG_SCALAR, [[1, 2]], 3)
        assert expected == 3
        assert f"fn {PROBE_FN}(@Unit -> @Int)" in wrapper
        assert "sum_array([1, 2])" in wrapper

    def test_array_return_compares_in_vera_and_expects_bool(self):
        wrapper, expected = build_wrapper(
            "", "doubles", self.SIG_ARRAY, [[1, 2]], [2, 4]
        )
        # vera run prints a Bool as 1/0, so the caller compares against 1.
        assert expected == 1
        assert "array_length(@Array<Int>.0) == 2" in wrapper
        assert "@Array<Int>.0[0] == 2" in wrapper
        assert "@Array<Int>.0[1] == 4" in wrapper

    def test_empty_expected_array_is_a_length_check_alone(self):
        wrapper, expected = build_wrapper("", "doubles", self.SIG_ARRAY, [[]], [])
        assert expected == 1
        assert "array_length(@Array<Int>.0) == 0" in wrapper

    def test_arg_count_mismatch_declines(self):
        with pytest.raises(Unsupported):
            build_wrapper("", "sum_array", self.SIG_SCALAR, [[1], 2], 3)

    def test_adt_return_declines(self):
        with pytest.raises(Unsupported):
            build_wrapper("", "f", "public fn f(@List -> @Option)", [[1]], None)

    def test_array_return_with_non_list_expected_declines(self):
        with pytest.raises(Unsupported):
            build_wrapper("", "doubles", self.SIG_ARRAY, [[1]], 7)


class TestCanWrap:
    def test_scalar_only_signatures_stay_on_the_cli(self):
        assert can_wrap("public fn abs(@Int -> @Int)") is False
        assert can_wrap("public fn greet(@String -> @String)") is False

    def test_array_params_wrap(self):
        assert can_wrap("public fn f(@Array<Int> -> @Int)") is True
        assert can_wrap("public fn f(@Array<String>, @String -> @String)") is True

    def test_adt_params_decline_for_now(self):
        # Step 2 of #107: these need the model's own declaration parsed.
        assert can_wrap("public fn f(@List -> @Nat)") is False
        assert can_wrap("public fn f(@Tree -> @Int)") is False

    def test_unparseable_declines(self):
        assert can_wrap("") is False
