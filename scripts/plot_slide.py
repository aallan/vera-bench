#!/usr/bin/env python3
"""Render benchmark result panels as 16:9 slides for talk presentation.

Five slide types are supported:

- `delta`     — the "Does Vera beat Python / TypeScript?" horizontal-bar chart
                (the headline storytelling slide; Vera-wins read as green
                positive bars).
- `tiers`     — per-tier comparison panels side-by-side (2 panels for the
                historical 2-tier data, 3 for the fable/opus/sonnet matrix),
                mirroring the top row of the documentation chart.
- `all-modes` — every model × the 4 core modes (Vera, Vera NL, Python,
                TypeScript) in a single grouped-bar panel.
- `ztd`       — the zero-training-data slide: Vera vs Aver vs AILANG on the
                subset of models that ran the ZTD generation targets. Needs
                Aver/AILANG result files, so it's opt-in (--type ztd), not
                part of --type all.
- `reasoning` — one model at two reasoning budgets (REASONING_PAIR) across
                every core mode, per-language delta annotated. The
                controlled comparison: both entries are the SAME model, so
                deliberation is the only variable — if Vera's delta is ~0
                while comparison languages gain, the language is supplying
                structure the reasoning budget otherwise reconstructs.
                Opt-in; needs both halves of the pair.

Standalone script — not part of the documentation chart-generation flow in
`plot_results.py`. Slide rendering has different typography and layout
requirements (slide-readable from the back of a room, single panel or
side-by-side per figure, landscape aspect) that don't belong in the README
artefact. Reuses palette + data extraction from `plot_results.py` so the
slide numbers match the README chart by construction.

Version handling: `--version 0.0.7` renders against the frozen
MODELS_V_0_0_7 lineup (what was actually run in v0.0.7 — the live
registry has moved on); any other version renders against the live
`plot_results.MODELS` matrix.

Usage:
    # Render the base trio (delta, tiers, all-modes)
    python scripts/plot_slide.py --version 0.0.16

    # One at a time
    python scripts/plot_slide.py --version 0.0.16 --type delta
    python scripts/plot_slide.py --version 0.0.16 --type ztd

    # The historical v0.0.7 talk slides still render identically
    python scripts/plot_slide.py --version 0.0.7

    # Custom output path (only with single --type)
    python scripts/plot_slide.py --type delta --output ~/Desktop/slide-3.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import ModuleType

# Guarded for the same reason as plot_results: the test job imports this
# module for its data helpers and constants, and must not need a plotting
# backend to do it. main() calls _require_mpl() before drawing anything.
# Annotations are lazy (`from __future__ import annotations`), so `Axes`
# being None does not break the signatures that mention it.
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402
    import numpy as np  # noqa: E402
    from matplotlib.axes import Axes  # noqa: E402
    from matplotlib.patches import Patch  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - only where matplotlib absent
    matplotlib = plt = np = None
    Axes = Patch = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.plot_results import (  # noqa: E402
    BROWN_300,
    BROWN_500,
    BROWN_700,
    BROWN_900,
    COLORS,
    CREAM,
    FONT_BODY,
    FONT_HEADING,
    GREEN,
    LANG_HATCH,
    RED,
    ZERO_STUB,
    ZTD_DISPLAYS,
    ModelSpec,
    _require_mpl,
    complete_models,
    extract_data,
)

# v0.0.7 historical lineup. Kept locally rather than imported from
# plot_results.MODELS because the live registry has since been updated
# (K2.6 in flagship, K2.5 in sonnet) — but the v0.0.7 chart needs the
# v0.0.7-era assignments to match the result files we're plotting.
MODELS_V_0_0_7: list[ModelSpec] = [
    ModelSpec("Claude Opus 4", "claude-opus-4-20250514", "flagship"),
    ModelSpec("GPT-4.1", "gpt-4.1-2025-04-14", "flagship"),
    ModelSpec("Kimi K2.5", "moonshot-kimi-k2.5", "flagship"),
    ModelSpec("Claude Sonnet 4", "claude-sonnet-4-20250514", "sonnet"),
    ModelSpec("GPT-4o", "gpt-4o", "sonnet"),
    ModelSpec("Kimi K2 Turbo", "moonshot-kimi-k2-turbo-preview", "sonnet"),
]

# Slide typography. Roughly 3× the README-chart sizes so the slide reads
# from the back of a room. Tier and all-modes panels use slightly smaller
# tick labels because they have more bars to label per panel.
TITLE_PT = 36
SUBTITLE_PT = 22
AXIS_LABEL_PT = 22
TICK_PT_LARGE = 22  # delta chart — 6 model rows
TICK_PT_MEDIUM = 20  # tier panels — 3 models per panel
TICK_PT_SMALL = 18  # all-modes — 6 models in one panel
BAR_LABEL_PT_LARGE = 22
BAR_LABEL_PT_MEDIUM = 18
BAR_LABEL_PT_SMALL = 14
BAR_LABEL_PT_DENSE = 16  # delta chart past six model rows
LEGEND_PT = 20

# Slide background choices. All are light-theme variants — the text/spine
# colors inherited from plot_results.py (BROWN_*) work cleanly on any of
# these. A dark-mode background is not offered here because it would
# require cascading text-color inversion that's out of scope for the
# current talk's design language.
BACKGROUNDS = {
    "paper": "#FAF7F0",  # off-white — chosen default; soft, neutral
    "white": "#FFFFFF",  # pure white — high contrast, baseline
    "cream": "#FEEAD1",  # on-brand (veralang.dev palette)
    "light-grey": "#F4F4F2",  # neutral grey
    # None means no fill at all. Used for figures embedded in a page
    # that already has its own background (the README, veralang.dev),
    # where a baked-in panel colour reads as a floating card.
    "transparent": None,
}
DEFAULT_BACKGROUND = "paper"

# When true, renderers draw the plot and nothing else: no title, no
# subtitle, no footnote. The surrounding prose carries those instead.
BARE = False


def _patch_models_for_slide() -> tuple[ModuleType, list[ModelSpec]]:
    """Temporarily swap plot_results.MODELS for the v0.0.7 lineup.

    extract_data() reads from the module-level MODELS in plot_results,
    so we patch it for the duration of the data load. Restored on exit.
    """
    import scripts.plot_results as pr

    original = pr.MODELS
    pr.MODELS = MODELS_V_0_0_7
    return pr, original


def _load_data(
    version: str, results_dir: Path, modes: list[str]
) -> tuple[dict[str, dict[str, dict[str, int]]], set[tuple[str, str]]]:
    """Load slide data as extract_data's tier dict, plus the missing set.

    For version 0.0.7 the historical MODELS_V_0_0_7 lineup is patched
    in (the frozen talk lineup — labels would silently mis-map against
    the live registry). Any other version uses plot_results.MODELS
    as-is, so slides track the current matrix.
    """
    if version == "0.0.7":
        pr, original = _patch_models_for_slide()
        try:
            tiers, warnings, _used, missing = extract_data(results_dir, version, modes)
        finally:
            pr.MODELS = original
    else:
        tiers, warnings, _used, missing = extract_data(results_dir, version, modes)

    if warnings:
        print("Warnings:")
        for w in warnings:
            print(w)

    return tiers, missing


def _merge_tiers(tiers: dict[str, dict]) -> dict:
    """Flatten the tier dict into display_name -> mode rows, tier order."""
    merged: dict = {}
    for tier_data in tiers.values():
        merged.update(tier_data)
    return merged


def _slide_rcparams() -> None:
    """rcParams shared across all slide types."""
    _require_mpl()
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [FONT_BODY, "Inter", "Helvetica", "Arial"],
            "font.size": TICK_PT_LARGE,
            "text.color": BROWN_700,
            "axes.labelcolor": BROWN_500,
            "xtick.color": BROWN_500,
            "ytick.color": BROWN_500,
        }
    )


def _style_ax(ax: Axes) -> None:
    """Light visual frame so the bars carry the eye."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(BROWN_300)
    ax.spines["left"].set_color(BROWN_300)
    ax.tick_params(colors=BROWN_500)


