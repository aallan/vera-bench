"""Generate markdown reports from benchmark results."""

from __future__ import annotations

from pathlib import Path

from vera_bench.metrics import (
    BenchmarkMetrics,
    compute_metrics,
    load_results,
)


def generate_report(results_dir: Path) -> str:
    """Generate a markdown report from all JSONL files in results_dir.

    Each .jsonl file is treated as one model's results.
    Returns the markdown string and writes summary.md.
    """
    jsonl_files = sorted(results_dir.glob("*.jsonl"))
    if not jsonl_files:
        return "No .jsonl result files found.\n"

    all_model_results: dict[str, list[dict]] = {}
    all_model_metrics: dict[str, BenchmarkMetrics] = {}

    for jf in jsonl_files:
        model_name = jf.stem
        results = load_results(jf)
        if results:
            all_model_results[model_name] = results
            all_model_metrics[model_name] = compute_metrics(results)

    if not all_model_metrics:
        return "No results to report.\n"

    sections = [
        "# VeraBench Results\n",
        _summary_table(all_model_metrics),
        _tier_breakdown(all_model_metrics),
        _per_problem_detail(all_model_results),
    ]

    report = "\n".join(sections)

    summary_path = results_dir / "summary.md"
    summary_path.write_text(report, encoding="utf-8")

    return report


def _pct(rate: float | None) -> str:
    if rate is None:
        return "-"
    return f"{rate * 100:.0f}%"


def _summary_table(
    all_metrics: dict[str, BenchmarkMetrics],
) -> str:
    lines = [
        "## Summary\n",
        "| Model | check@1 | verify@1 | fix@1 | run_correct | Problems |",
        "|-------|---------|----------|-------|-------------|----------|",
    ]
    for model, m in sorted(all_metrics.items()):
        lines.append(
            f"| {model} "
            f"| {_pct(m.check_rate)} "
            f"| {_pct(m.verify_rate)} "
            f"| {_pct(m.fix_rate)} "
            f"| {_pct(m.run_correct_rate)} "
            f"| {m.total_problems} |"
        )
    return "\n".join(lines) + "\n"


def _tier_breakdown(
    all_metrics: dict[str, BenchmarkMetrics],
) -> str:
    lines = [
        "## By Tier\n",
        "| Model | Metric | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |",
        "|-------|--------|--------|--------|--------|--------|--------|",
    ]
    for model, m in sorted(all_metrics.items()):
        for metric_name, attr in [
            ("check@1", "check_rate"),
            ("verify@1", "verify_rate"),
            ("fix@1", "fix_rate"),
            ("run_correct", "run_correct_rate"),
        ]:
            tier_vals = []
            for t in range(1, 6):
                tm = m.by_tier.get(t)
                tier_vals.append(_pct(getattr(tm, attr)) if tm else "-")
            lines.append(f"| {model} | {metric_name} | {' | '.join(tier_vals)} |")
    return "\n".join(lines) + "\n"


def _per_problem_detail(
    all_results: dict[str, list[dict]],
) -> str:
    lines = [
        "## Per-Problem Detail\n",
    ]
    for model, results in sorted(all_results.items()):
        lines.append(f"### {model}\n")
        lines.append("| Problem | check@1 | verify | fix | run | tokens | time |")
        lines.append("|---------|---------|--------|-----|-----|--------|------|")

        # Group by problem, show best attempt
        by_problem: dict[str, list[dict]] = {}
        for r in results:
            pid = r.get("problem_id", "")
            by_problem.setdefault(pid, []).append(r)

        for pid in sorted(by_problem):
            attempts = by_problem[pid]
            a1 = next(
                (a for a in attempts if a.get("attempt") == 1),
                None,
            )
            a2 = next(
                (a for a in attempts if a.get("attempt") == 2),
                None,
            )

            check = _pass_fail(a1.get("check_pass") if a1 else None)
            verify = _pass_fail(a1.get("verify_pass") if a1 else None)
            fix = _pass_fail(a2.get("check_pass")) if a2 else "-"

            best = a2 if a2 and a2.get("check_pass") else a1
            run = _pass_fail(best.get("run_correct") if best else None)
            tokens = best.get("output_tokens", 0) if best else 0
            wall = best.get("wall_time_s", 0) if best else 0

            lines.append(
                f"| {pid} | {check} | {verify} | {fix} | {run} | {tokens} | {wall}s |"
            )

        lines.append("")

    return "\n".join(lines)


def _pass_fail(value: bool | None) -> str:
    if value is None:
        return "-"
    return "PASS" if value else "FAIL"
