"""Metric computation and aggregation for benchmark results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TierMetrics:
    tier: int
    count: int
    check_rate: float
    verify_rate: float
    fix_rate: float
    run_correct_rate: float


@dataclass
class BenchmarkMetrics:
    total_problems: int
    check_rate: float
    verify_rate: float
    fix_rate: float
    run_correct_rate: float
    by_tier: dict[int, TierMetrics]


def load_results(path: Path) -> list[dict]:
    """Load a JSONL results file into a list of dicts."""
    results = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def compute_metrics(results: list[dict]) -> BenchmarkMetrics:
    """Compute aggregate metrics from result records."""
    # Group by problem_id
    by_problem: dict[str, list[dict]] = {}
    for r in results:
        pid = r.get("problem_id", "")
        by_problem.setdefault(pid, []).append(r)

    total = len(by_problem)
    if total == 0:
        return BenchmarkMetrics(
            total_problems=0,
            check_rate=0.0,
            verify_rate=0.0,
            fix_rate=0.0,
            run_correct_rate=0.0,
            by_tier={},
        )

    check_pass_count = 0
    verify_pass_count = 0
    verify_eligible = 0
    fix_success = 0
    fix_eligible = 0
    run_correct_count = 0
    run_eligible = 0

    for pid, attempts in by_problem.items():
        attempt_1 = next((a for a in attempts if a.get("attempt") == 1), None)
        attempt_2 = next((a for a in attempts if a.get("attempt") == 2), None)
        best = attempt_2 if attempt_2 and attempt_2.get("check_pass") else attempt_1

        if not attempt_1:
            continue

        # check@1
        if attempt_1.get("check_pass"):
            check_pass_count += 1

        # fix@1
        if not attempt_1.get("check_pass"):
            fix_eligible += 1
            if attempt_2 and attempt_2.get("check_pass"):
                fix_success += 1

        # verify (on best passing attempt)
        if best and best.get("check_pass"):
            verify_eligible += 1
            if best.get("verify_pass"):
                verify_pass_count += 1

        # run_correct (on best passing attempt)
        if best and best.get("check_pass"):
            rc = best.get("run_correct")
            if rc is not None:
                run_eligible += 1
                if rc:
                    run_correct_count += 1

    overall = BenchmarkMetrics(
        total_problems=total,
        check_rate=_rate(check_pass_count, total),
        verify_rate=_rate(verify_pass_count, verify_eligible),
        fix_rate=_rate(fix_success, fix_eligible),
        run_correct_rate=_rate(run_correct_count, run_eligible),
        by_tier=_compute_by_tier(by_problem),
    )
    return overall


def _compute_by_tier(
    by_problem: dict[str, list[dict]],
) -> dict[int, TierMetrics]:
    """Compute per-tier metrics."""
    tier_problems: dict[int, dict[str, list[dict]]] = {}
    for pid, attempts in by_problem.items():
        tier = _tier_from_id(pid)
        tier_problems.setdefault(tier, {})[pid] = attempts

    result = {}
    for tier, problems in sorted(tier_problems.items()):
        count = len(problems)
        check = 0
        verify = 0
        verify_elig = 0
        fix_ok = 0
        fix_elig = 0
        run_ok = 0
        run_elig = 0

        for pid, attempts in problems.items():
            a1 = next((a for a in attempts if a.get("attempt") == 1), None)
            a2 = next((a for a in attempts if a.get("attempt") == 2), None)
            best = a2 if a2 and a2.get("check_pass") else a1

            if not a1:
                continue
            if a1.get("check_pass"):
                check += 1
            if not a1.get("check_pass"):
                fix_elig += 1
                if a2 and a2.get("check_pass"):
                    fix_ok += 1
            if best and best.get("check_pass"):
                verify_elig += 1
                if best.get("verify_pass"):
                    verify += 1
                rc = best.get("run_correct")
                if rc is not None:
                    run_elig += 1
                    if rc:
                        run_ok += 1

        result[tier] = TierMetrics(
            tier=tier,
            count=count,
            check_rate=_rate(check, count),
            verify_rate=_rate(verify, verify_elig),
            fix_rate=_rate(fix_ok, fix_elig),
            run_correct_rate=_rate(run_ok, run_elig),
        )

    return result


def _tier_from_id(problem_id: str) -> int:
    """Extract tier number from problem ID like VB-T1-001."""
    try:
        return int(problem_id.split("-")[1][1:])
    except (IndexError, ValueError):
        return 0


def _rate(num: int, denom: int) -> float:
    if denom == 0:
        return 0.0
    return round(num / denom, 4)
