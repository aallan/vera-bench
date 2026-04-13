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
    "--language",
    type=click.Choice(["vera", "python", "typescript", "aver"]),
    default="vera",
    help="Target language for code generation",
)
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
    help="Keep temporary generated files",
)
def run(
    model: str,
    tier: int | None,
    problem: str | None,
    language: str,
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

    # Warn on flags that are ignored for the selected language
    if language not in ("vera", "aver"):
        if skill_md is not None:
            console.print(
                f"[yellow]Warning: --skill-md is ignored "
                f"with --language {language}[/yellow]"
            )
        if mode != "full-spec":
            console.print(
                f"[yellow]Warning: --mode is ignored "
                f"with --language {language}[/yellow]"
            )
    if language == "aver" and mode != "full-spec":
        console.print(
            f"[yellow]Warning: --mode {mode} is ignored with --language aver[/yellow]"
        )

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

    # Load language spec (SKILL.md for Vera, llms.txt for Aver)
    skill_content = ""
    if language == "vera":
        import hashlib

        from vera_bench.prompts import SKILL_MD_URL

        source = str(skill_md) if skill_md else SKILL_MD_URL
        skill_content = load_skill_md(skill_md)
        content_hash = hashlib.sha256(skill_content.encode()).hexdigest()[:12]
        console.print(f"SKILL.md: {source} ({content_hash})")
    elif language == "aver":
        import hashlib

        from vera_bench.prompts import AVER_LLMS_TXT_URL, load_aver_llms_txt

        source = str(skill_md) if skill_md else AVER_LLMS_TXT_URL
        skill_content = load_aver_llms_txt(skill_md)
        content_hash = hashlib.sha256(skill_content.encode()).hexdigest()[:12]
        console.print(f"llms.txt: {source} ({content_hash})")

    # Versions
    import vera_bench

    bench_ver = vera_bench.__version__

    # Create clients
    client = create_client(model)
    vera = VeraRunner() if language == "vera" else None
    vera_ver = vera.version() if vera else ""

    # Get Aver version if running Aver
    aver_ver = ""
    if language == "aver":
        import subprocess as _sp

        try:
            _av_proc = _sp.run(  # noqa: S603
                ["aver", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if _av_proc.returncode != 0:
                console.print(
                    "[red]Error: aver --version failed "
                    f"(exit {_av_proc.returncode}). "
                    "Check your aver installation.[/red]"
                )
                raise SystemExit(1)
            aver_ver = _av_proc.stdout.strip().replace("aver ", "")
        except (FileNotFoundError, _sp.TimeoutExpired):
            console.print(
                "[red]Error: aver not found on PATH. "
                "Install with: cargo install aver-lang[/red]"
            )
            raise SystemExit(1)

    # Set up output — dots to hyphens in versions for clean filenames
    def _ver_slug(v: str) -> str:
        return v.replace(".", "-")

    if output_dir is None:
        output_dir = root / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    parts = [model.replace("/", "-")]
    if language != "vera":
        parts.append(language)
    if language == "vera" and mode != "full-spec":
        parts.append(mode)
    parts.append(f"bench-{_ver_slug(bench_ver)}")
    if vera_ver and vera_ver != "unknown":
        parts.append(f"vera-{_ver_slug(vera_ver)}")
    if aver_ver and aver_ver != "unknown":
        parts.append(f"aver-{_ver_slug(aver_ver)}")
    output_path = output_dir / f"{'-'.join(parts)}.jsonl"

    # Truncate stale results from previous runs
    if output_path.exists():
        output_path.unlink()

    console.print(f"Model:    {model}")
    console.print(f"Language: {language}")
    console.print(f"Mode:     {mode}")
    console.print(f"Bench:    v{bench_ver}")
    if aver_ver:
        console.print(f"Aver:     v{aver_ver}")
    if vera_ver:
        console.print(f"Vera:     v{vera_ver}")
    console.print(f"Output:   {output_path}\n")

    # Run benchmark
    results = run_benchmark(
        problems=problems,
        client=client,
        skill_md=skill_content,
        vera=vera,
        mode=mode,
        language=language,
        output_path=output_path,
        max_tokens=max_tokens,
        keep_temps=keep_temps,
        bench_version=bench_ver,
        vera_version=vera_ver,
    )

    # Print summary
    if results:
        metrics = compute_metrics([json.loads(r.to_jsonl()) for r in results])
        _print_metrics(model, metrics, language=language)

    console.print(f"\nResults written to {output_path}")


def _fmt_rate(rate: float | None) -> str:
    if rate is None:
        return "-"
    return f"{rate * 100:.0f}%"


def _print_metrics(model: str, metrics, language: str = "vera") -> None:
    """Print a summary metrics table."""
    table = Table(title=f"Results: {model}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Problems", str(metrics.total_problems))
    table.add_row("check@1", _fmt_rate(metrics.check_rate))
    if language in ("vera", "aver"):
        table.add_row("verify@1", _fmt_rate(metrics.verify_rate))
        table.add_row("fix@1", _fmt_rate(metrics.fix_rate))
    table.add_row("run_correct", _fmt_rate(metrics.run_correct_rate))

    if metrics.by_tier:
        table.add_section()
        for t in sorted(metrics.by_tier):
            tm = metrics.by_tier[t]
            table.add_row(
                f"Tier {t} check@1",
                f"{_fmt_rate(tm.check_rate)} ({tm.count})",
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


@main.command()
@click.option(
    "--language",
    type=click.Choice(["python", "typescript", "aver"]),
    default="python",
    help="Baseline language to run",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
)
def baselines(language: str, output_dir: Path | None):
    """Run baseline solutions against test cases."""
    from vera_bench.baseline_runner import run_all_baselines
    from vera_bench.metrics import compute_metrics

    root = _repo_root()

    # Load all problems
    problems_dir = root / "problems"
    problem_files = sorted(problems_dir.rglob("VB_*.json"))
    problems = []
    for pf in problem_files:
        with open(pf, encoding="utf-8") as f:
            problems.append(json.load(f))

    console.print(f"Found {len(problems)} problems.\n")

    # Set up output
    solutions_dir = root / "solutions"
    if output_dir is None:
        output_dir = root / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{language}-baseline.jsonl"

    # Truncate stale results from previous runs
    if output_path.exists():
        output_path.unlink()

    # Fail fast if aver is not on PATH
    if language == "aver":
        import shutil as _shutil

        if _shutil.which("aver") is None:
            console.print(
                "[red]Error: aver not found on PATH. "
                "Install with: cargo install aver-lang[/red]"
            )
            raise SystemExit(1)

    console.print(f"Language: {language}")
    console.print(f"Output:   {output_path}\n")

    # Run baselines
    results = run_all_baselines(
        problems=problems,
        solutions_dir=solutions_dir,
        output_path=output_path,
        language=language,
    )

    # Print summary
    if results:
        metrics = compute_metrics([json.loads(r.to_jsonl()) for r in results])
        _print_metrics(f"{language}-baseline", metrics, language=language)

    console.print(f"\nResults written to {output_path}")
