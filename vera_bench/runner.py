"""Orchestrate benchmark runs: generate -> check -> verify -> run -> fix."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from vera_bench.models import LLMClient
from vera_bench.prompts import (
    build_ailang_fix_prompt,
    build_aver_fix_prompt,
    build_aver_prompt,
    build_fix_prompt,
    build_full_spec_prompt,
    build_python_prompt,
    build_spec_from_nl_prompt,
    build_typescript_prompt,
)
from vera_bench.validate import normalize_output
from vera_bench.vera_runner import VeraRunner

console = Console()

_FENCE_RE = re.compile(
    r"```(?:vera|aver|ailang|ail|python|py|typescript|ts)?\s*\n(.*?)\n?```",
    re.DOTALL,
)


def extract_code(response_text: str) -> str:
    """Extract code from an LLM response.

    Handles markdown-fenced blocks and bare code.
    If multiple fenced blocks, picks the longest.
    """
    matches = _FENCE_RE.findall(response_text)
    if matches:
        code = max(matches, key=len)
    else:
        code = response_text
    return code.strip() + "\n"


# Backward-compatible alias
extract_vera_code = extract_code


@dataclass
class ProblemResult:
    problem_id: str
    model: str
    language: str
    attempt: int
    check_pass: bool
    verify_pass: bool | None = None
    verify_tier1: int = 0
    verify_tier3: int = 0
    run_correct: bool | None = None
    tests_total: int = 0
    tests_passed: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    wall_time_s: float = 0.0
    timestamp: str = ""
    error_message: str | None = None
    bench_version: str = ""
    vera_version: str = ""

    def to_jsonl(self) -> str:
        d = asdict(self)
        # Drop None values for cleaner JSONL
        d = {k: v for k, v in d.items() if v is not None}
        return json.dumps(d, ensure_ascii=False)


def _evaluate_code(
    code: str,
    problem: dict,
    vera: VeraRunner,
    work_dir: Path,
    attempt: int,
) -> dict:
    """Write code to a file and run check/verify/run. Returns result fields."""
    file_path = work_dir / f"{problem['id']}_attempt{attempt}.vera"
    file_path.write_text(code, encoding="utf-8")

    result: dict = {
        "check_pass": False,
        "verify_pass": None,
        "verify_tier1": 0,
        "verify_tier3": 0,
        "run_correct": None,
        "tests_total": 0,
        "tests_passed": 0,
        "error_message": None,
    }

    # vera check
    try:
        check = vera.check(file_path)
        result["check_pass"] = check.passed and check.exit_code == 0
        if not result["check_pass"]:
            errors = [d.get("description", "unknown") for d in check.diagnostics]
            result["error_message"] = "; ".join(errors) or check.stderr
            return result
    except Exception as e:
        result["error_message"] = f"check error: {e}"
        return result

    # vera verify
    try:
        verify = vera.verify(file_path)
        result["verify_pass"] = verify.passed and verify.exit_code == 0
        result["verify_tier1"] = verify.tier1_verified
        result["verify_tier3"] = verify.tier3_runtime
    except Exception as e:
        result["verify_pass"] = False
        result["error_message"] = f"verify error: {e}"

    # Test cases
    test_cases = problem.get("test_cases", [])
    entry_point = problem.get("entry_point", "")
    if not test_cases:
        result["run_correct"] = None
        return result

    all_pass = True
    for tc in test_cases:
        if not isinstance(tc, dict):
            continue
        args = tc.get("args", [])
        expected = tc.get("expected")
        result["tests_total"] += 1
        try:
            run = vera.run_fn(file_path, entry_point, args if args else None)
            if run.exit_code != 0:
                all_pass = False
                continue
            actual, expected_str = normalize_output(run.stdout, expected)
            if actual == expected_str:
                result["tests_passed"] += 1
            else:
                all_pass = False
        except Exception:
            all_pass = False

    result["run_correct"] = all_pass
    return result


def _evaluate_python_code(
    code: str,
    problem: dict,
    work_dir: Path,
    attempt: int,
) -> dict:
    """Write Python code to a file and run test cases via subprocess."""
    entry_point = problem.get("entry_point", "")
    test_cases = problem.get("test_cases", [])

    result: dict = {
        "check_pass": True,
        "verify_pass": None,
        "verify_tier1": 0,
        "verify_tier3": 0,
        "run_correct": None,
        "tests_total": 0,
        "tests_passed": 0,
        "error_message": None,
    }

    if not test_cases:
        return result

    # Write the generated code (sanitize ID for valid Python module name)
    safe_id = problem["id"].replace("-", "_")
    code_path = work_dir / f"{safe_id}_attempt{attempt}.py"
    code_path.write_text(code, encoding="utf-8")

    # Build test wrapper
    wrapper_lines = [
        "import json",
        "import sys",
        f"sys.path.insert(0, {str(work_dir)!r})",
        f"from {code_path.stem} import {entry_point}",
        "",
        "results = []",
    ]

    for i, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            continue
        args = tc.get("args", [])
        expected = tc.get("expected")
        if isinstance(expected, str) and expected in ("true", "false"):
            expected = expected == "true"
        args_repr = repr(args)
        expected_repr = repr(expected)
        wrapper_lines.extend(
            [
                "try:",
                f"    actual_{i} = {entry_point}(*{args_repr})",
                f"    passed_{i} = actual_{i} == {expected_repr}",
                f'    results.append({{"passed": passed_{i},'
                f' "actual": repr(actual_{i})}})',
                "except Exception as e:",
                '    results.append({"passed": False, "error": str(e)})',
            ]
        )

    wrapper_lines.append("print(json.dumps(results))")
    wrapper_path = work_dir / f"{safe_id}_test{attempt}.py"
    wrapper_path.write_text("\n".join(wrapper_lines), encoding="utf-8")

    # Execute with restricted cwd; strip API keys from env
    run_env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    try:
        proc = subprocess.run(  # noqa: S603
            [sys.executable, str(wrapper_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=work_dir,
            env=run_env,
        )
    except subprocess.TimeoutExpired:
        result["tests_total"] = len(test_cases)
        result["run_correct"] = False
        result["error_message"] = "Execution timed out"
        return result

    if proc.returncode != 0:
        err = proc.stderr[:200] if proc.stderr else "Non-zero exit"
        # Errors before test execution are analogous to check failures
        check_errors = (
            "SyntaxError",
            "ImportError",
            "ModuleNotFoundError",
            "IndentationError",
            "TabError",
            "NameError",
        )
        is_check_fail = any(e in err for e in check_errors)
        result["check_pass"] = not is_check_fail
        result["tests_total"] = len(test_cases)
        result["run_correct"] = False
        result["error_message"] = err
        return result

    try:
        test_results = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result["tests_total"] = len(test_cases)
        result["run_correct"] = False
        result["error_message"] = f"Bad output: {proc.stdout[:100]}"
        return result

    passed = sum(1 for r in test_results if r.get("passed"))
    result["tests_total"] = len(test_cases)
    result["tests_passed"] = passed
    result["run_correct"] = passed == len(test_cases)
    return result


def _evaluate_typescript_code(
    code: str,
    problem: dict,
    work_dir: Path,
    attempt: int,
) -> dict:
    """Write TypeScript code to a file and run test cases via npx tsx."""
    from vera_bench.baseline_runner import _snake_to_camel

    entry_point = problem.get("entry_point", "")
    ts_fn = _snake_to_camel(entry_point)
    test_cases = problem.get("test_cases", [])

    result: dict = {
        "check_pass": True,
        "verify_pass": None,
        "verify_tier1": 0,
        "verify_tier3": 0,
        "run_correct": None,
        "tests_total": 0,
        "tests_passed": 0,
        "error_message": None,
    }

    if not test_cases:
        return result

    # Write the generated code with export
    safe_id = problem["id"].replace("-", "_")
    code_path = work_dir / f"{safe_id}_attempt{attempt}.ts"
    # Ensure function is exported
    export_code = code
    if f"export function {ts_fn}" not in code:
        export_code = code.replace(f"function {ts_fn}(", f"export function {ts_fn}(")
    code_path.write_text(export_code, encoding="utf-8")

    # Build test wrapper
    wrapper_lines = [
        f'import {{ {ts_fn} }} from "./{code_path.name}";',
        "",
        "const results: Array<{passed: boolean,"
        " actual?: string, error?: string}> = [];",
        "",
    ]

    for i, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            continue
        args = tc.get("args", [])
        expected = tc.get("expected")
        if isinstance(expected, str) and expected in ("true", "false"):
            expected = expected == "true"
        args_json = json.dumps(args)
        expected_json = json.dumps(expected)
        # Use == (not ===) so true==1 and false==0 match
        wrapper_lines.extend(
            [
                "try {",
                f"  const actual_{i} = {ts_fn}(...{args_json});",
                f"  const passed_{i} = actual_{i} == {expected_json};",
                f"  results.push({{passed: passed_{i}, actual: String(actual_{i})}});",
                "} catch (e: any) {",
                "  results.push({passed: false, error: String(e)});",
                "}",
                "",
            ]
        )

    wrapper_lines.append("console.log(JSON.stringify(results));")
    wrapper_path = work_dir / f"{safe_id}_test{attempt}.ts"
    wrapper_path.write_text("\n".join(wrapper_lines), encoding="utf-8")

    # Find tsx
    tsx = shutil.which("tsx")
    if tsx:
        cmd = [tsx, str(wrapper_path)]
    else:
        npx = shutil.which("npx")
        if npx:
            cmd = [npx, "tsx", str(wrapper_path)]
        else:
            result["check_pass"] = False
            result["error_message"] = "tsx/npx not found on PATH"
            return result

    # Execute
    run_env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=work_dir,
            env=run_env,
        )
    except subprocess.TimeoutExpired:
        result["tests_total"] = len(test_cases)
        result["run_correct"] = False
        result["error_message"] = "Execution timed out"
        return result

    if proc.returncode != 0:
        err = proc.stderr[:200] if proc.stderr else "Non-zero exit"
        check_errors = (
            "SyntaxError",
            "TypeError",
            "ReferenceError",
            "Cannot find module",
        )
        is_check_fail = any(e in err for e in check_errors)
        result["check_pass"] = not is_check_fail
        result["tests_total"] = len(test_cases)
        result["run_correct"] = False
        result["error_message"] = err
        return result

    try:
        test_results = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result["tests_total"] = len(test_cases)
        result["run_correct"] = False
        result["error_message"] = f"Bad output: {proc.stdout[:100]}"
        return result

    passed = sum(1 for r in test_results if r.get("passed"))
    result["tests_total"] = len(test_cases)
    result["tests_passed"] = passed
    result["run_correct"] = passed == len(test_cases)
    return result


def _evaluate_aver_code(
    code: str,
    problem: dict,
    work_dir: Path,
    attempt: int,
) -> dict:
    """Write Aver code to a file and run check + test cases via aver run."""
    entry_point = problem.get("entry_point", "")
    test_cases = problem.get("test_cases", [])

    result: dict = {
        "check_pass": False,
        "verify_pass": None,
        "verify_tier1": 0,
        "verify_tier3": 0,
        "run_correct": None,
        "tests_total": 0,
        "tests_passed": 0,
        "error_message": None,
    }

    # Write the generated code
    safe_id = problem["id"].replace("-", "_")
    code_path = work_dir / f"{safe_id}_attempt{attempt}.av"
    code_path.write_text(code, encoding="utf-8")

    # aver check
    run_env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    try:
        check_proc = subprocess.run(  # noqa: S603
            ["aver", "check", str(code_path)],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=run_env,
        )
    except FileNotFoundError:
        result["error_message"] = "aver not found on PATH"
        return result
    except subprocess.TimeoutExpired:
        result["error_message"] = "aver check timed out"
        return result

    if check_proc.returncode != 0:
        result["check_pass"] = False
        result["error_message"] = (check_proc.stderr or check_proc.stdout)[:500]
        return result

    # aver verify (typecheck + verify blocks in one step)
    try:
        verify_proc = subprocess.run(  # noqa: S603
            ["aver", "verify", str(code_path)],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=run_env,
        )
        result["verify_pass"] = verify_proc.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        result["verify_pass"] = False

    result["check_pass"] = True

    # Test cases — build a single test .av file per test case
    if not test_cases:
        result["run_correct"] = None
        return result

    # Strategy: strip any existing main() from the LLM code and replace
    # with our own that calls the entry_point with specific test args.
    # Also drop any module-level `effects [...]` boundary the LLM
    # declared — Aver 0.13+ enforces it as a hard type error, but the
    # injected main needs `! [Console.print]` which the original
    # boundary may not cover.
    code_without_main = _strip_module_effects(_strip_aver_main(code))

    all_pass = True
    for i, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            continue
        args = tc.get("args", [])
        expected = tc.get("expected")
        result["tests_total"] += 1

        args_str = ", ".join(_aver_literal(a) for a in args)

        # If code has no module declaration, wrap it
        has_module = any(
            line.strip().startswith("module ") for line in code_without_main.split("\n")
        )
        if has_module:
            test_file = (
                f"{code_without_main}\n\n"
                f"fn main() -> Unit\n"
                f"    ! [Console.print]\n"
                f'    Console.print("{{{entry_point}({args_str})}}")\n'
            )
        else:
            test_file = (
                f"module Test{safe_id}\n"
                f'    intent = "Test wrapper"\n\n'
                f"{code_without_main}\n\n"
                f"fn main() -> Unit\n"
                f"    ! [Console.print]\n"
                f'    Console.print("{{{entry_point}({args_str})}}")\n'
            )

        test_path = work_dir / f"{safe_id}_test{i}_attempt{attempt}.av"
        test_path.write_text(test_file, encoding="utf-8")

        try:
            run_proc = subprocess.run(  # noqa: S603
                ["aver", "run", str(test_path)],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=run_env,
            )
        except subprocess.TimeoutExpired:
            all_pass = False
            continue

        if run_proc.returncode != 0:
            all_pass = False
            continue

        actual_output = run_proc.stdout.strip()

        if _aver_output_matches(actual_output, expected):
            result["tests_passed"] += 1
        else:
            all_pass = False

    result["run_correct"] = all_pass
    return result


_IS_MAIN_DEF_RE = re.compile(r"^(\s*)(export\s+)?(pure\s+)?func\s+main\b")
_BARE_CLOSE_BRACE_RE = re.compile(r"^\s*\}\s*(--.*)?$")


def _strip_ailang_main(code: str) -> str:
    """Remove any top-level `main` function from AILANG code.

    Handles all three forms the LLM produces:
      - single-line `= expr`:            `export func main() -> () = ()`
      - single-line block `{ … }`:       `export func main() ! {IO} { println("x") }`
      - multi-line block `{` … `}`:      with body indented and a `}` on a later line
      - multi-line equals form `=` …:    body indented across multiple lines

    Strategy: don't try to count braces — `! {IO}` effect annotations
    contain balanced braces which fooled the previous brace-counting
    heuristic into mis-classifying the def line and leaving the body
    behind as orphan code (the original bug; CR-flagged 2026-05-22 as
    C1 on PR #70).

    Instead, after matching the main def line, consume body lines using
    indentation + structural rules:
      - blank lines are part of the body block
      - lines strictly more indented than the def line are the body
      - a bare `}` (block-close, possibly with a trailing `-- comment`)
        is the body's close-brace and ends the swallow loop
      - any other line at the def's indent level (sibling definitions,
        comments-attached-to-the-next-def) ends the swallow loop

    The harness wraps the LLM's function with its own per-test-case main,
    so any main the LLM supplied is stripped to avoid name conflicts.
    """
    out: list[str] = []
    lines = code.split("\n")
    i, n = 0, len(lines)
    while i < n:
        m = _IS_MAIN_DEF_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue

        def_indent = len(m.group(1))
        i += 1  # skip the def line itself

        # Consume the body until the next sibling top-level item.
        while i < n:
            line = lines[i]
            stripped = line.strip()
            if stripped == "":
                # Blank lines between the def and its body — keep
                # swallowing so the result doesn't accumulate trailing
                # blanks where main used to live.
                i += 1
                continue
            cur_indent = len(line) - len(line.lstrip())
            if cur_indent > def_indent:
                # Indented continuation = body.
                i += 1
                continue
            if cur_indent == def_indent and _BARE_CLOSE_BRACE_RE.match(line):
                # Block-form close brace at def-indent — swallow and stop.
                i += 1
                break
            # Sibling top-level item or comment attached to the next def.
            # Stop swallowing; outer loop resumes with this line preserved.
            break
    return "\n".join(out)


def _ailang_literal(value: object) -> str:
    """Convert a Python value to an AILANG literal expression."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if value < 0:
            return f"({value})"
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_ailang_literal(v) for v in value)
        return f"[{items}]"
    return str(value)


