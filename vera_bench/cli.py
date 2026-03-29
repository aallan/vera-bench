"""CLI entry point for vera-bench."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _repo_root() -> Path:
    return Path(__file__).parent.parent


@click.group()
@click.version_option(package_name="vera-bench")
def main():
    """VeraBench — benchmark suite for the Vera programming language."""


@main.command()
@click.option(
    "--problems-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
@click.option(
    "--solutions-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
def validate(problems_dir: Path | None, solutions_dir: Path | None):
    """Validate all problem definitions and canonical solutions."""
    from vera_bench.validate import run_validation

    raise SystemExit(run_validation(problems_dir, solutions_dir))


@main.command()
@click.option("--model", required=True, help="Model identifier")
@click.option("--tier", type=int, default=None, help="Run only this tier (1-5)")
@click.option("--problem", default=None, help="Run only this problem ID")
@click.option(
    "--mode",
    type=click.Choice(["full-spec", "spec-from-nl"]),
    default="full-spec",
)
@click.option(
    "--skill-md",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
)
@click.option(
    "--max-tokens",
    type=int,
    default=4096,
    help="Max tokens for LLM response",
)
@click.option(
    "--keep-temps",
    is_flag=True,
    help="Keep temporary .vera files",
)
def run(
    model: str,
    tier: int | None,
    problem: str | None,
    mode: str,
    skill_md: Path | None,
    output_dir: Path | None,
    max_tokens: int,
    keep_temps: bool,
):
    """Run benchmark against an LLM model."""
    from vera_bench.metrics import compute_metrics
    from vera_bench.models import create_client
    from vera_bench.prompts import load_skill_md
    from vera_bench.runner import run_benchmark
    from vera_bench.vera_runner import VeraRunner

    root = _repo_root()

    # Load problems
    problems_dir = root / "problems"
    problem_files = sorted(problems_dir.rglob("VB_*.json"))
    problems = []
    for pf in problem_files:
        with open(pf, encoding="utf-8") as f:
            p = json.load(f)
        if tier and p.get("tier") != tier:
            continue
        if problem and p.get("id") != problem:
            continue
        problems.append(p)

    if not problems:
        console.print("[red]No matching problems found.[/red]")
        raise SystemExit(1)

    console.print(f"Found {len(problems)} problems to evaluate.\n")

    # Load SKILL.md
    if skill_md is None:
        skill_md = root / "context" / "SKILL.md"
    skill_content = load_skill_md(skill_md)

    # Set up output
    if output_dir is None:
        output_dir = root / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{model}.jsonl"

    # Create clients
    client = create_client(model)
    vera = VeraRunner()

    console.print(f"Model:   {model}")
    console.print(f"Mode:    {mode}")
    console.print(f"Output:  {output_path}\n")

    # Run benchmark
    results = run_benchmark(
        problems=problems,
        client=client,
        skill_md=skill_content,
        vera=vera,
        mode=mode,
        output_path=output_path,
        max_tokens=max_tokens,
        keep_temps=keep_temps,
    )

    # Print summary
    if results:
        metrics = compute_metrics([json.loads(r.to_jsonl()) for r in results])
        _print_metrics(model, metrics)

    console.print(f"\nResults written to {output_path}")


def _print_metrics(model: str, metrics) -> None:
    """Print a summary metrics table."""
    table = Table(title=f"Results: {model}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Problems", str(metrics.total_problems))
    table.add_row("check@1", f"{metrics.check_rate * 100:.0f}%")
    table.add_row("verify@1", f"{metrics.verify_rate * 100:.0f}%")
    table.add_row("fix@1", f"{metrics.fix_rate * 100:.0f}%")
    table.add_row("run_correct", f"{metrics.run_correct_rate * 100:.0f}%")

    if metrics.by_tier:
        table.add_section()
        for t in sorted(metrics.by_tier):
            tm = metrics.by_tier[t]
            table.add_row(
                f"Tier {t} check@1",
                f"{tm.check_rate * 100:.0f}% ({tm.count})",
            )

    console.print(table)


@main.command()
@click.argument("results_dir", type=click.Path(exists=True, path_type=Path))
def report(results_dir: Path):
    """Generate markdown report from results directory."""
    from vera_bench.report import generate_report

    md = generate_report(results_dir)
    console.print(md)
    summary = results_dir / "summary.md"
    if summary.exists():
        console.print(f"\nReport written to {summary}")