# ----------------------------------------------------------------------
# Delta slide — the storytelling chart
# ----------------------------------------------------------------------


def render_delta(
    tiers: dict[str, dict],
    output: Path,
    background: str = DEFAULT_BACKGROUND,
    missing: set[tuple[str, str]] | None = None,
) -> None:
    """The 'Does Vera beat …?' horizontal-bar chart at 16:9."""
    all_data = _merge_tiers(tiers)
    comparison_modes = ["Python", "TypeScript"]
    # Every bar here is a difference, so a missing file cannot be allowed
    # through: Vera 100 minus an absent Python renders as +100 in Vera's
    # favour — the strongest form of this slide's own claim, manufactured
    # entirely from data that does not exist.
    models = complete_models(all_data, missing, ["Vera", *comparison_modes])
    if not models:
        print("  delta slide: no model ran Vera + all comparisons — skipping")
        return

    deltas = {
        mode: [all_data[m]["Vera"] - all_data[m][mode] for m in models]
        for mode in comparison_modes
    }

    fig, ax = plt.subplots(figsize=(16, 9), dpi=180)

    y = np.arange(len(models))
    n = len(comparison_modes)
    height = 0.7 / n
    offsets = [(i - (n - 1) / 2) * height for i in range(n)]

    hatches = [None, "//"]
    alphas = [0.9, 0.6]
    # The label type was sized for six model rows. At nine the rows are a
    # third shorter, and the two bars of a pair sit close enough that
    # equal deltas ("−6" above "−6") printed on top of one another.
    label_pt = BAR_LABEL_PT_LARGE if len(models) <= 6 else BAR_LABEL_PT_DENSE

    # Needed before drawing, to size the zero stub. Floor lowered from 22
    # (sized for v0.0.7's ±17 spread) so a frontier lineup whose largest
    # delta is 8 does not render as stubs in an empty panel.
    max_abs = max(
        (abs(v) for mode in comparison_modes for v in deltas[mode]),
        default=0,
    )
    limit = max(12, max_abs + 6)
    zero_stub = limit * 0.014

    for i, mode in enumerate(comparison_modes):
        d = deltas[mode]
        colors = [GREEN if v >= 0 else RED for v in d]
        bars = ax.barh(
            y + offsets[i],
            d,
            height,
            color=colors,
            edgecolor=CREAM,
            linewidth=0.8,
            alpha=alphas[i],
            hatch=hatches[i],
        )
        # A tie draws a zero-length bar — nothing at all — leaving its "0"
        # label floating unattached, and indistinguishable from missing
        # data. A neutral stub at the axis gives every row a mark. Grey,
        # not the green/red polarity colours: a tie has no direction.
        for bar, val in zip(bars, d):
            if val == 0:
                ax.barh(
                    bar.get_y() + bar.get_height() / 2,
                    zero_stub,
                    height,
                    # Straddle the axis. Drawn from zero rightwards it reads as a
                    # tiny win for Vera, which is exactly what a tie is not.
                    left=-zero_stub / 2,
                    color=ZERO_STUB,
                    linewidth=0,
                    zorder=5,
                )
        for bar, val in zip(bars, d):
            # Offset in POINTS, not data units — a fixed ±1.2-unit gap is a
            # constant fraction of the axis, so once the x-limit tightened
            # to the data the labels floated out into whitespace rather
            # than sitting at the ends of their bars.
            tip = zero_stub / 2 if val == 0 else val
            sign = "+" if val > 0 else ""
            ax.annotate(
                f"{sign}{val}",
                xy=(tip, bar.get_y() + bar.get_height() / 2),
                xytext=(7 if val >= 0 else -7, 0),
                textcoords="offset points",
                ha="left" if val >= 0 else "right",
                va="center",
                fontsize=label_pt,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.axvline(x=0, color=BROWN_900, linewidth=2)
    ax.set_yticks(y)
    ax.set_yticklabels(models, fontsize=TICK_PT_LARGE)
    ax.set_xlabel(
        # The bars are pass@1 (% solved), not the old run_correct-over-
        # eligible rate this label was written for — that metric shrank
        # its denominator when a model refused, which is exactly what
        # this lineup does.
        "Vera % solved minus comparison language (percentage points)",
        fontsize=AXIS_LABEL_PT,
        color=BROWN_500,
        labelpad=12,
    )
    ax.set_title(
        "Does Vera beat Python / TypeScript?",
        fontsize=TITLE_PT,
        fontweight="bold",
        pad=24,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )

    ax.set_xlim(-limit, limit)
    ax.invert_yaxis()
    ax.tick_params(axis="x", labelsize=TICK_PT_LARGE)

    _style_ax(ax)

    legend_handles = [
        Patch(facecolor="#888888", edgecolor=CREAM, alpha=alphas[0], label="vs Python"),
        Patch(
            facecolor="#aaaaaa",
            edgecolor=CREAM,
            alpha=alphas[1],
            hatch=hatches[1],
            label="vs TypeScript",
        ),
    ]
    ax.legend(
        handles=legend_handles,
        loc="lower right",
        fontsize=LEGEND_PT,
        framealpha=0.85,
        edgecolor=BROWN_300,
    )

    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.95))
    _save(fig, output, background)


