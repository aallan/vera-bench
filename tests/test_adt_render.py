"""The per-language ADT renderer: construction, inference, and refusal.

Twelve problems ask the model to define the data type, so the harness has
to build test-case values with whatever the solution declared. These tests
pin the two properties that make that grading fair: a solution using its
own names or field labels is graded, and anything the renderer cannot map
with confidence declines — ungraded, never scored wrong on a call we were
not sure of.
"""

from __future__ import annotations

import pytest

from vera_bench.adt_render import (
    grades_on_stdout,
    infer_ts_fields,
    render,
    render_args,
    resolve_names,
    return_spec,
    uses_native_collection,
)
from vera_bench.vera_wrapper import Unsupported

LIST = {
    "type": "List",
    "form": "list",
    "empty": "Nil",
    "cons": "Cons",
    "constructors": [
        {"name": "Nil", "args": [], "fields": []},
        {"name": "Cons", "args": ["Int", "List"], "fields": ["head", "tail"]},
    ],
}
OPTION = {
    "type": "Option",
    "form": "tagged",
    "constructors": [
        {"name": "None", "args": [], "fields": []},
        {"name": "Some", "args": ["Int"], "fields": ["value"]},
    ],
}


class TestRender:
    def test_each_language_gets_its_own_idiom(self):
        # Python instantiates nullary constructors; the others name them.
        assert render([1], LIST, "python") == "Cons(1, Nil())"
        assert render([1], LIST, "ailang") == "Cons(1, Nil)"
        assert render([1], LIST, "aver", qualifier="MyList") == (
            "MyList.Cons(1, MyList.Nil)"
        )

    def test_names_map_onto_the_solutions_own(self):
        out = render([7], LIST, "ailang", names={"Nil": "MyNil", "Cons": "MyCons"})
        assert out == "MyCons(7, MyNil)"

    def test_native_renders_the_builtin_literal(self):
        assert render([1, 2], LIST, "aver", native=True) == "[1, 2]"

    def test_tagged_constructor(self):
        assert render({"Some": [5]}, OPTION, "python") == "Some(5)"
        assert render({"None": []}, OPTION, "aver", qualifier="Option") == (
            "Option.None"
        )

    def test_unknown_constructor_declines(self):
        with pytest.raises(Unsupported):
            render({"Whatever": [1]}, OPTION, "python")

    def test_element_type_follows_the_cons_declaration(self):
        strings = {
            **LIST,
            "constructors": [
                {"name": "Nil", "args": [], "fields": []},
                {
                    "name": "Cons",
                    "args": ["String", "List"],
                    "fields": ["head", "tail"],
                },
            ],
        }
        assert render(["a"], strings, "python") == 'Cons("a", Nil())'


class TestTypeScriptFields:
    def test_inferred_from_a_type_alias(self):
        src = 'type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };'
        assert infer_ts_fields(src) == {"Nil": [], "Cons": ["head", "tail"]}

    def test_solutions_own_field_names_are_used(self):
        # The canonical fields are head/tail; this solution chose its own.
        # Constructing with the canonical names would hand its correct
        # code objects whose fields read as undefined.
        src = 'type List = { tag: "Nil" } | { tag: "Cons"; value: number; rest: List };'
        out = render([1], LIST, "typescript", ts_fields=infer_ts_fields(src))
        assert out == '{ tag: "Cons", value: 1, rest: { tag: "Nil" } }'

    def test_a_nullary_value_literal_never_shadows_the_declaration(self):
        src = (
            'const empty = { tag: "Cons" };\n'
            'type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };'
        )
        assert infer_ts_fields(src)["Cons"] == ["head", "tail"]

    def test_uninferable_fields_decline_rather_than_guess(self):
        with pytest.raises(Unsupported):
            render([1], LIST, "typescript", ts_fields={})


class TestRenderArgs:
    def test_arity_mismatch_declines_instead_of_truncating(self):
        # zip would silently drop the extras and the wrapper would call
        # the entry point with the wrong arity.
        with pytest.raises(Unsupported):
            render_args([[1], 2, 3], ["List", "Int"], LIST, "python")

    def test_mixed_adt_and_scalar(self):
        out = render_args([[1], 5], ["List", "Int"], LIST, "python")
        assert out == ["Cons(1, Nil())", "5"]


class TestResolveNames:
    def test_near_name_variants_resolve(self):
        # AILANG's MyNil / Python's NoneOpt style.
        src = "type MyList = MyNil | MyCons(int, MyList)"
        assert resolve_names(src, LIST, "ailang") == {
            "Nil": "MyNil",
            "Cons": "MyCons",
        }

    def test_unrelated_names_decline(self):
        with pytest.raises(Unsupported):
            resolve_names("type L = Empty | Node(int, L)", LIST, "ailang")

    def test_builtin_needs_no_declaration(self):
        src = "fn f(o: Option<Int>) -> Int"
        assert resolve_names(src, OPTION, "aver") == {}
        assert uses_native_collection("fn f(xs: List<Int>) -> Int", LIST)


class TestSpecQueries:
    def test_grades_on_stdout_is_the_unit_return(self):
        assert grades_on_stdout({"signature": "fn f(@Nat -> @Unit)"})
        assert not grades_on_stdout({"signature": "fn f(@Nat -> @Int)"})

    def test_return_spec_prefers_the_dedicated_block(self):
        problem = {
            "signature": "fn f(@List -> @Option)",
            "adt": LIST,
            "return_adt": OPTION,
        }
        assert return_spec(problem) is problem["return_adt"]
        # And the arguments' spec does not masquerade as the return's.
        assert return_spec({"signature": "fn f(@List -> @Int)", "adt": LIST}) is None


class TestSharedTsWrapper:
    """One builder, two callers — the property that ends the double-patch."""

    PROBLEM = {
        "id": "VB-TEST-TS",
        "entry_point": "absolute_value",
        "signature": "public fn absolute_value(@Int -> @Int)",
        "test_cases": [{"args": [-5], "expected": 5}],
    }

    def test_wrapper_restores_console_in_a_finally(self):
        from vera_bench.ts_wrapper import build_ts_wrapper

        text = build_ts_wrapper(self.PROBLEM, "", "./sol.ts")
        assert "} finally {" in text
        assert "console.log = _log" in text
        assert text.count("console.log(JSON.stringify(results));") == 1

    def test_both_callers_emit_identical_wrappers(self):
        # Import path is the only legitimate difference between the LLM
        # evaluator's wrapper and the baseline runner's.
        from vera_bench.ts_wrapper import build_ts_wrapper

        a = build_ts_wrapper(self.PROBLEM, "", "./a.ts")
        b = build_ts_wrapper(self.PROBLEM, "", "./b.ts")

        def strip(text: str) -> list[str]:
            return [ln for ln in text.splitlines() if "import" not in ln]

        assert strip(a) == strip(b)

    def test_snake_to_camel(self):
        from vera_bench.ts_wrapper import snake_to_camel

        assert snake_to_camel("list_length") == "listLength"
        assert snake_to_camel("greet") == "greet"
