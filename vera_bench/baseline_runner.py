"""Execute Python baseline solutions against test cases."""

from __future__ import annotations

import json
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


def _find_baseline_file(
    problem_id: str,
    solutions_dir: Path,
    language: str,
) -> Path | None:
    """Find the baseline file for a problem by ID prefix match."""
    lang_dir = solutions_dir / language
    prefix = problem_id.replace("-", "_") + "_"
    matches = list(lang_dir.glob(f"{prefix}*.py"))
    return matches[0] if len(matches) == 1 else None


def _build_python_wrapper(
    problem: dict,
    baseline_path: Path,
) -> str:
    """Build a Python wrapper script that runs test cases.

    The wrapper imports the entry_point function, calls it with
    each test case's args, and prints JSON results to stdout.
    """
    entry_point = problem["entry_point"]
    test_cases = problem.get("test_cases", [])

    # Build the test runner code
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
        args_repr = repr(args)
        expected_repr = repr(expected)
        lines.extend(
            [
                "try:",
                f"    actual_{i} = {entry_point}(*{args_repr})",
                f"    passed_{i} = actual_{i} == {expected_repr}",
                f"    results.append({{"
                f'"passed": passed_{i}, '
                f'"actual": repr(actual_{i})}})',
                "except Exception as e:",
                '    results.append({"passed": False, "error": str(e)})',
            ]
        )

    lines.append("print(json.dumps(results))")
    return "\n".join(lines)


def run_python_baseline(
    problem: dict,
    solutions_dir: Path,
    work_dir: Path,
    timeout: int = 30,
) -> ProblemResult:
    """Run a Python baseline solution against test cases."""
    problem_id = problem["id"]
    test_cases = problem.get("test_cases", [])

    # No test cases — nothing to run
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

    # Find baseline file
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

    # Build and write wrapper
    wrapper_code = _build_python_wrapper(problem, baseline_path)
    wrapper_path = work_dir / f"{problem_id}_wrapper.py"
    wrapper_path.write_text(wrapper_code, encoding="utf-8")

    # Execute
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
            error_message="Execution timed out",
            wall_time_s=round(time.monotonic() - start, 2),
            timestamp=_now(),
        )

    elapsed = round(time.monotonic() - start, 2)

    if result.returncode != 0:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="python",
            attempt=1,
            check_pass=True,
            run_correct=False,
            error_message=result.stderr[:200] if result.stderr else "Non-zero exit",
            wall_time_s=elapsed,
            timestamp=_now(),
        )

    # Parse results
    try:
        test_results = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ProblemResult(
            problem_id=problem_id,
            model="baseline",
            language="python",
            attempt=1,
            check_pass=True,
            run_correct=False,
            error_message=f"Bad JSON output: {result.stdout[:100]}",
            wall_time_s=elapsed,
            timestamp=_now(),
        )

    tests_passed = sum(1 for r in test_results if r.get("passed"))
    tests_total = len(test_cases)

    return ProblemResult(
        problem_id=problem_id,
        model="baseline",
        language="python",
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
    work_dir = Path(tempfile.mkdtemp(prefix="verabench_baseline_"))
    all_results: list[ProblemResult] = []

    testable = [p for p in problems if p.get("test_cases")]
    skipped = len(problems) - len(testable)

    if skipped:
        console.print(f"[dim]Skipping {skipped} problems with no test cases[/dim]")

    with Progress(console=console) as progress:
        task = progress.add_task("Running baselines...", total=len(testable))
        for problem in testable:
            result = run_python_baseline(problem, solutions_dir, work_dir)
            all_results.append(result)

            if output_path:
                with open(output_path, "a", encoding="utf-8") as f:
                    f.write(result.to_jsonl() + "\n")

            progress.advance(task)

    return all_results


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