# ----------------------------------------------------------------------
# Tier comparison slide — Flagship and Sonnet panels side-by-side
# ----------------------------------------------------------------------


def _draw_tier_panel(
    ax: Axes,
    data: dict,
    title: str,
    comparison_modes: list[str],
    n_panels: int = 2,
) -> None:
    """Grouped vertical bars: Vera vs each comparison language, per model.

    Typography scales with `n_panels`. The constants were chosen for two
    half-width panels; at three the panels are a third of the figure and
    nothing rescaled, so the rightmost title ran off the canvas and the
    model labels collided in every panel. Measured, not guessed: the
    "Sonnet Tier (workhorse)" title spanned to x=2964 on a 2880px figure.
    """
    # 2 panels -> 1.0 (unchanged, so the v0.0.7 slides are byte-stable);
    # 3 panels -> 2/3.
    scale = min(1.0, 2 / n_panels)
    models = list(data.keys())
    # A fourth model in a tier (opus, once Opus 5 landed) crowds the same
    # panel width by another third — shrink again so the labels neither
    # collide nor overrun the panel.
    # Three models already collide: "Claude Sonnet 5" next to
    # "GPT-5.6 Terra" runs together in a panel a third of the canvas wide.
    # Only the two-model fable tier has room for level labels.
    crowded = len(models) >= 3
    crowd_scale = 0.8 if len(models) > 3 else 0.9
    # Drop the per-cent sign from three models up. The y-axis already
    # reads "% solved", and at frontier scores nearly every label is the
    # 4-glyph "100%" — wide enough that neighbouring labels ran together
    # ("100%100%100%") in the sonnet and opus panels alike.
    fmt = "{}" if len(models) >= 3 else "{}%"
    title_pt = round((TITLE_PT - 4) * scale)
    tick_pt = round(TICK_PT_MEDIUM * scale * crowd_scale)
    bar_pt = round(BAR_LABEL_PT_MEDIUM * scale * crowd_scale)
    legend_pt = round(LEGEND_PT * scale)
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
            linewidth=0.8,
            hatch=LANG_HATCH[lang],
        )
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.5,
                fmt.format(val),
                ha="center",
                va="bottom",
                fontsize=bar_pt,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.set_ylabel("% solved", fontsize=round(AXIS_LABEL_PT * scale), color=BROWN_500)
    ax.set_title(
        title,
        fontsize=title_pt,
        fontweight="bold",
        pad=16,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.set_xticks(x + width * (len(languages) - 1) / 2)
    ax.set_xticklabels(
        models,
        fontsize=tick_pt,
        rotation=12 if crowded else 0,
        ha="right" if crowded else "center",
    )
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.tick_params(axis="y", labelsize=tick_pt)
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.8, alpha=0.4)
    _style_ax(ax)
    # Under the panel: at frontier scores every bar reaches the ceiling,
    # so an in-panel legend covers data wherever it is placed.
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16 if crowded else -0.10),
        ncol=len(languages),
        fontsize=round(legend_pt * 0.8),
        framealpha=0.85,
        edgecolor=BROWN_300,
    )


