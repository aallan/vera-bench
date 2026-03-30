"""Orchestrate benchmark runs: generate -> check -> verify -> run -> fix."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from vera_bench.models import LLMClient
from vera_bench.prompts import (
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
    r"```(?:vera|python|py|typescript|ts)?\s*\n(.*?)\n?```", re.DOTALL
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
) -> list[ProblemResult]:
    """Run the full pipeline for one problem.

    Returns 1-2 ProblemResults (initial attempt + optional fix).
    """
    results: list[ProblemResult] = []

    # Build prompt
    if language == "python":
        prompt = build_python_prompt(problem)
    elif language == "typescript":
        prompt = build_typescript_prompt(problem)
    elif mode == "spec-from-nl":
        prompt = build_spec_from_nl_prompt(problem, skill_md)
    else:
        prompt = build_full_spec_prompt(problem, skill_md)

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
            )
        )
        return results

    code = extract_code(llm_response.text)

    if language == "python":
        eval_result = _evaluate_python_code(code, problem, work_dir, attempt=1)
    elif language == "typescript":
        eval_result = _evaluate_typescript_code(code, problem, work_dir, attempt=1)
    else:
        if vera is None:
            raise ValueError("VeraRunner required for language='vera'")
        eval_result = _evaluate_code(code, problem, vera, work_dir, attempt=1)

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
            **eval_result,
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
) -> list[ProblemResult]:
    """Run the full benchmark across all problems.

    Results are written to JSONL incrementally (survives crashes).
    """
    work_dir = Path(tempfile.mkdtemp(prefix="verabench_"))
    all_results: list[ProblemResult] = []

    try:
        with Progress(console=console) as progress:
            task = progress.add_task("Running benchmark...", total=len(problems))
            for problem in problems:
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
                )
                all_results.extend(problem_results)

                # Write JSONL incrementally
                if output_path:
                    with open(output_path, "a", encoding="utf-8") as f:
                        for r in problem_results:
                            f.write(r.to_jsonl() + "\n")

                progress.advance(task)
    finally:
        if not keep_temps:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            console.print(f"[dim]Temp files kept at: {work_dir}[/dim]")

    return all_results


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
