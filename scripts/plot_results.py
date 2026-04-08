#!/usr/bin/env python3
"""Generate benchmark comparison charts from VeraBench results."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

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
}

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

# --- Official report data (v0.0.7, vera 0.0.108) ---

FLAGSHIP = {
    "Claude Opus 4": {"Vera": 88, "Vera NL": 79, "Python": 96, "TypeScript": 96},
    "GPT-4.1": {"Vera": 91, "Vera NL": 50, "Python": 96, "TypeScript": 96},
    "Kimi K2.5": {"Vera": 100, "Vera NL": 100, "Python": 86, "TypeScript": 91},
}

SONNET = {
    "Claude Sonnet 4": {"Vera": 79, "Vera NL": 79, "Python": 96, "TypeScript": 88},
    "GPT-4o": {"Vera": 78, "Vera NL": 76, "Python": 93, "TypeScript": 83},
    "Kimi K2 Turbo": {"Vera": 83, "Vera NL": 77, "Python": 88, "TypeScript": 79},
}


def _style_ax(ax):
    """Apply site styling to an axes."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(BROWN_300)
    ax.spines["left"].set_color(BROWN_300)
    ax.tick_params(colors=BROWN_500)


def plot_tier(ax, data: dict, title: str):
    models = list(data.keys())
    languages = ["Vera", "Python", "TypeScript"]
    x = np.arange(len(models))
    width = 0.25

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
    ax.set_xticks(x + width)
    ax.set_xticklabels(models, fontsize=10)
    ax.set_ylim(0, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.5, alpha=0.3)
    _style_ax(ax)
    ax.legend(loc="lower left", fontsize=9, framealpha=0.8, edgecolor=BROWN_300)


def plot_vera_vs_both(ax, flagship: dict, sonnet: dict):
    """Show deltas: Vera minus Python and Vera minus TypeScript per model."""
    all_data = {**flagship, **sonnet}
    models = list(all_data.keys())
    delta_py = [all_data[m]["Vera"] - all_data[m]["Python"] for m in models]
    delta_ts = [all_data[m]["Vera"] - all_data[m]["TypeScript"] for m in models]

    y = np.arange(len(models))
    height = 0.35

    colors_py = [GREEN if d >= 0 else RED for d in delta_py]
    bars_py = ax.barh(
        y - height / 2,
        delta_py,
        height,
        color=colors_py,
        edgecolor=CREAM,
        linewidth=0.5,
        label="vs Python",
        alpha=0.85,
    )
    colors_ts = [GREEN if d >= 0 else RED for d in delta_ts]
    bars_ts = ax.barh(
        y + height / 2,
        delta_ts,
        height,
        color=colors_ts,
        edgecolor=CREAM,
        linewidth=0.5,
        label="vs TypeScript",
        alpha=0.55,
        hatch="//",
    )

    for bar, val in zip(bars_py, delta_py):
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
    for bar, val in zip(bars_ts, delta_ts):
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
        "Vera run_correct minus traditional language (pp)", fontsize=10, color=BROWN_500
    )
    ax.set_title(
        "Does Vera beat Python / TypeScript?",
        fontsize=13,
        fontweight="bold",
        pad=12,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    _style_ax(ax)
    ax.set_xlim(-22, 22)
    ax.invert_yaxis()
    ax.legend(loc="lower right", fontsize=9, framealpha=0.8, edgecolor=BROWN_300)


def plot_all_modes(ax, flagship: dict, sonnet: dict):
    """Grouped comparison: all 4 modes for each model."""
    all_data = {**flagship, **sonnet}
    models = list(all_data.keys())
    modes = ["Vera", "Vera NL", "Python", "TypeScript"]
    x = np.arange(len(models))
    width = 0.2

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
    ax.set_xticks(x + 1.5 * width)
    ax.set_xticklabels(models, fontsize=8, rotation=15, ha="right")
    ax.set_ylim(0, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.5, alpha=0.3)
    _style_ax(ax)
    ax.legend(loc="lower left", fontsize=8, ncol=2, framealpha=0.8, edgecolor=BROWN_300)


def main():
    fig = plt.figure(figsize=(16, 18))
    fig.suptitle(
        "VeraBench v0.0.7 \u2014 Vera v0.0.108\n"
        "50 problems \u00d7 6 models \u00d7 4 modes",
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
    plot_tier(ax1, FLAGSHIP, "Flagship Tier \u2014 run_correct")

    ax2 = fig.add_subplot(gs[0, 1])
    plot_tier(ax2, SONNET, "Sonnet Tier \u2014 run_correct")

    # Row 2: delta chart
    ax3 = fig.add_subplot(gs[1, :])
    plot_vera_vs_both(ax3, FLAGSHIP, SONNET)

    # Row 3: all modes
    ax4 = fig.add_subplot(gs[2, :])
    plot_all_modes(ax4, FLAGSHIP, SONNET)

    # Row 4: footer — explanation (left 3/4) + branding (right 1/4)
    # Footer spans full width
    ax_footer = fig.add_subplot(gs[3, :])
    ax_footer.axis("off")

    explanation = (
        "Vera (full-spec):  The model receives the complete Vera\n"
        "type signature and contracts (requires/ensures/effects)\n"
        "in the prompt. It only needs to write the function body."
        "\n\n"
        "Vera (spec-from-NL):  The model receives only a natural\n"
        "language description. It must infer the contracts itself,\n"
        "then write the code. This tests whether the model\n"
        "understands Vera\u2019s type system well enough to author\n"
        "correct specifications from scratch."
    )
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

    out = "assets/benchmark_v0.0.7.png"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, facecolor="white")
    print(f"Saved: {out}")
    plt.close()


if __name__ == "__main__":
    main()