def render_tiers(
    tiers: dict[str, dict],
    output: Path,
    background: str = DEFAULT_BACKGROUND,
    missing: set[tuple[str, str]] | None = None,
) -> None:
    """Per-tier comparison panels side-by-side at 16:9 (2 or 3 tiers)."""
    from scripts.plot_results import TIER_TITLES

    n = max(len(tiers), 1)
    fig, axes = plt.subplots(1, n, figsize=(16, 9), dpi=180)
    if n == 1:
        axes = [axes]
    comparison_modes = ["Python", "TypeScript"]
    for ax, (tier_key, tier_data) in zip(axes, tiers.items()):
        title = TIER_TITLES.get(tier_key, tier_key.title())
        _draw_tier_panel(ax, tier_data, title, comparison_modes, n_panels=n)

    fig.suptitle(
        "% solved by model (Vera vs Python vs TypeScript)",
        fontsize=TITLE_PT - 2,
        fontweight="bold",
        y=0.97,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )

    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.92))
    _save(fig, output, background)


# ----------------------------------------------------------------------
# All-modes slide — 6 models × 4 modes
# ----------------------------------------------------------------------


def render_all_modes(
    tiers: dict[str, dict],
    output: Path,
    background: str = DEFAULT_BACKGROUND,
    missing: set[tuple[str, str]] | None = None,
) -> None:
    """Single panel showing Vera, Vera NL, Python, TypeScript for every model."""
    all_data = _merge_tiers(tiers)
    models = list(all_data.keys())
    modes = ["Vera", "Vera NL", "Python", "TypeScript"]

    fig, ax = plt.subplots(figsize=(16, 9), dpi=180)
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
            linewidth=0.8,
            hatch=LANG_HATCH[mode],
        )
        for bar, val in zip(bars, values):
            # Rotated: 9 models x 4 modes is 36 bars in one panel, and a
            # 3-glyph "100" is wider than the bar it labels. Upright text
            # costs one glyph of width instead of three.
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 2,
                f"{val}",
                ha="center",
                va="bottom",
                rotation=90,
                fontsize=BAR_LABEL_PT_SMALL - 2,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.set_ylabel("% solved", fontsize=AXIS_LABEL_PT, color=BROWN_500)
    ax.set_title(
        "All Models × All Modes",
        fontsize=TITLE_PT,
        fontweight="bold",
        pad=20,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.set_xticks(x + width * (len(modes) - 1) / 2)
    ax.set_xticklabels(models, fontsize=TICK_PT_SMALL, rotation=12, ha="right")
    ax.set_ylim(0, 132)  # headroom for the rotated value labels
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.tick_params(axis="y", labelsize=TICK_PT_SMALL)
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.8, alpha=0.4)
    _style_ax(ax)
    ax.legend(
        loc="lower left",
        fontsize=LEGEND_PT,
        ncol=2,
        framealpha=0.85,
        edgecolor=BROWN_300,
    )

    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.95))
    _save(fig, output, background)


