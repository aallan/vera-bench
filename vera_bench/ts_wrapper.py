"""The generated TypeScript test wrapper, built once for both callers.

The LLM evaluator (`runner.py`) and the baseline runner
(`baseline_runner.py`) grade TypeScript through the same generated
wrapper, and until this module they each built their own copy of it.
The copies were verified byte-identical apart from the import line —
and keeping them that way cost five double-patches in one review cycle
(the array comparison, the stdout capture, the `stdout.write` capture,
the newline preservation, the try/finally restore). One implementation,
parameterised by the import path, ends that.

What the wrapper does, per test case: capture `console.log` and
`process.stdout.write` around the invocation (restored in a `finally`,
so a throwing case cannot swallow later cases or the final JSON line),
then grade by whichever comparison the problem calls for — captured
stdout for `@Unit` problems, structural key-sorted JSON for ADT
returns, JSON equality for arrays, loose `==` for scalars so a
Vera-style 1/0 matches a native boolean.

`Unsupported` propagates to the caller, which records the problem
ungraded — the same decline contract as every other generated caller.
"""

from __future__ import annotations

import json

from vera_bench.adt_render import adt_call, adt_expected, grades_on_stdout


def snake_to_camel(name: str) -> str:
    """`list_length` -> `listLength`, the TypeScript naming convention."""
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def build_ts_wrapper(problem: dict, source: str, import_path: str) -> str:
    """The full wrapper script text for one problem.

    `source` is the solution being graded (its declarations drive ADT
    constructor and field resolution); `import_path` is the module
    specifier the wrapper imports the entry point from — the only thing
    the two callers legitimately disagree about.
    """
    ts_fn = snake_to_camel(problem["entry_point"])
    test_cases = problem.get("test_cases", [])

    lines = [
        f'import {{ {ts_fn} }} from "{import_path}";',
        "",
        "let _out: string[] = [];",
        "const _log = console.log;",
        "const _cap = (...a: any[]) => { _out.push(a.join(' ') + '\\n'); };",
        # A solution may print with either; capture both.
        "const _w = process.stdout.write.bind(process.stdout);",
        "const _capw = (c: any) => { _out.push(String(c)); return true; };",
        "const _norm = (v: any): any => (v && typeof v === 'object')",
        "  ? (Array.isArray(v) ? v.map(_norm)",
        "     : Object.keys(v).sort().reduce("
        "        (o: any,k)=>{o[k]=_norm(v[k]);return o;},{}))",
        "  : v;",
        "const results: Array<"
        "{passed: boolean, actual?: string, error?: string}> = [];",
        "",
    ]

    for i, tc in enumerate(test_cases):
        args = tc.get("args", [])
        expected = tc.get("expected")
        # Normalize vera-style bools: "true"/"false" become booleans;
        # 1/0 stay ints and rely on the loose == below.
        if isinstance(expected, str) and expected in ("true", "false"):
            expected = expected == "true"
        args_json = json.dumps(args)
        if grades_on_stdout(problem) and not isinstance(expected, str):
            # stdout comparison is textual; a bare `5.trim()` would not
            # even parse, and the wrapper failing to build is recorded as
            # the model's failure.
            expected = str(expected)
        expected_json = json.dumps(expected)
        adt_args = adt_call(problem, source, "typescript", args)
        ts_call = adt_args if adt_args is not None else f"...{args_json}"
        adt_ret_ts = adt_expected(problem, source, "typescript", expected)
        # Loose == (not ===) so a Vera-style 1/0 expected matches a native
        # boolean (VB-T1-006's original false failure). Arrays are the
        # exception: == on arrays is reference equality and always false
        # for a fresh return value, so they compare by JSON — which is
        # value equality for the int/string arrays the problems use.
        lines.extend(
            [
                "try {",
                "  _out = []; console.log = _cap;",
                "  (process.stdout as any).write = _capw;",
                f"  let actual_{i}: any;",
                # The invocation sits in try/finally so the console is
                # restored on every path — success, throw, anything. A
                # restore that lives on the success path and again in the
                # catch is the same behaviour but invites the next editor
                # to add a path that forgets it.
                "  try {",
                f"    actual_{i} = {ts_fn}({ts_call});",
                "  } finally {",
                "    console.log = _log; (process.stdout as any).write = _w;",
                "  }",
                f"  const passed_{i} = "
                + (
                    # @Unit: compare what was printed (#107 step 5).
                    f"_out.join('').trim() === {expected_json}.trim();"
                    if grades_on_stdout(problem)
                    else f"JSON.stringify(_norm(actual_{i})) === "
                    f"JSON.stringify(_norm({adt_ret_ts}));"
                    if adt_ret_ts is not None
                    else f"Array.isArray(actual_{i}) || Array.isArray({expected_json}) "
                    f"? JSON.stringify(actual_{i}) === JSON.stringify({expected_json}) "
                    f": actual_{i} == {expected_json};"
                ),
                f"  results.push({{passed: passed_{i}, actual: String(actual_{i})}});",
                "} catch (e: any) {",
                "  results.push({passed: false, error: String(e)});",
                "}",
                "",
            ]
        )

    lines.append("console.log(JSON.stringify(results));")
    return "\n".join(lines)
