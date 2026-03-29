"""CLI entry point for vera-bench."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

console = Console()


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
@click.option("--tier", type=int, default=None, help="Run only this tier")
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
def run(
    model: str,
    tier: int | None,
    problem: str | None,
    mode: str,
    skill_md: Path | None,
    output_dir: Path | None,
):
    """Run benchmark against a model (not yet implemented)."""
    console.print("[yellow]vera-bench run is not yet implemented.[/yellow]")
    console.print(f"  model:  {model}")
    console.print(f"  tier:   {tier or 'all'}")
    console.print(f"  mode:   {mode}")


@main.command()
@click.argument("results_dir", type=click.Path(exists=True, path_type=Path))
def report(results_dir: Path):
    """Generate report from results directory (not yet implemented)."""
    console.print("[yellow]vera-bench report is not yet implemented.[/yellow]")
    console.print(f"  dir: {results_dir}")