# ----------------------------------------------------------------------
# Plumbing
# ----------------------------------------------------------------------


def _bare_kw() -> dict:
    """Crop to the drawn content once the chrome is gone.

    Removing a title leaves the space it occupied, so a bare figure would
    otherwise carry a band of empty canvas where the heading used to be.
    """
    return {"bbox_inches": "tight", "pad_inches": 0.12} if BARE else {}


def _strip_chrome(fig) -> None:
    """Drop every title, subtitle and footnote, keeping the plot itself.

    Chrome is identified by position rather than by tagging each call
    site: a title or subtitle is drawn in axes coordinates ABOVE the axes
    box, while every data label sits inside it. Figure-level texts are
    chrome by construction here, since the renderers only reach for
    fig.text/suptitle when a caption spans more than one axes.
    """
    for text in list(fig.texts):
        text.remove()
    for ax in fig.axes:
        ax.set_title("")
        for text in list(ax.texts):
            if text.get_transform() is ax.transAxes and text.get_position()[1] > 1.0:
                text.remove()


def _save(fig, output: Path, background: str = DEFAULT_BACKGROUND) -> None:
    """Tint the figure to the chosen background and write the PNG.

    The figure-level patch and every axes facecolor both need setting —
    matplotlib doesn't propagate one to the other, and the savefig
    facecolor kwarg only governs the area *outside* the axes box.
    """
    hex_ = BACKGROUNDS[background]
    output.parent.mkdir(parents=True, exist_ok=True)
    if BARE:
        _strip_chrome(fig)
    if hex_ is None:
        # Both patches have to go: savefig(transparent=True) clears the
        # figure patch but leaves each axes patch opaque.
        fig.patch.set_alpha(0)
        for ax in fig.axes:
            ax.patch.set_alpha(0)
        fig.savefig(output, dpi=180, transparent=True, **_bare_kw())
    else:
        fig.patch.set_facecolor(hex_)
        for ax in fig.axes:
            ax.set_facecolor(hex_)
        fig.savefig(output, dpi=180, facecolor=hex_, **_bare_kw())
    print(f"Saved: {output}  (16×9, bg={background} {hex_ or 'none'})")
    plt.close(fig)


