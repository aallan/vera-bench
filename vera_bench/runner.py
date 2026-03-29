"""Orchestrate benchmark runs: generate -> check -> verify -> run -> fix."""

from __future__ import annotations

import json
import re
import shutil
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
    build_spec_from_nl_prompt,
)
from vera_bench.validate import normalize_output
from vera_bench.vera_runner import VeraRunner

console = Console()

_FENCE_RE = re.compile(r"```(?:vera)?\s*\n(.*?)\n?```", re.DOTALL)


def extract_vera_code(response_text: str) -> str:
    """Extract Vera code from an LLM response.

    Handles markdown-fenced blocks (```vera ... ```) and bare code.
    If multiple fenced blocks, picks the longest.
    """
    matches = _FENCE_RE.findall(response_text)
    if matches:
        code = max(matches, key=len)
    else:
        code = response_text
    return code.strip() + "\n"


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


def run_single_problem(
    problem: dict,
    client: LLMClient,
    skill_md: str,
    vera: VeraRunner,
    work_dir: Path,
    mode: str = "full-spec",
    max_fix_attempts: int = 1,
    max_tokens: int = 4096,
) -> list[ProblemResult]:
    """Run the full pipeline for one problem.

    Returns 1-2 ProblemResults (initial attempt + optional fix).
    """
    results: list[ProblemResult] = []

    # Build prompt
    if mode == "spec-from-nl":
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
                language="vera",
                attempt=1,
                check_pass=False,
                error_message=f"API error: {e}",
                timestamp=_now(),
            )
        )
        return results

    code = extract_vera_code(llm_response.text)
    eval_result = _evaluate_code(code, problem, vera, work_dir, attempt=1)

    results.append(
        ProblemResult(
            problem_id=problem["id"],
            model=llm_response.model,
            language="vera",
            attempt=1,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
            wall_time_s=llm_response.wall_time_s,
            timestamp=_now(),
            **eval_result,
        )
    )

    # Attempt 2: fix from error (if check failed)
    if not eval_result["check_pass"] and max_fix_attempts > 0:
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
                    language="vera",
                    attempt=2,
                    check_pass=False,
                    error_message=f"Fix API error: {e}",
                    timestamp=_now(),
                )
            )
            return results

        fix_code = extract_vera_code(fix_response.text)
        fix_eval = _evaluate_code(fix_code, problem, vera, work_dir, attempt=2)

        results.append(
            ProblemResult(
                problem_id=problem["id"],
                model=fix_response.model,
                language="vera",
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
    vera: VeraRunner,
    mode: str = "full-spec",
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