def _evaluate_ailang_code(
    code: str,
    problem: dict,
    work_dir: Path,
    attempt: int,
) -> dict:
    """Wrap the LLM's AILANG code with a per-test-case main and grade.

    Mirrors the Aver pattern: the prompt asks for the function ONLY
    (no main), the harness strips any main the LLM provided anyway,
    then for each test case writes a fresh .ail file that defines the
    LLM's function plus an `export func main() ! {IO}` that calls
    entry_point(args) and prints the result. The harness compares
    that stdout against the expected value per test case.
    """
    entry_point = problem.get("entry_point", "")
    test_cases = problem.get("test_cases", [])

    result: dict = {
        "check_pass": False,
        "verify_pass": None,
        "verify_tier1": 0,
        "verify_tier3": 0,
        "run_correct": None,
        "tests_total": 0,
        "tests_passed": 0,
        "error_message": None,
    }

    safe_id = problem["id"].replace("-", "_")
    run_env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    run_env["AILANG_TRACE"] = "off"

    code_without_main = _strip_ailang_main(code)
    # If the LLM forgot a `module ...` line, add one. AILANG requires
    # the module declaration as the first non-blank/comment line.
    has_module = any(
        line.strip().startswith("module ")
        for line in code_without_main.split("\n")
        if not line.strip().startswith("--")
    )
    if not has_module:
        code_without_main = f"module benchmark/solution\n\n{code_without_main}"

    # Guard against empty / missing-entry-point modules: an empty module
    # type-checks but downstream test invocations would fail with
    # `undefined variable`. Catch this here and report as a clear check
    # failure rather than a generic runtime error per test case.
    entry_point_re = re.compile(
        rf"^\s*(export\s+)?(pure\s+)?func\s+{re.escape(entry_point)}\b"
    )
    has_entry_point = any(
        entry_point_re.match(line) for line in code_without_main.split("\n")
    )
    if not has_entry_point:
        result["check_pass"] = False
        result["error_message"] = (
            f"LLM did not define entry point `{entry_point}` "
            "(empty module or missing function definition)"
        )
        if not test_cases:
            return result
        result["tests_total"] = len(test_cases)
        result["run_correct"] = False
        return result

    # First, type-check the bare module (without any main) — failures here
    # are compile errors and we don't need to attempt test cases.
    check_path = work_dir / f"{safe_id}_check_attempt{attempt}.ail"
    check_path.write_text(code_without_main, encoding="utf-8")
    try:
        check_proc = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "ailang",
                "check",
                "--relax-modules",
                str(check_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=run_env,
        )
    except FileNotFoundError:
        result["error_message"] = "ailang not found on PATH"
        return result
    except subprocess.TimeoutExpired:
        result["error_message"] = "ailang check timed out"
        return result

    # When checking without a main, AILANG may complain about a missing
    # entrypoint or pure-only module — that's the ONE non-zero exit we
    # tolerate, since the harness adds a per-test-case main below. Every
    # other non-zero exit (tagged compile error OR untagged failure) is
    # treated as check failure.
    if check_proc.returncode != 0:
        err = (check_proc.stderr or check_proc.stdout)[:500]
        if "missing main" not in err.lower():
            result["check_pass"] = False
            result["error_message"] = err
            if not test_cases:
                return result
            result["tests_total"] = len(test_cases)
            result["run_correct"] = False
            return result

    result["check_pass"] = True

    if not test_cases:
        result["run_correct"] = None
        return result

    result["tests_total"] = len(test_cases)
    tests_passed = 0
    # Capture the first non-zero stderr from any test-case run for the
    # all-tests-fail diagnostic case. Without this, a model that writes
    # type-correct AILANG that crashes at runtime is indistinguishable
    # in JSONL output from one with wrong logic (error_message=None,
    # check_pass=True, run_correct=False, tests_passed=0). CR-flagged
    # 2026-05-22 as C3 on PR #70. Issue #72 tracks the broader
    # per-test-stderr-loss concern shared with the Aver path.
    last_run_error: str | None = None

    for i, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            continue
        args = tc.get("args", [])
        expected = tc.get("expected")
        args_str = ", ".join(_ailang_literal(a) for a in args)

        test_main = (
            f"\n\nexport func main() -> () ! {{IO}} {{\n"
            f"  println(show({entry_point}({args_str})))\n"
            f"}}\n"
        )
        test_file = code_without_main + test_main
        test_path = work_dir / f"{safe_id}_test{i}_attempt{attempt}.ail"
        test_path.write_text(test_file, encoding="utf-8")

        try:
            run_proc = subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "ailang",
                    "run",
                    "--relax-modules",
                    "--quiet",
                    "--caps",
                    "IO",
                    "--entry",
                    "main",
                    str(test_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=run_env,
            )
        except subprocess.TimeoutExpired:
            if last_run_error is None:
                last_run_error = f"test {i}: ailang run timed out after 30s"
            continue

        if run_proc.returncode != 0:
            if last_run_error is None:
                # stderr-or-stdout coalesce: AILANG runtime errors land on
                # stderr in most cases, but quiet mode + some compile-stage
                # diagnostics land on stdout. Truncate to keep JSONL rows
                # readable.
                err = (run_proc.stderr or run_proc.stdout or "").strip()[:400]
                last_run_error = (
                    f"test {i}: {err}"
                    if err
                    else (f"test {i}: exit {run_proc.returncode} (no output)")
                )
            continue

        actual = run_proc.stdout.strip()
        if _aver_output_matches(actual, expected):
            tests_passed += 1

    result["tests_passed"] = tests_passed
    result["run_correct"] = tests_passed == len(test_cases)
    # Only attach last_run_error if we don't have a more upstream error
    # (e.g. from the check step) — preserve the original failure mode.
    if last_run_error is not None and not result.get("error_message"):
        result["error_message"] = last_run_error
    return result