# ----------------------------------------------------------------------
# Zero-training-data slide — Vera vs Aver vs AILANG
# ----------------------------------------------------------------------

# The Aver/AILANG generation targets run on a subset of the matrix.
# Read from the matrix's `ztd` flag, not hand-listed here: the previous
# literal went stale the moment Claude Opus 5 joined the matrix, and the
# slide simply omitted it — no warning, because a shorter lineup is
# indistinguishable from a deliberate one.
ZTD_MODELS = ZTD_DISPLAYS
ZTD_MODES = ["Vera", "Aver", "AILANG"]


def render_ztd(
    tiers: dict[str, dict],
    output: Path,
    background: str = DEFAULT_BACKGROUND,
    missing: set[tuple[str, str]] | None = None,
    ztd_modes: list[str] | None = None,
) -> None:
    """Zero-training-data languages: Vera vs Aver vs AILANG at 16:9.

    The strongest single slide for the language-design thesis: none of
    the three languages appear in any model's training data — every
    percentage point comes from in-context instruction alone.
    """
    all_data = _merge_tiers(tiers)
    absent = missing or set()
    # Which zero-training-data languages to show. Narrowing the set is a
    # real comparison, not a crop: Vera and Aver are the two that drop
    # variable names entirely (Vera via De Bruijn indices, Aver by having
    # no `let`), so a Vera-vs-Aver cut isolates that design choice.
    modes = ztd_modes or ZTD_MODES

    def ran_all_ztd(model: str) -> bool:
        """Did this model actually produce every ZTD result file?

        `extract_data` writes 0 for a missing file, so `mode in row` is
        always true and cannot answer this — an un-run language would
        otherwise be plotted at 0%, which on this slide reads as "the
        language failed catastrophically" rather than "no data". This is
        the ZTD thesis slide; a fabricated zero is the worst possible
        error on it.
        """
        return all((model, mode) not in absent for mode in modes)

    models = [m for m in ZTD_MODELS if m in all_data and ran_all_ztd(m)]
    if not models:
        # Fall back to every model that ran all three — keeps the
        # renderer usable if the subset lineup changes.
        models = [m for m in all_data if ran_all_ztd(m)]
    if not models:
        # Both paths empty. Without this the renderer writes a blank but
        # otherwise well-formed 16:9 PNG — which is worse than an error,
        # because you find out it is empty when it is already on screen.
        print(f"  ztd slide: no model has all of {modes} — skipping")
        return

    fig, ax = plt.subplots(figsize=(16, 9), dpi=180)
    x = np.arange(len(models))
    width = 0.8 / len(modes)

    for i, mode in enumerate(modes):
        values = [all_data[m].get(mode, 0) for m in models]
        bars = ax.bar(
            x + i * width,
            values,
            width,
            label=mode,
            color=COLORS[mode],
            edgecolor=CREAM,
            linewidth=0.8,
            # This slide's two headline series, Vera green and AILANG
            # magenta, sit at ΔE 2.1 under deuteranopia — indistinguishable
            # for a red-green colourblind viewer, which is roughly 1 in 12
            # men in the room. Texture carries the identity that hue cannot.
            hatch=LANG_HATCH[mode],
        )
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.5,
                f"{val}",
                ha="center",
                va="bottom",
                fontsize=BAR_LABEL_PT_MEDIUM,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.set_ylabel("% solved", fontsize=AXIS_LABEL_PT, color=BROWN_500)
    # Short title + subtitle: the single-line form ran off the canvas at
    # 16:9, and matplotlib clips silently rather than shrinking.
    ax.set_title(
        "Zero-training-data languages",
        fontsize=TITLE_PT,
        fontweight="bold",
        pad=44,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.text(
        0.5,
        1.015,
        "none of these appear in any model's training data — every point "
        "comes from in-context instruction alone",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=SUBTITLE_PT,
        color=BROWN_500,
    )
    ax.set_xticks(x + width * (len(modes) - 1) / 2)
    ax.set_xticklabels(models, fontsize=TICK_PT_MEDIUM)
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.tick_params(axis="y", labelsize=TICK_PT_SMALL)
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.8, alpha=0.4)
    _style_ax(ax)
    ax.legend(
        # Under the axes: these bars all reach 92%+, so an in-panel
        # legend covers the leftmost model's data whatever corner it
        # takes.
        loc="upper center",
        bbox_to_anchor=(0.5, -0.09),
        ncol=len(modes),
        fontsize=LEGEND_PT,
        framealpha=0.85,
        edgecolor=BROWN_300,
    )

    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.95))
    _save(fig, output, background)


