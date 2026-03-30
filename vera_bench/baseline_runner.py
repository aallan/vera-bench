"""Execute Python and TypeScript baseline solutions against test cases."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from vera_bench.runner import ProblemResult

console = Console()

_EXT = {"python": ".py", "typescript": ".ts"}


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


def _find_baseline_file(
    problem_id: str,
    solutions_dir: Path,
    language: str,
) -> Path | None:
    """Find the baseline file for a problem by ID prefix match."""
    lang_dir = solutions_dir / language
    ext = _EXT.get(language, ".py")
    prefix = problem_id.replace("-", "_") + "_"
    matches = list(lang_dir.glob(f"{prefix}*{ext}"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = [str(m) for m in matches]
        raise ValueError(f"Multiple baselines for {prefix} in {lang_dir}: {names}")
    return None


def _build_python_wrapper(
    problem: dict,
    baseline_path: Path,
) -> str:
    """Build a Python wrapper script that runs test cases."""
    entry_point = problem["entry_point"]
    test_cases = problem.get("test_cases", [])

    lines = [
        "import json",
        "import sys",
        f"sys.path.insert(0, {str(baseline_path.parent)!r})",
        f"from {baseline_path.stem} import {entry_point}",
        "",
        "results = []",
    ]

    for i, tc in enumerate(test_cases):
        args = tc.get("args", [])
        expected = tc.get("expected")
        if isinstance(expected, str) and expected in ("true", "false"):
            expected = expected == "true"
        args_repr = repr(args)
        expected_repr = repr(expected)
        lines.extend(
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

    lines.append("print(json.dumps(results))")
    return "\n".join(lines)


def _build_typescript_wrapper(
    problem: dict,
    baseline_path: Path,
) -> str:
    """Build a TypeScript wrapper script that runs test cases."""
    entry_point = problem["entry_point"]
    ts_fn = _snake_to_camel(entry_point)
    test_cases = problem.get("test_cases", [])

    # Use relative import path for the baseline
    rel_path = f"./{baseline_path.name}"

    lines = [
        f'import {{ {ts_fn} }} from "{rel_path}";',
        "",
        "const results: Array<"
        "{passed: boolean, actual?: string, error?: string}> = [];",
        "",
    ]

    for i, tc in enumerate(test_cases):
        args = tc.get("args", [])
        expected = tc.get("expected")
        # Normalize vera-style bools: "true"/"false" strings or 1/0 ints
        if isinstance(expected, str) and expected in ("true", "false"):
            expected = expected == "true"
        elif isinstance(expected, int) and expected in (0, 1):
            # Could be a bool — use loose comparison to handle both
            pass  # keep as int, use == below
        args_json = json.dumps(args)
        expected_json = json.dumps(expected)
        # Use == (not ===) so true==1 and false==0 match
        lines.extend(
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

    lines.append("console.log(JSON.stringify(results));")
    return "\n".join(lines)


def _tsx_bin() -> str | None:
    """Find tsx executable, or return None if not available."""
    return shutil.which("tsx") or shutil.which("npx")


def run_python_baseline(
    problem: dict,
    solutions_dir: Path,
    work_dir: Path,
    timeout: int = 30,
) -> ProblemResult:
    """Run a Python baseline solution against test cases."""
    problem_id = problem["id"]
    test_cases = problem.get("test_cases", [])

    if not test_cases:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="python",
            attempt=1,
            check_pass=True,
            run_correct=None,
            timestamp=_now(),
        )

    baseline_path = _find_baseline_file(problem_id, solutions_dir, "python")
    if baseline_path is None:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="python",
            attempt=1,
            check_pass=False,
            error_message=f"No Python baseline found for {problem_id}",
            timestamp=_now(),
        )

    wrapper_code = _build_python_wrapper(problem, baseline_path)
    wrapper_path = work_dir / f"{problem_id}_wrapper.py"
    wrapper_path.write_text(wrapper_code, encoding="utf-8")

    start = time.monotonic()
    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(wrapper_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="python",
            attempt=1,
            check_pass=True,
            run_correct=False,
            tests_total=len(test_cases),
            error_message="Execution timed out",
            wall_time_s=round(time.monotonic() - start, 2),
            timestamp=_now(),
        )

    return _parse_subprocess_result(result, problem_id, "python", test_cases, start)


def run_typescript_baseline(
    problem: dict,
    solutions_dir: Path,
    work_dir: Path,
    timeout: int = 30,
) -> ProblemResult:
    """Run a TypeScript baseline solution against test cases."""
    problem_id = problem["id"]
    test_cases = problem.get("test_cases", [])

    if not test_cases:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="typescript",
            attempt=1,
            check_pass=True,
            run_correct=None,
            timestamp=_now(),
        )

    baseline_path = _find_baseline_file(problem_id, solutions_dir, "typescript")
    if baseline_path is None:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="typescript",
            attempt=1,
            check_pass=False,
            error_message=(f"No TypeScript baseline found for {problem_id}"),
            timestamp=_now(),
        )

    # Copy baseline to work_dir so relative imports work
    work_baseline = work_dir / baseline_path.name
    shutil.copy2(baseline_path, work_baseline)

    # The TS files don't export — add export wrapper
    _add_ts_export(work_baseline, problem)

    wrapper_code = _build_typescript_wrapper(problem, work_baseline)
    wrapper_path = work_dir / f"{problem_id}_wrapper.ts"
    wrapper_path.write_text(wrapper_code, encoding="utf-8")

    # Find tsx/npx
    tsx_path = _tsx_bin()
    if tsx_path is None:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="typescript",
            attempt=1,
            check_pass=False,
            error_message="tsx/npx not found on PATH",
            timestamp=_now(),
        )

    if Path(tsx_path).stem.lower() == "npx":
        cmd = [tsx_path, "tsx", str(wrapper_path)]
    else:
        cmd = [tsx_path, str(wrapper_path)]

    # Strip API keys from env
    run_env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}

    start = time.monotonic()
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=work_dir,
            env=run_env,
        )
    except subprocess.TimeoutExpired:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="typescript",
            attempt=1,
            check_pass=True,
            run_correct=False,
            tests_total=len(test_cases),
            error_message="Execution timed out",
            wall_time_s=round(time.monotonic() - start, 2),
            timestamp=_now(),
        )

    return _parse_subprocess_result(result, problem_id, "typescript", test_cases, start)


def _add_ts_export(file_path: Path, problem: dict) -> None:
    """Add export to a TS baseline file that uses bare function decls."""
    entry_point = problem["entry_point"]
    ts_fn = _snake_to_camel(entry_point)
    content = file_path.read_text(encoding="utf-8")
    # Replace 'function name(' with 'export function name('
    if f"export function {ts_fn}" not in content:
        content = content.replace(f"function {ts_fn}(", f"export function {ts_fn}(")
        file_path.write_text(content, encoding="utf-8")


def _parse_subprocess_result(
    result: subprocess.CompletedProcess,
    problem_id: str,
    language: str,
    test_cases: list,
    start: float,
) -> ProblemResult:
    """Parse subprocess output into a ProblemResult."""
    elapsed = round(time.monotonic() - start, 2)

    if result.returncode != 0:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language=language,
            attempt=1,
            check_pass=True,
            run_correct=False,
            tests_total=len(test_cases),
            error_message=(result.stderr[:200] if result.stderr else "Non-zero exit"),
            wall_time_s=elapsed,
            timestamp=_now(),
        )

    try:
        test_results = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language=language,
            attempt=1,
            check_pass=True,
            run_correct=False,
            tests_total=len(test_cases),
            error_message=f"Bad JSON output: {result.stdout[:100]}",
            wall_time_s=elapsed,
            timestamp=_now(),
        )

    tests_passed = sum(1 for r in test_results if r.get("passed"))
    tests_total = len(test_cases)

    return ProblemResult(
        problem_id=problem_id,
        model="baseline",
        language=language,
        attempt=1,
        check_pass=True,
        run_correct=(tests_passed == tests_total),
        tests_total=tests_total,
        tests_passed=tests_passed,
        wall_time_s=elapsed,
        timestamp=_now(),
    )


def run_all_baselines(
    problems: list[dict],
    solutions_dir: Path,
    output_path: Path | None = None,
    language: str = "python",
) -> list[ProblemResult]:
    """Run baselines for all problems. Write JSONL incrementally."""
    if language not in ("python", "typescript"):
        raise NotImplementedError(
            f"Baseline runner for {language!r} not yet implemented"
        )

    runner = run_python_baseline if language == "python" else run_typescript_baseline

    all_results: list[ProblemResult] = []

    testable = [p for p in problems if p.get("test_cases")]
    skipped = len(problems) - len(testable)

    if skipped:
        console.print(f"[dim]Skipping {skipped} problems with no test cases[/dim]")

    with tempfile.TemporaryDirectory(prefix="verabench_baseline_") as tmpdir:
        work_dir = Path(tmpdir)
        with Progress(console=console) as progress:
            task = progress.add_task("Running baselines...", total=len(testable))
            for problem in testable:
                result = runner(problem, solutions_dir, work_dir)
                all_results.append(result)

                if output_path:
                    with open(output_path, "a", encoding="utf-8") as f:
                        f.write(result.to_jsonl() + "\n")

                progress.advance(task)

    return all_results


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
