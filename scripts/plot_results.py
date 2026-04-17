#!/usr/bin/env python3
"""Generate benchmark comparison charts from VeraBench results.

Reads JSONL files in `results/` (via `vera_bench.metrics.compute_metrics`)
and produces a run_correct comparison chart. The canonical committed chart
is `assets/results-graph.png`; variant suffixes (`_v{VERSION}`,
`_with-{lang}`) are gitignored.

Usage:
    python scripts/plot_results.py
        # -> assets/results-graph.png (pyproject version)
    python scripts/plot_results.py --version 0.0.7
        # -> assets/results-graph_v0.0.7.png (historical snapshot)
    python scripts/plot_results.py --extra aver
        # -> assets/results-graph_with-aver.png (include Aver)
    python scripts/plot_results.py --output my.png
        # -> my.png (explicit path)

To add a new model, append it to MODELS below. File naming follows the
convention described in scripts/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# Allow importing vera_bench without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vera_bench.metrics import compute_metrics  # noqa: E402

# --- Site palette (from veralang.dev) ---
CREAM = "#FEEAD1"
BROWN_900 = "#1A0B00"
BROWN_700 = "#421C00"
BROWN_500 = "#5E2C08"
BROWN_300 = "#975526"
ORANGE_400 = "#E05600"
GREEN = "#1A7F45"
RED = "#C0392B"

COLORS = {
    "Vera": GREEN,
    "Vera NL": "#52b788",
    "Python": ORANGE_400,
    "TypeScript": BROWN_300,
    "Aver": "#6B4FBB",  # indigo — visually distinct from the Vera greens
}

# Neutral grey shades for the delta-chart legend (not per-language green/red).
_DELTA_LEGEND_SHADES = ["#888888", "#aaaaaa", "#cccccc"]
_DELTA_HATCHES = [None, "//", ".."]
_DELTA_ALPHAS = [0.85, 0.55, 0.40]

# --- Fonts (veralang.dev: Inter, DM Serif Display, JetBrains Mono) ---
FONT_BODY = "Inter UI"
FONT_HEADING = "Georgia"  # fallback for DM Serif Display

matplotlib.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [FONT_BODY, "Inter", "Helvetica", "Arial"],
        "font.size": 11,
        "text.color": BROWN_700,
        "axes.labelcolor": BROWN_500,
        "xtick.color": BROWN_500,
        "ytick.color": BROWN_500,
    }
)

# --- Model registry ------------------------------------------------------
# file_prefix is the model-id portion of the result-file name. To find the
# file for any mode, we glob for "<file_prefix>-<mode_marker>bench-<ver>*.jsonl"
# (see MODE_PATTERNS below).


@dataclass(frozen=True)
class ModelSpec:
    display: str  # Shown on the chart (e.g. "Claude Opus 4")
    file_prefix: str  # Model-id portion of result filename
    tier: str  # "flagship" or "sonnet" — controls chart layout


MODELS: list[ModelSpec] = [
    # Flagship row
    ModelSpec("Claude Opus 4", "claude-opus-4-20250514", "flagship"),
    ModelSpec("GPT-4.1", "gpt-4.1-2025-04-14", "flagship"),
    ModelSpec("Kimi K2.5", "moonshot-kimi-k2.5", "flagship"),
    # Sonnet row
    ModelSpec("Claude Sonnet 4", "claude-sonnet-4-20250514", "sonnet"),
    ModelSpec("GPT-4o", "gpt-4o", "sonnet"),
    ModelSpec("Kimi K2 Turbo", "moonshot-kimi-k2-turbo-preview", "sonnet"),
]

# Mode label -> glob pattern fragment inserted between prefix and bench-VER.
# An empty fragment means the mode is the Vera full-spec "default" file.
# Vera-based modes have a trailing "-vera-{compiler}" suffix in the filename;
# other languages do not (see _find_result_file).
MODE_PATTERNS: dict[str, str] = {
    "Vera": "",  # {prefix}-bench-{v}-vera-*.jsonl
    "Vera NL": "spec-from-nl-",  # {prefix}-spec-from-nl-bench-{v}-vera-*.jsonl
    "Python": "python-",  # {prefix}-python-bench-{v}.jsonl
    "TypeScript": "typescript-",  # {prefix}-typescript-bench-{v}.jsonl
    "Aver": "aver-",  # {prefix}-aver-bench-{v}-aver-*.jsonl
}

# Modes that have a trailing "-vera-{compiler}" or "-aver-{compiler}" suffix.
_COMPILER_SUFFIXED = {"Vera": "vera", "Vera NL": "vera", "Aver": "aver"}

# Default chart: Python + TypeScript as comparison languages. Opt in to Aver
# (or future languages) via --extra.
DEFAULT_COMPARISON_MODES = ["Python", "TypeScript"]
OPTIONAL_COMPARISON_MODES = {"aver": "Aver"}


def _version_to_filename(version: str) -> str:
    """Convert '0.0.9' -> '0-0-9' for filename matching."""
    return version.replace(".", "-")


def _find_result_file(
    results_dir: Path, model: ModelSpec, mode: str, version: str
) -> Path | None:
    """Locate the JSONL file for a given model × mode × bench-version.

    Returns the most recently modified match, or None if no file exists.
    """
    fragment = MODE_PATTERNS[mode]
    ver = _version_to_filename(version)
    compiler_tag = _COMPILER_SUFFIXED.get(mode)
    if compiler_tag:
        pattern = f"{model.file_prefix}-{fragment}bench-{ver}-{compiler_tag}-*.jsonl"
    else:
        pattern = f"{model.file_prefix}-{fragment}bench-{ver}.jsonl"

    matches = sorted(
        results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return matches[0] if matches else None


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def extract_data(
    results_dir: Path, version: str, modes: list[str]
) -> tuple[dict, dict, list[str], list[Path]]:
    """Extract run_correct percentages for every MODEL × MODE.

    Args:
        results_dir: Directory containing JSONL result files.
        version: Bench version (e.g. "0.0.9").
        modes: Mode labels to extract, in display order. Must be keys in
            MODE_PATTERNS.

    Returns (flagship, sonnet, warnings, used_paths).
    flagship/sonnet: dict[display_name] -> dict[mode_label] -> int percentage
    warnings: human-readable list of missing files.
    used_paths: the actual JSONL files consulted (one per successful lookup).
        Downstream code should derive subtitle metadata (compiler version,
        problem count) from this list rather than re-globbing — re-globbing
        can pick up stale files that _find_result_file's mtime tie-breaker
        would have rejected.
    """
    flagship: dict[str, dict[str, int]] = {}
    sonnet: dict[str, dict[str, int]] = {}
    warnings: list[str] = []
    used_paths: list[Path] = []

    for model in MODELS:
        row: dict[str, int] = {}
        for mode in modes:
            path = _find_result_file(results_dir, model, mode, version)
            if path is None:
                warnings.append(
                    f"  {model.display} / {mode}: no file matching bench-{version}"
                )
                row[mode] = 0
                continue
            used_paths.append(path)
            metrics = compute_metrics(_load_jsonl(path))
            rate = metrics.run_correct_rate or 0.0
            row[mode] = round(rate * 100)

        (flagship if model.tier == "flagship" else sonnet)[model.display] = row

    return flagship, sonnet, warnings, used_paths


def _style_ax(ax):
    """Apply site styling to an axes."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(BROWN_300)
    ax.spines["left"].set_color(BROWN_300)
    ax.tick_params(colors=BROWN_500)