# ----------------------------------------------------------------------
# Reasoning-budget slide — same model, two reasoning modes
# ----------------------------------------------------------------------

# Display names of a (default, pro) pair from plot_results.MODELS. Both
# entries are the SAME underlying model at different reasoning budgets,
# so the only variable between them is deliberation.
REASONING_PAIR = ("GPT-5.6 Sol", "GPT-5.6 Sol (pro)")
REASONING_MODES = ["Vera", "Vera NL", "Python", "TypeScript"]


def render_reasoning(
    tiers: dict[str, dict],
    output: Path,
    background: str = DEFAULT_BACKGROUND,
    missing: set[tuple[str, str]] | None = None,
) -> None:
    """Does a bigger reasoning budget help — and does it help less on Vera?

    The controlled comparison no other provider offers: one model, two
    reasoning modes, every language. If Vera's delta is ~0 while the
    comparison languages gain from extra deliberation, the language is
    supplying the structure the reasoning budget otherwise has to
    reconstruct.
    """
    all_data = _merge_tiers(tiers)
    absent = missing or set()
    base_name, pro_name = REASONING_PAIR
    unknown = [n for n in REASONING_PAIR if n not in all_data]
    if unknown:
        print(f"  reasoning slide: no data for {unknown} — skipping")
        return

    base, pro = all_data[base_name], all_data[pro_name]
    # Both halves must have a real result file for the mode. `m in base`
    # cannot express that — extract_data writes 0 for a missing file, so
    # every mode key is always present. Without this, an unrun mode
    # contributes a fabricated delta of ±the other half's score, which is
    # exactly the quantity this slide exists to report.
    modes = [
        m
        for m in REASONING_MODES
        if (base_name, m) not in absent and (pro_name, m) not in absent
    ]
    if not modes:
        print(
            f"  reasoning slide: no mode has results for both "
            f"{base_name!r} and {pro_name!r} — skipping"
        )
        return
    deltas = [pro[m] - base[m] for m in modes]

    fig, ax = plt.subplots(figsize=(16, 9), dpi=180)
    x = np.arange(len(modes))
    width = 0.36

    for offset, row, label, alpha, hatch in (
        (-width / 2, base, "reasoning: standard", 0.95, None),
        (width / 2, pro, "reasoning: pro", 0.75, "//"),
    ):
        values = [row[m] for m in modes]
        bars = ax.bar(
            x + offset,
            values,
            width,
            label=label,
            color=[COLORS[m] for m in modes],
            edgecolor=CREAM,
            linewidth=0.8,
            alpha=alpha,
            hatch=hatch,
        )
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.5,
                f"{val}",
                ha="center",
                va="bottom",
                fontsize=BAR_LABEL_PT_MEDIUM,
                fontweight="bold",
                color=BROWN_700,
            )

    # The point of the slide: the per-language delta.
    for xi, d in zip(x, deltas):
        sign = "+" if d > 0 else ""
        ax.text(
            xi,
            108,
            f"{sign}{d} pp",
            ha="center",
            va="center",
            fontsize=BAR_LABEL_PT_MEDIUM,
            fontweight="bold",
            color=GREEN if d > 0 else (BROWN_500 if d == 0 else RED),
        )

    ax.set_ylabel("% solved", fontsize=AXIS_LABEL_PT, color=BROWN_500)
    # Punchy title + explanatory subtitle: the long single-line form
    # clips at 16:9 even at TITLE_PT - 2.
    ax.set_title(
        "Does more reasoning help?",
        fontsize=TITLE_PT,
        fontweight="bold",
        pad=44,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.text(
        0.5,
        1.015,
        f"{base_name} — one model, two reasoning budgets",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=SUBTITLE_PT,
        color=BROWN_500,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(modes, fontsize=TICK_PT_LARGE)
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.tick_params(axis="y", labelsize=TICK_PT_SMALL)
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.8, alpha=0.4)
    _style_ax(ax)

    # Neutral legend: colour already encodes language, so the legend
    # only needs to distinguish the two reasoning modes.
    ax.legend(
        handles=[
            Patch(
                facecolor="#888888",
                edgecolor=CREAM,
                alpha=0.95,
                label="reasoning: standard",
            ),
            Patch(
                facecolor="#888888",
                edgecolor=CREAM,
                alpha=0.75,
                hatch="//",
                label="reasoning: pro",
            ),
        ],
        # Under the axes — every bar here reaches 92%+, so there is no
        # interior whitespace left for a legend box.
        loc="upper center",
        bbox_to_anchor=(0.5, -0.09),
        ncol=2,
        fontsize=LEGEND_PT,
        framealpha=0.85,
        edgecolor=BROWN_300,
    )

    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.95))
    _save(fig, output, background)


