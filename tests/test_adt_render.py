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
    infer_ts_discriminant,
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
        assert infer_ts_fields(src) == {
            "Nil": [],
            "Cons": [("head", "number"), ("tail", "List")],
        }

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
        assert [n for n, _ in infer_ts_fields(src)["Cons"]] == ["head", "tail"]

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


class TestTsFieldAlignment:
    """Inferred fields align to canonical argument order by TYPE.

    A declaration listing `tail` before `head` is legal; positional
    zipping scrambled the constructed value and failed a correct
    solution at runtime (multi-agent review of #112, verified with real
    tsx). Same-type fields keep declared order — the only reading the
    solution's own author could have meant.
    """

    def test_swapped_declaration_order_still_constructs_correctly(self):
        src = 'type List = { tag: "Nil" } | { tag: "Cons"; tail: List; head: number };'
        out = render([1], LIST, "typescript", ts_fields=infer_ts_fields(src))
        assert out == '{ tag: "Cons", head: 1, tail: { tag: "Nil" } }'

    def test_kind_discriminated_union_uses_kind(self):
        src = (
            "type List = { kind: 'Nil' } | { kind: 'Cons'; head: number; tail: List };"
        )
        out = render(
            [1],
            LIST,
            "typescript",
            ts_fields=infer_ts_fields(src),
            ts_disc=infer_ts_discriminant(src),
        )
        assert out == '{ kind: "Cons", head: 1, tail: { kind: "Nil" } }'

    def test_a_value_literal_in_a_comment_does_not_poison_inference(self):
        src = (
            '// e.g. { tag: "Cons", head: 1, tail: { tag: "Nil" } }\n'
            'type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };'
        )
        out = render([1], LIST, "typescript", ts_fields=infer_ts_fields(src))
        assert out == '{ tag: "Cons", head: 1, tail: { tag: "Nil" } }'


class TestResolveNamesWidening:
    """The declaration forms the first regexes missed (review of #112)."""

    def test_bare_and_dataclass_python_classes_resolve(self):
        src = "class Nil:\n    pass\n\n@dataclass\nclass Cons:\n    head: int\n"
        assert resolve_names(src, LIST, "python") == {"Nil": "Nil", "Cons": "Cons"}

    def test_multiline_ailang_type_resolves(self):
        src = "type MyList =\n  | MyNil\n  | MyCons(int, MyList)"
        assert resolve_names(src, LIST, "ailang") == {
            "Nil": "MyNil",
            "Cons": "MyCons",
        }

    def test_mapping_must_be_one_to_one(self):
        # Both canonical names near-match the single declared name; a
        # confident wrong mapping is the one output this must not have.
        spec = {
            "type": "T",
            "form": "tagged",
            "constructors": [
                {"name": "Value", "args": ["Int"], "fields": ["value"]},
                {"name": "Val", "args": [], "fields": []},
            ],
        }
        with pytest.raises(Unsupported):
            resolve_names("type T = MyValue(int)", spec, "ailang")


class TestAdtPrintedQualifier:
    """Aver prints built-ins qualified and declared types bare."""

    def test_builtin_prints_qualified(self):
        from vera_bench.adt_render import adt_printed

        problem = {
            "signature": "public fn f(@List -> @Option)",
            "entry_point": "f",
            "adt": LIST,
            "return_adt": OPTION,
        }
        src = "fn f(xs: List<Int>) -> Option<Int>"
        assert adt_printed(problem, src, "aver", {"Some": [3]}) == "Option.Some(3)"

    def test_declared_type_prints_bare(self):
        from vera_bench.adt_render import adt_printed

        problem = {
            "signature": "public fn f(@List -> @Option)",
            "entry_point": "f",
            "adt": LIST,
            "return_adt": OPTION,
        }
        src = "type MyOption\n    MyNone\n    MySome(Int)\n"
        assert adt_printed(problem, src, "aver", {"Some": [3]}) == "MySome(3)"


class TestCommentBlindness:
    """Comments must never reach a declaration scanner.

    Adversarial review of #112 found every scanner regex-matching raw
    source: a comment inside a Vera data block dropped a constructor, an
    echoed canonical declaration in a comment shadowed the model's real
    one, an Aver doc comment mentioning List<Int> flipped a declared-type
    solution onto nonexistent builtin members, and a TypeScript JSDoc
    example overrode the real field names. Each mis-graded a correct
    solution. All five reproductions are pinned here.
    """

    def test_vera_comment_inside_a_data_block_keeps_constructors(self):
        from vera_bench.vera_wrapper import parse_data_decls

        src = "private data List {\n  Nil,   -- head and tail\n  Cons(Int, List)\n}\n"
        assert parse_data_decls(src) == {
            "List": [("Nil", ()), ("Cons", ("Int", "SELF"))]
        }

    def test_a_commented_out_declaration_does_not_shadow_the_real_one(self):
        from vera_bench.vera_wrapper import parse_data_decls

        src = (
            "-- Canonical: data List { Nil, Cons(Int, List) }\n"
            "private data L2 {\n  Empty,\n  Node(Int, L2)\n}\n"
        )
        assert list(parse_data_decls(src)) == ["L2"]

    def test_effects_quoted_in_a_comment_is_not_mirrored(self):
        from vera_bench.vera_wrapper import entry_effects

        src = (
            "public fn f(@Int -> @Int)\n"
            "  -- every function needs requires(), ensures(), effects()\n"
            "  requires(true)\n  ensures(true)\n  effects(pure)\n{\n  @Int.0\n}\n"
        )
        assert entry_effects(src, "f") == "effects(pure)"

    def test_aver_builtin_mentioned_in_a_comment_is_not_a_builtin(self):
        src = (
            "-- uses its own type rather than the builtin List<Int>.\n"
            "type MyList\n    Nil\n    Cons(Int, MyList)\n"
        )
        assert uses_native_collection(src, LIST) is False

    def test_typescript_jsdoc_example_does_not_override_the_declaration(self):
        src = (
            '/** @example listLength({ tag: "Cons", head: 1, tail: { tag: "Nil" } }) */\n'
            'type List = { kind: "Nil" } | { kind: "Cons"; head: number; tail: List };'
        )
        assert infer_ts_discriminant(src) == "kind"
        assert [n for n, _ in infer_ts_fields(src)["Cons"]] == ["head", "tail"]

    def test_a_marker_inside_a_string_literal_is_code_not_a_comment(self):
        from vera_bench.adt_render import strip_comments

        assert '"a -- b"' in strip_comments('let x = "a -- b"  -- gone', "vera")