def _strip_aver_main(code: str) -> str:
    """Remove fn main() and its body from Aver code."""
    lines = code.split("\n")
    result_lines = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("fn main(") or stripped.startswith("fn main ()"):
            skip = True
            continue
        if skip:
            # main body is indented; stop skipping at next top-level item
            if stripped and not line[0:1].isspace():
                skip = False
            else:
                continue
        if not skip:
            result_lines.append(line)
    return "\n".join(result_lines)


_AVER_EFFECTS_OPEN_RE = re.compile(r"^effects\s*\[")


def _strip_module_effects(code: str) -> str:
    """Remove the module header's `effects [...]` declaration if present.

    Aver 0.13+ enforces that every function's `! [Effect]` is covered
    by the module's declared `effects [...]` boundary. The bench
    injects its own `fn main()` with `! [Console.print]`, which would
    violate any narrower boundary the LLM declared (including the
    common `effects []` for "pure" modules). Stripping the line
    returns the module to legacy / no-boundary mode where the
    injected main type-checks.

    Scoped to the module-header window: we start matching after a
    top-level `module X` line and stop at the next top-level item
    (a non-indented, non-blank, non-comment line). Outside that
    window any `effects [...]` we see is left alone — it isn't the
    boundary declaration this strip was written for.
    """
    lines = code.split("\n")
    out = []
    in_module_header = False
    skip_until_close = False
    for line in lines:
        stripped = line.strip()
        indent_len = len(line) - len(line.lstrip(" "))

        if skip_until_close:
            # Multi-line `effects [\n  ...\n]` — drop everything up to
            # and including the line that closes the bracket. Use
            # presence rather than `endswith("]")` so a trailing line
            # comment (Aver's `// ...` syntax) doesn't make us miss
            # the close and chew through the rest of the file.
            if "]" in stripped:
                skip_until_close = False
            continue

        # Track the module-header window. The header runs from the
        # `module X` line through the last indented line before the
        # next top-level item (mirrors how the Aver parser scopes
        # `intent` / `exposes` / `depends` / `effects`).
        if indent_len == 0 and stripped.startswith("module "):
            in_module_header = True
            out.append(line)
            continue
        if (
            in_module_header
            and indent_len == 0
            and stripped
            and not stripped.startswith("//")
        ):
            in_module_header = False

        if (
            in_module_header
            and indent_len > 0
            and _AVER_EFFECTS_OPEN_RE.match(stripped)
        ):
            # Same `]`-presence rule as the skip_until_close branch —
            # tolerates `effects [...] // pure module` (single-line
            # declaration with a trailing comment) without falling into
            # the multi-line skip path that would eat the function body.
            if "]" in stripped:
                continue
            skip_until_close = True
            continue
        out.append(line)
    return "\n".join(out)