RENDERERS = {
    "delta": render_delta,
    "tiers": render_tiers,
    "all-modes": render_all_modes,
    "ztd": render_ztd,
    "reasoning": render_reasoning,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--type",
        choices=[*RENDERERS.keys(), "all"],
        default="all",
        help="Which slide to render (default: all three).",
    )
    parser.add_argument(
        "--version",
        default="0.0.7",
        help=(
            "Bench version to plot. '0.0.7' renders against the frozen "
            "MODELS_V_0_0_7 talk lineup; any other version renders "
            "against the live plot_results.MODELS matrix."
        ),
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Directory containing JSONL result files.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output PNG path. Only valid with a single --type. "
            "Default: /tmp/vera-bench_slide_{type}.png"
        ),
    )
    parser.add_argument(
        "--background",
        choices=list(BACKGROUNDS),
        default=DEFAULT_BACKGROUND,
        help=(
            f"Slide background colour (default: {DEFAULT_BACKGROUND}). "
            "All choices are light themes — text/spine colours don't invert."
        ),
    )
    parser.add_argument(
        "--bare",
        action="store_true",
        help=(
            "Draw the plot only, with no title, subtitle or footnote, for "
            "embedding in a page whose prose carries them."
        ),
    )
    parser.add_argument(
        "--ztd-modes",
        default=None,
        help=(
            "Comma-separated zero-training-data languages for --type ztd "
            "(default: Vera,Aver,AILANG). e.g. 'Vera,Aver' for the two "
            "languages that drop variable names entirely."
        ),
    )
    args = parser.parse_args()

    if args.output and args.type == "all":
        parser.error("--output is only valid when --type is a single slide type")

    ztd_modes = (
        [m.strip() for m in args.ztd_modes.split(",")] if args.ztd_modes else None
    )
    if ztd_modes:
        # Against the ZTD lineup, not the full palette: COLORS also
        # holds Python, TypeScript and Vera NL, and putting any of
        # them on this slide contradicts its own title.
        unknown = [m for m in ztd_modes if m not in ZTD_MODES]
        if unknown:
            parser.error(
                f"--ztd-modes: {unknown} not zero-training-data; "
                f"choose from {ZTD_MODES}"
            )

    global BARE
    BARE = args.bare
    _slide_rcparams()
    types = list(RENDERERS) if args.type == "all" else [args.type]
    # "all" renders the base trio only — the ZTD slide needs Aver/AILANG
    # result files that historical versions don't have; request it
    # explicitly with --type ztd.
    if args.type == "all":
        types = [t for t in types if t not in ("ztd", "reasoning")]
    modes = ["Vera", "Vera NL", "Python", "TypeScript"]
    if "ztd" in types:
        # Load whatever the ZTD slide will actually draw, so a narrowed
        # --ztd-modes still finds its files.
        modes += [m for m in (ztd_modes or ZTD_MODES) if m not in modes]
    tiers, missing = _load_data(args.version, Path(args.results_dir), modes)

    for t in types:
        output = (
            Path(args.output) if args.output else Path(f"/tmp/vera-bench_slide_{t}.png")
        )
        kwargs = {"ztd_modes": ztd_modes} if t == "ztd" and ztd_modes else {}
        RENDERERS[t](
            tiers, output, background=args.background, missing=missing, **kwargs
        )


if __name__ == "__main__":
    main()