def plot_tier(ax, data: dict, title: str, comparison_modes: list[str]):
    """Grouped bars: Vera vs. each comparison language, per model."""
    models = list(data.keys())
    languages = ["Vera", *comparison_modes]
    x = np.arange(len(models))
    width = 0.8 / len(languages)

    for i, lang in enumerate(languages):
        values = [data[m][lang] for m in models]
        bars = ax.bar(
            x + i * width,
            values,
            width,
            label=lang,
            color=COLORS[lang],
            edgecolor=CREAM,
            linewidth=0.5,
        )
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                f"{val}%",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.set_ylabel("run_correct (%)", fontsize=10, color=BROWN_500)
    ax.set_title(
        title,
        fontsize=13,
        fontweight="bold",
        pad=12,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.set_xticks(x + width * (len(languages) - 1) / 2)
    ax.set_xticklabels(models, fontsize=10)
    ax.set_ylim(0, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.5, alpha=0.3)
    _style_ax(ax)
    ax.legend(loc="lower left", fontsize=9, framealpha=0.8, edgecolor=BROWN_300)


def plot_vera_vs_comparison(
    ax, flagship: dict, sonnet: dict, comparison_modes: list[str]
):
    """Horizontal bars: Vera run_correct minus each comparison language, per model."""
    from matplotlib.patches import Patch  # noqa: E402

    all_data = {**flagship, **sonnet}
    models = list(all_data.keys())

    # Per-comparison delta arrays and bar objects (one row per mode).
    deltas = {
        mode: [all_data[m]["Vera"] - all_data[m][mode] for m in models]
        for mode in comparison_modes
    }

    y = np.arange(len(models))
    n = len(comparison_modes)
    height = 0.7 / n  # fit n bars inside a row

    # Center the stack of bars on each model's tick.
    offsets = [(i - (n - 1) / 2) * height for i in range(n)]

    for i, mode in enumerate(comparison_modes):
        d = deltas[mode]
        colors = [GREEN if v >= 0 else RED for v in d]
        hatch = _DELTA_HATCHES[i % len(_DELTA_HATCHES)]
        alpha = _DELTA_ALPHAS[i % len(_DELTA_ALPHAS)]
        bars = ax.barh(
            y + offsets[i],
            d,
            height,
            color=colors,
            edgecolor=CREAM,
            linewidth=0.5,
            alpha=alpha,
            hatch=hatch,
        )
        for bar, val in zip(bars, d):
            xpos = val + (1 if val >= 0 else -1)
            ha = "left" if val >= 0 else "right"
            sign = "+" if val > 0 else ""
            ax.text(
                xpos,
                bar.get_y() + bar.get_height() / 2,
                f"{sign}{val}",
                ha=ha,
                va="center",
                fontsize=9,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.axvline(x=0, color=BROWN_900, linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(models, fontsize=10)
    ax.set_xlabel(
        "Vera run_correct minus comparison language (pp)",
        fontsize=10,
        color=BROWN_500,
    )
    title = "Does Vera beat " + " / ".join(comparison_modes) + "?"
    ax.set_title(
        title,
        fontsize=13,
        fontweight="bold",
        pad=12,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    _style_ax(ax)
    # Dynamic x-axis: leave at least ±22 points of headroom; expand for
    # larger deltas.
    max_abs = max(
        (abs(v) for mode in comparison_modes for v in deltas[mode]), default=0
    )
    limit = max(22, max_abs + 4)
    ax.set_xlim(-limit, limit)
    ax.invert_yaxis()

    # Neutral grey legend swatches (not red/green — avoids conflating
    # positive/negative colours with per-mode identity).
    legend_handles = [
        Patch(
            facecolor=_DELTA_LEGEND_SHADES[i % len(_DELTA_LEGEND_SHADES)],
            edgecolor=CREAM,
            alpha=_DELTA_ALPHAS[i % len(_DELTA_ALPHAS)],
            hatch=_DELTA_HATCHES[i % len(_DELTA_HATCHES)],
            label=f"vs {mode}",
        )
        for i, mode in enumerate(comparison_modes)
    ]
    ax.legend(
        handles=legend_handles,
        loc="lower right",
        fontsize=9,
        framealpha=0.8,
        edgecolor=BROWN_300,
    )


# Backwards-compatible alias for the v0.0.7 name (in case anyone imports it).
plot_vera_vs_both = plot_vera_vs_comparison


def plot_all_modes(ax, flagship: dict, sonnet: dict, modes: list[str]):
    """Grouped comparison: all modes (Vera + Vera NL + comparisons) per model."""
    all_data = {**flagship, **sonnet}
    models = list(all_data.keys())
    x = np.arange(len(models))
    width = 0.8 / len(modes)

    for i, mode in enumerate(modes):
        values = [all_data[m][mode] for m in models]
        bars = ax.bar(
            x + i * width,
            values,
            width,
            label=mode,
            color=COLORS[mode],
            edgecolor=CREAM,
            linewidth=0.5,
        )
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                f"{val}",
                ha="center",
                va="bottom",
                fontsize=7,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.set_ylabel("run_correct (%)", fontsize=10, color=BROWN_500)
    ax.set_title(
        "All Models \u00d7 All Modes",
        fontsize=13,
        fontweight="bold",
        pad=12,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.set_xticks(x + width * (len(modes) - 1) / 2)
    ax.set_xticklabels(models, fontsize=8, rotation=15, ha="right")
    ax.set_ylim(0, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.5, alpha=0.3)
    _style_ax(ax)
    ax.legend(loc="lower left", fontsize=8, ncol=2, framealpha=0.8, edgecolor=BROWN_300)


def _detect_vera_version(used_paths: list[Path]) -> str:
    """Return the most common Vera compiler version among the files plotted.

    Operates on the Path list returned by extract_data() so the subtitle
    reflects the files the chart actually uses, not whatever else happens to
    match the glob in results/.
    """
    from collections import Counter

    counter: Counter[str] = Counter()
    for path in used_paths:
        # Only Vera-mode files have a "-vera-X-Y-Z" suffix we can parse.
        stem = path.stem
        if "-vera-" not in stem:
            continue
        tail = stem.rsplit("-vera-", 1)[-1]
        counter[tail.replace("-", ".")] += 1
    return counter.most_common(1)[0][0] if counter else "?"


def _detect_problem_count(used_paths: list[Path]) -> int:
    """Infer the problem set size from the actual files plotted.

    Returns the max unique problem_id count across the used files. Operating
    on used_paths (rather than re-globbing) ensures consistency with the
    files _find_result_file() actually selected.
    """
    counts = []
    for path in used_paths:
        ids = {json.loads(line)["problem_id"] for line in path.read_text().splitlines()}
        counts.append(len(ids))
    return max(counts) if counts else 0


def _default_version() -> str:
    """Pull the bench version from pyproject.toml via tomllib (stdlib 3.11+)."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return "0.0.0"
    # PEP 621 (canonical for this project) first; fall back to poetry-style.
    version = data.get("project", {}).get("version")
    if not version:
        version = data.get("tool", {}).get("poetry", {}).get("version")
    return version or "0.0.0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=_default_version(),
        help="Bench version to plot (default: pyproject.toml)",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Directory containing JSONL result files",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output PNG path "
            "(default: assets/results-graph[_v{version}][_with-{extras}].png)"
        ),
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        choices=sorted(OPTIONAL_COMPARISON_MODES),
        help=(
            "Additional comparison language to include in the chart "
            "(repeat for multiple; default: none, i.e. Python + TypeScript only)"
        ),
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    version = args.version
    current_version = _default_version()
    extras = [OPTIONAL_COMPARISON_MODES[k] for k in args.extra]

    comparison_modes = [*DEFAULT_COMPARISON_MODES, *extras]
    all_modes = ["Vera", "Vera NL", *comparison_modes]

    # Default canonical filename: assets/results-graph.png. Any variant
    # (historical version, optional comparison language) gets a suffix —
    # `assets/results-graph_*` is gitignored so only the canonical chart
    # is committed.
    if args.output:
        out = args.output
    else:
        suffixes = []
        if version != current_version:
            suffixes.append(f"_v{version}")
        if args.extra:
            suffixes.append("_with-" + "-".join(args.extra))
        out = f"assets/results-graph{''.join(suffixes)}.png"

    flagship, sonnet, warnings, used_paths = extract_data(
        results_dir, version, all_modes
    )
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(w)

    vera_version = _detect_vera_version(used_paths)
    problem_count = _detect_problem_count(used_paths)
    subtitle = (
        f"{problem_count} problems \u00d7 {len(MODELS)} models "
        f"\u00d7 {len(all_modes)} modes"
    )

    fig = plt.figure(figsize=(16, 18))
    fig.suptitle(
        f"VeraBench v{version} \u2014 Vera v{vera_version}\n{subtitle}",
        fontsize=16,
        fontweight="bold",
        y=0.98,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )

    gs = fig.add_gridspec(
        4,
        2,
        hspace=0.35,
        wspace=0.3,
        height_ratios=[1, 1, 1, 0.3],
        left=0.10,
        right=0.95,
        top=0.92,
        bottom=0.04,
    )

    # Row 1: tier comparisons
    ax1 = fig.add_subplot(gs[0, 0])
    plot_tier(ax1, flagship, "Flagship Tier \u2014 run_correct", comparison_modes)

    ax2 = fig.add_subplot(gs[0, 1])
    plot_tier(ax2, sonnet, "Sonnet Tier \u2014 run_correct", comparison_modes)

    # Row 2: delta chart
    ax3 = fig.add_subplot(gs[1, :])
    plot_vera_vs_comparison(ax3, flagship, sonnet, comparison_modes)

    # Row 3: all modes
    ax4 = fig.add_subplot(gs[2, :])
    plot_all_modes(ax4, flagship, sonnet, all_modes)

    # Row 4: footer — explanation (left 3/4) + branding (right 1/4)
    # Footer spans full width
    ax_footer = fig.add_subplot(gs[3, :])
    ax_footer.axis("off")

    # fmt: off
    explanation = (
        "Vera (full-spec):  The model receives the complete Vera type signature and contracts (requires/ensures/effects) in the\n"  # noqa: E501
        "prompt. It only needs to write the function body.\n"
        "\n"
        "Vera (spec-from-NL):  The model receives only a natural language description. It must infer the contracts itself, then\n"  # noqa: E501
        "write the code. This tests whether the model understands Vera\u2019s type system well enough to author correct specifications\n"  # noqa: E501
        "from scratch."
    )
    # fmt: on
    ax_footer.text(
        0.0,
        0.95,
        explanation,
        transform=ax_footer.transAxes,
        fontsize=13,
        color=BROWN_500,
        va="top",
        ha="left",
        linespacing=1.6,
    )

    ax_footer.text(
        1.0,
        0.95,
        "VeraBench",
        transform=ax_footer.transAxes,
        fontsize=20,
        fontweight="bold",
        color=BROWN_900,
        va="top",
        ha="right",
        fontfamily=FONT_HEADING,
    )
    ax_footer.text(
        1.0,
        0.58,
        "veralang.dev",
        transform=ax_footer.transAxes,
        fontsize=11,
        color=ORANGE_400,
        va="top",
        ha="right",
        fontweight="bold",
    )
    ax_footer.text(
        1.0,
        0.30,
        "github.com/aallan/vera\ngithub.com/aallan/vera-bench",
        transform=ax_footer.transAxes,
        fontsize=9,
        color=BROWN_300,
        va="top",
        ha="right",
        linespacing=1.6,
    )

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, facecolor="white")
    print(f"Saved: {out}")
    plt.close()


if __name__ == "__main__":
    main()