def _aver_literal(value) -> str:
    """Convert a Python value to an Aver literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if value < 0:
            return f"(0 - {abs(value)})"
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_aver_literal(v) for v in value)
        return f"[{items}]"
    return str(value)


def _aver_output_matches(actual: str, expected) -> bool:
    """Check if aver output matches expected, handling bool normalization."""
    from vera_bench.baseline_runner import _aver_output_matches as _match

    return _match(actual, expected)


def run_single_problem(
    problem: dict,
    client: LLMClient,
    skill_md: str,
    vera: VeraRunner | None,
    work_dir: Path,
    mode: str = "full-spec",
    language: str = "vera",
    max_fix_attempts: int = 1,
    max_tokens: int = 4096,
    bench_version: str = "",
    vera_version: str = "",
) -> list[ProblemResult]:
    """Run the full pipeline for one problem.

    Returns 1-2 ProblemResults (initial attempt + optional fix).
    """
    results: list[ProblemResult] = []

    # Build prompt
    if language == "aver":
        prompt = build_aver_prompt(problem, skill_md)
    elif language == "ailang":
        from vera_bench.prompts import build_ailang_prompt

        prompt = build_ailang_prompt(problem, skill_md)
    elif language == "python":
        prompt = build_python_prompt(problem)
    elif language == "typescript":
        prompt = build_typescript_prompt(problem)
    elif language == "vera" and mode == "spec-from-nl":
        prompt = build_spec_from_nl_prompt(problem, skill_md)
    elif language == "vera":
        prompt = build_full_spec_prompt(problem, skill_md)
    else:
        raise ValueError(f"Unknown language: {language!r}")

    # Attempt 1: generate
    try:
        llm_response = client.complete(
            system=prompt["system"],
            user=prompt["user"],
            max_tokens=max_tokens,
        )
    except Exception as e:
        results.append(
            ProblemResult(
                problem_id=problem["id"],
                model="unknown",
                language=language,
                attempt=1,
                check_pass=False,
                error_message=f"API error: {e}",
                timestamp=_now(),
                bench_version=bench_version,
                vera_version=vera_version,
            )
        )
        return results

    code = extract_code(llm_response.text)

    if language == "aver":
        eval_result = _evaluate_aver_code(code, problem, work_dir, attempt=1)
    elif language == "ailang":
        eval_result = _evaluate_ailang_code(code, problem, work_dir, attempt=1)
    elif language == "python":
        eval_result = _evaluate_python_code(code, problem, work_dir, attempt=1)
    elif language == "typescript":
        eval_result = _evaluate_typescript_code(code, problem, work_dir, attempt=1)
    elif language == "vera":
        if vera is None:
            raise ValueError("VeraRunner required for language='vera'")
        eval_result = _evaluate_code(code, problem, vera, work_dir, attempt=1)
    else:
        raise ValueError(f"Unknown language: {language!r}")

    results.append(
        ProblemResult(
            problem_id=problem["id"],
            model=llm_response.model,
            language=language,
            attempt=1,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
            wall_time_s=llm_response.wall_time_s,
            timestamp=_now(),
            bench_version=bench_version,
            vera_version=vera_version,
            **eval_result,
        )
    )

    # Attempt 2: fix from error (Aver — only on actual check failures,
    # not tooling errors like "aver not found" or timeouts)
    _err = eval_result.get("error_message") or ""
    _is_tooling_error = (
        "aver not found" in _err or "ailang not found" in _err or "timed out" in _err
    )
    if (
        language == "aver"
        and not eval_result["check_pass"]
        and max_fix_attempts > 0
        and not _is_tooling_error
    ):
        fix_prompt = build_aver_fix_prompt(
            code, eval_result.get("error_message", ""), skill_md
        )
        try:
            fix_response = client.complete(
                system=fix_prompt["system"],
                user=fix_prompt["user"],
                max_tokens=max_tokens,
            )
        except Exception as e:
            results.append(
                ProblemResult(
                    problem_id=problem["id"],
                    model=llm_response.model,
                    language=language,
                    attempt=2,
                    check_pass=False,
                    error_message=f"Fix API error: {e}",
                    timestamp=_now(),
                    bench_version=bench_version,
                    vera_version=vera_version,
                )
            )
            return results

        fix_code = extract_code(fix_response.text)
        fix_eval = _evaluate_aver_code(fix_code, problem, work_dir, attempt=2)

        results.append(
            ProblemResult(
                problem_id=problem["id"],
                model=fix_response.model,
                language=language,
                attempt=2,
                input_tokens=fix_response.input_tokens,
                output_tokens=fix_response.output_tokens,
                wall_time_s=fix_response.wall_time_s,
                timestamp=_now(),
                bench_version=bench_version,
                vera_version=vera_version,
                **fix_eval,
            )
        )

    # Attempt 2: fix from error (AILANG — mirrors the Aver retry path).
    # The previous omission meant `--max-fix-attempts > 0` was silently
    # ignored for AILANG, undercounting it vs Aver/Vera by the entire
    # attempt-2 contribution. CR-flagged 2026-05-22 as C2 on PR #70.
    if (
        language == "ailang"
        and not eval_result["check_pass"]
        and max_fix_attempts > 0
        and not _is_tooling_error
    ):
        fix_prompt = build_ailang_fix_prompt(
            code, eval_result.get("error_message", ""), skill_md
        )
        try:
            fix_response = client.complete(
                system=fix_prompt["system"],
                user=fix_prompt["user"],
                max_tokens=max_tokens,
            )
        except Exception as e:
            results.append(
                ProblemResult(
                    problem_id=problem["id"],
                    model=llm_response.model,
                    language=language,
                    attempt=2,
                    check_pass=False,
                    error_message=f"Fix API error: {e}",
                    timestamp=_now(),
                    bench_version=bench_version,
                    vera_version=vera_version,
                )
            )
            return results

        fix_code = extract_code(fix_response.text)
        fix_eval = _evaluate_ailang_code(fix_code, problem, work_dir, attempt=2)

        results.append(
            ProblemResult(
                problem_id=problem["id"],
                model=fix_response.model,
                language=language,
                attempt=2,
                input_tokens=fix_response.input_tokens,
                output_tokens=fix_response.output_tokens,
                wall_time_s=fix_response.wall_time_s,
                timestamp=_now(),
                bench_version=bench_version,
                vera_version=vera_version,
                **fix_eval,
            )
        )

    # Attempt 2: fix from error (Vera only — Python has no check step)
    if language == "vera" and not eval_result["check_pass"] and max_fix_attempts > 0:
        fix_prompt = build_fix_prompt(code, eval_result.get("error_message", ""))
        try:
            fix_response = client.complete(
                system=fix_prompt["system"],
                user=fix_prompt["user"],
                max_tokens=max_tokens,
            )
        except Exception as e:
            results.append(
                ProblemResult(
                    problem_id=problem["id"],
                    model=llm_response.model,
                    language=language,
                    attempt=2,
                    check_pass=False,
                    error_message=f"Fix API error: {e}",
                    timestamp=_now(),
                    bench_version=bench_version,
                    vera_version=vera_version,
                )
            )
            return results

        fix_code = extract_code(fix_response.text)
        fix_eval = _evaluate_code(fix_code, problem, vera, work_dir, attempt=2)

        results.append(
            ProblemResult(
                problem_id=problem["id"],
                model=fix_response.model,
                language=language,
                attempt=2,
                input_tokens=fix_response.input_tokens,
                output_tokens=fix_response.output_tokens,
                wall_time_s=fix_response.wall_time_s,
                timestamp=_now(),
                bench_version=bench_version,
                vera_version=vera_version,
                **fix_eval,
            )
        )

    return results


def run_benchmark(
    problems: list[dict],
    client: LLMClient,
    skill_md: str,
    vera: VeraRunner | None,
    mode: str = "full-spec",
    language: str = "vera",
    output_path: Path | None = None,
    max_fix_attempts: int = 1,
    max_tokens: int = 4096,
    keep_temps: bool = False,
    bench_version: str = "",
    vera_version: str = "",
    parallel: int = 1,
) -> list[ProblemResult]:
    """Run the full benchmark across all problems.

    Results are written to JSONL incrementally (survives crashes).

    When ``parallel > 1``, problems are dispatched to a ThreadPoolExecutor
    with ``parallel`` workers. Each problem runs independently (its own
    LLM call, its own subprocess-based check/run), so threads only block
    on I/O (HTTP to the LLM provider, subprocess spawns to the toolchain).
    The GIL is not a bottleneck. Use this when sweeping slow models —
    e.g. Kimi K2.5 at ~50s/problem sequential becomes ~5s/problem with
    parallel=10.

    JSONL output ordering is by completion order, not by problem index,
    when running in parallel. Each line is self-contained (carries
    ``problem_id``) so downstream consumers can sort if needed.

    Worker exceptions are caught (in both sequential and parallel paths)
    and converted into a visible ``ProblemResult`` row written to JSONL,
    so downstream ``vera-bench report`` sees an honest denominator
    rather than a silent under-report when a problem crashes.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="verabench_"))
    all_results: list[ProblemResult] = []

    def _record(problem_results: list[ProblemResult]) -> None:
        """Append results to the in-memory list AND to output_path (if set)."""
        all_results.extend(problem_results)
        if output_path:
            with open(output_path, "a", encoding="utf-8") as f:
                for r in problem_results:
                    f.write(r.to_jsonl() + "\n")

    def _crash_result(problem: dict, exc: BaseException, tb: str) -> ProblemResult:
        """Synthesise a ProblemResult representing a worker crash.

        Before this existed, worker exceptions vanished silently from the
        parallel path: a 60-problem sweep with 2 crashes wrote 58 JSONL
        rows and downstream ``vera-bench report`` showed "58/58 (100%)" —
        the operator wouldn't know problems had crashed. The crash row
        keeps the denominator honest and embeds the full traceback in
        ``error_message`` for post-hoc debugging.
        """
        return ProblemResult(
            problem_id=problem.get("id", "?"),
            model=getattr(client, "_model", "unknown"),
            language=language,
            attempt=0,
            check_pass=False,
            run_correct=False,
            error_message=f"Worker crash: {exc!r}\n{tb}",
            timestamp=_now(),
            bench_version=bench_version,
            vera_version=vera_version,
        )

    try:
        if parallel <= 1:
            with Progress(console=console) as progress:
                task = progress.add_task("Running benchmark...", total=len(problems))
                for problem in problems:
                    # Symmetry with the parallel path: a single problem's
                    # crash is logged + recorded + sweep continues, rather
                    # than aborting the whole run on problem N of M.
                    try:
                        problem_results = run_single_problem(
                            problem=problem,
                            client=client,
                            skill_md=skill_md,
                            vera=vera,
                            work_dir=work_dir,
                            mode=mode,
                            language=language,
                            max_fix_attempts=max_fix_attempts,
                            max_tokens=max_tokens,
                            bench_version=bench_version,
                            vera_version=vera_version,
                        )
                    except Exception as exc:  # noqa: BLE001
                        tb = traceback.format_exc()
                        pid = problem.get("id", "?")
                        console.print(f"[red]Worker failed on {pid}: {exc!r}[/red]")
                        console.print(f"[dim]{tb}[/dim]")
                        _record([_crash_result(problem, exc, tb)])
                        progress.advance(task)
                        continue
                    _record(problem_results)
                    progress.advance(task)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            # No write lock needed: the `for fut in as_completed(...)` loop
            # below runs on the main thread, so the JSONL appends are
            # already serialised by the loop structure. Workers only run
            # `_run_one` (the LLM/subprocess work), never touch output_path.

            def _run_one(p: dict) -> list[ProblemResult]:
                return run_single_problem(
                    problem=p,
                    client=client,
                    skill_md=skill_md,
                    vera=vera,
                    work_dir=work_dir,
                    mode=mode,
                    language=language,
                    max_fix_attempts=max_fix_attempts,
                    max_tokens=max_tokens,
                    bench_version=bench_version,
                    vera_version=vera_version,
                )

            with Progress(console=console) as progress:
                task = progress.add_task(
                    f"Running benchmark (parallel={parallel})...",
                    total=len(problems),
                )
                with ThreadPoolExecutor(max_workers=parallel) as executor:
                    futures = {executor.submit(_run_one, p): p for p in problems}
                    for fut in as_completed(futures):
                        problem = futures[fut]
                        try:
                            problem_results = fut.result()
                        except Exception as exc:  # noqa: BLE001
                            tb = traceback.format_exc()
                            pid = problem.get("id", "?")
                            console.print(f"[red]Worker failed on {pid}: {exc!r}[/red]")
                            console.print(f"[dim]{tb}[/dim]")
                            _record([_crash_result(problem, exc, tb)])
                            progress.advance(task)
                            continue
                        _record(problem_results)
                        progress.advance(task)
    finally:
        if not keep_temps:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            console.print(f"[dim]Temp files kept at: {work_dir}[/dim]")

    return all_results


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
