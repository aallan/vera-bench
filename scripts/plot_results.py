#!/usr/bin/env python3
"""Generate benchmark comparison charts from VeraBench results.

Reads JSONL files in `results/` and produces a **% solved** (pass@1)
comparison chart, where a refusal, a compile failure, a runtime error and
a wrong answer all count as not-solved. The canonical committed chart
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

To add a new model, edit the canonical matrix in vera_bench/matrix.py;
the MODELS list below is a projection of it. File naming follows the
convention described in scripts/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Rendering needs matplotlib/numpy, but importing this module for its data
# helpers (MODELS, extract_data, _pass_at_1_pct) must not — so the test job
# that only imports those need not install a plotting backend. main() calls
# _require_mpl() before drawing anything.
try:
    import matplotlib
    import numpy as np

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - only where matplotlib absent
    matplotlib = plt = np = None

# Allow importing vera_bench without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vera_bench.matrix import MODELS as _MATRIX  # noqa: E402
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
# Tie marker on the delta charts. Neutral by design: a tie has no
# direction, so it must not borrow either polarity colour.
ZERO_STUB = "#7A7069"

COLORS = {
    "Vera": GREEN,
    "Vera NL": "#52b788",
    "Python": ORANGE_400,
    "TypeScript": BROWN_300,
    "Aver": "#6B4FBB",  # indigo — visually distinct from the Vera greens
    "AILANG": "#C2185B",  # magenta — distinct from Aver's indigo
}

# Redundant, non-colour identity channels. The palette above is the
# veralang.dev brand, and it does not survive a colourblind-safety audit
# on two pairs that matter:
#
#   Vera green vs Python orange   ΔE 4.4 (protanopia)
#   Vera green vs AILANG magenta  ΔE 2.1 (deuteranopia)
#
# Neither is fixable by reassignment — green-versus-orange IS the
# red-green axis, and it is precisely the comparison the benchmark
# exists to make. So identity never rests on hue alone: bars carry a
# fixed hatch, dot marks a fixed shape, and every mark a direct value
# label. Assigned by language and never cycled, so a language keeps its
# texture in charts that omit the others.
LANG_HATCH: dict[str, str | None] = {
    "Vera": None,
    "Vera NL": "//",
    "Python": "..",
    "TypeScript": "\\\\",
    "Aver": "xx",
    "AILANG": "--",
}
LANG_MARKER: dict[str, str] = {
    "Vera": "o",
    "Vera NL": "s",
    "Python": "^",
    "TypeScript": "D",
    "Aver": "v",
    "AILANG": "P",
}

# Neutral grey shades for the delta-chart legend (not per-language green/red).
_DELTA_LEGEND_SHADES = ["#888888", "#aaaaaa", "#cccccc"]
_DELTA_HATCHES = [None, "//", ".."]
_DELTA_ALPHAS = [0.85, 0.55, 0.40]

# --- Fonts (veralang.dev: Inter, DM Serif Display, JetBrains Mono) ---
FONT_BODY = "Inter UI"
FONT_HEADING = "Georgia"  # fallback for DM Serif Display

if matplotlib is not None:
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
    display: str  # Shown on the chart (e.g. "Claude Fable 5")
    file_prefix: str  # Model-id portion of result filename
    tier: str  # Key into TIER_TITLES — controls chart layout


# Tier display order + panel titles. Any tier present in MODELS but not
# listed here renders last with a title-cased fallback; a tier listed
# here but absent from MODELS is skipped (no empty panel).
TIER_TITLES: dict[str, str] = {
    "fable": "Fable Tier (ceiling)",
    "opus": "Opus Tier (flagship)",
    # Legacy "flagship" sits between opus and sonnet so historical
    # 2-tier renders (plot_slide's frozen v0.0.7 lineup) keep their
    # original left-to-right order: Flagship, then Sonnet.
    "flagship": "Flagship Tier",
    "sonnet": "Sonnet Tier (workhorse)",
}

# The lineup is the canonical matrix (vera_bench/matrix.py) projected onto
# the fields the chart needs. file_prefix comes from Model.file_prefix
# (CLI string, '/'->'-'), so it byte-matches what cli.py writes by
# construction rather than by a hand-kept copy.
MODELS: list[ModelSpec] = [ModelSpec(m.display, m.file_prefix, m.tier) for m in _MATRIX]

# Models that also run the Aver + AILANG generation targets, by display
# name. Derived from the matrix's own `ztd` flag rather than hand-listed:
# a hardcoded copy silently dropped Claude Opus 5 from the
# zero-training-data slide when it was added to the matrix, which is the
# precise class of drift the matrix consolidation exists to prevent.
ZTD_DISPLAYS: list[str] = [m.display for m in _MATRIX if m.ztd]

# Lineups for bench versions whose models have since left the matrix.
# Without this, `--version 0.0.7` looks up today's nine models against
# result files written for six retired ones, misses every single lookup,
# and — because extract_data records an absent file as 0 — renders a
# complete, well-formed, entirely blank chart. Both shipped historical
# versions ran the same six models. `plot_slide.py` had this lineup
# frozen for its own renderer; the documentation chart never did.
_LINEUP_V_0_0_7: list[ModelSpec] = [
    ModelSpec("Claude Opus 4", "claude-opus-4-20250514", "flagship"),
    ModelSpec("GPT-4.1", "gpt-4.1-2025-04-14", "flagship"),
    ModelSpec("Kimi K2.5", "moonshot-kimi-k2.5", "flagship"),
    ModelSpec("Claude Sonnet 4", "claude-sonnet-4-20250514", "sonnet"),
    ModelSpec("GPT-4o", "gpt-4o", "sonnet"),
    ModelSpec("Kimi K2 Turbo", "moonshot-kimi-k2-turbo-preview", "sonnet"),
]
HISTORICAL_LINEUPS: dict[str, list[ModelSpec]] = {
    "0.0.7": _LINEUP_V_0_0_7,
    "0.0.9": _LINEUP_V_0_0_7,
}


def lineup_for(version: str) -> list[ModelSpec]:
    """The models a given bench version actually ran."""
    return HISTORICAL_LINEUPS.get(version, MODELS)


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
    "AILANG": "ailang-",  # {prefix}-ailang-bench-{v}-ailang-*.jsonl
}

# Modes that have a trailing "-{compiler}-{ver}" suffix in the filename.
_COMPILER_SUFFIXED = {
    "Vera": "vera",
    "Vera NL": "vera",
    "Aver": "aver",
    "AILANG": "ailang",
}

# Default chart: Python + TypeScript as comparison languages. Opt in to Aver
# / AILANG (or future languages) via --extra.
DEFAULT_COMPARISON_MODES = ["Python", "TypeScript"]
OPTIONAL_COMPARISON_MODES = {"aver": "Aver", "ailang": "AILANG"}


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


_GRADEABLE_IDS: set[str] | None = None

# Problems whose test cases were first added in a given bench version.
# The gradeable set is read from problems/ on disk, which only knows
# TODAY's problem set — but old result files carry rows for problems
# that were not gradeable when they were swept. Without this pin,
# regenerating a v0.0.16 chart after #107 landed would divide 36
# problems' worth of solves by the current 60-problem denominator and
# silently deflate every published number. Same failure class, same
# remedy, as HISTORICAL_LINEUPS above.
#
# Maintenance rule: whenever test cases are added to an EXISTING
# problem, record its id here against the first bench version whose
# sweeps grade it. Brand-new problems need no entry — old result files
# carry no rows for them at all, so presence-filtering already excludes
# them.
GRADEABLE_ADDED: dict[str, str] = {
    **{
        pid: "0.0.17"
        for pid in (
            # arrays, via the generated wrapper (#107 step 1)
            "VB-T2-001",
            "VB-T2-002",
            "VB-T2-006",
            "VB-T2-007",
            "VB-T2-008",
            "VB-T2-010",
            "VB-T5-005",
            "VB-T5-010",
            # scalar strings on the CLI, no wrapper needed
            "VB-T2-003",
            "VB-T2-009",
        )
    },
    **{
        pid: "0.0.18"
        for pid in (
            # ADT arguments, matched against the model's own declaration
            # (#107 step 2a)
            "VB-T3-001",
            "VB-T3-002",
            "VB-T3-003",
            "VB-T3-004",
            "VB-T3-005",
            "VB-T3-006",
            "VB-T3-007",
            "VB-T3-008",
            "VB-T4-009",
            # ADT returns, compared structurally per language (step 2b)
            "VB-T3-009",
            "VB-T3-010",
            "VB-T4-006",
            # graded on printed output (step 5)
            "VB-T5-002",
            "VB-T5-008",
        )
    },
}


def _version_tuple(version: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(x) for x in version.split("."))
    except (AttributeError, ValueError):
        return None


def _gradeable_ids(version: str | None = None) -> set[str]:
    """Problem ids output-gradeable as of `version` (None = today).

    The base set is read from problems/ so the pass@1 denominator is the
    real number of gradeable problems, not a hardcoded constant that
    would silently rot. `version` then subtracts problems whose test
    cases postdate that bench version, per GRADEABLE_ADDED — an
    unparseable version is treated as current rather than guessed at.
    """
    global _GRADEABLE_IDS
    if _GRADEABLE_IDS is None:
        ids: set[str] = set()
        root = Path(__file__).resolve().parent.parent / "problems"
        for pf in root.rglob("VB_*.json"):
            try:
                p = json.loads(pf.read_text())
            except (OSError, ValueError):
                continue
            if p.get("test_cases"):
                ids.add(p.get("id"))
        _GRADEABLE_IDS = ids
    base = _GRADEABLE_IDS
    vt = _version_tuple(version) if version is not None else None
    if vt is None:
        return base
    return {
        pid
        for pid in base
        if pid not in GRADEABLE_ADDED
        or (_version_tuple(GRADEABLE_ADDED[pid]) or ()) <= vt
    }


def _declined(row: dict) -> bool:
    """A harness decline: ungraded because WE could not build a caller."""
    return "run_correct" not in row and "test wrapper unavailable" in (
        row.get("error_message") or ""
    )


def _pass_at_1_pct(rows: list[dict], version: str | None = None) -> int | None:
    """pass@1 as an integer percent: solved / gradeable-problems-present.

    A refusal, a compile failure, a runtime error and a wrong answer all
    count as NOT solved — the model was asked to produce correct code and
    did not. This is the honest headline: unlike run_correct-over-eligible
    it does not shrink the denominator when the model refuses or fails to
    compile, so refusing hard problems cannot inflate the bar.

    The one exception is a harness DECLINE — "test wrapper unavailable",
    written when the harness could not map the model's own type
    declaration to build a caller. That is the harness abstaining, not
    the model failing, so the problem leaves the denominator for that
    target. The distinction is deliberate and narrow: only rows the
    harness itself labelled are excluded, so a model cannot buy a
    smaller denominator with anything it writes.

    Best attempt per problem (an attempt-2 fix that compiles supersedes
    attempt-1), matching compute_metrics. Returns None when no gradeable
    problem is present, so the caller can treat that as absent data rather
    than a genuine 0%.
    """
    gradeable = _gradeable_ids(version)
    attempts: dict[str, dict[int | None, dict]] = {}
    for r in rows:
        pid = r.get("problem_id")
        if pid in gradeable:
            attempts.setdefault(pid, {})[r.get("attempt")] = r
    if not attempts:
        return None
    solved = eligible = 0
    for a in attempts.values():
        a2, a1 = a.get(2), a.get(1)
        best = a2 if (a2 and a2.get("check_pass")) else a1
        if best and _declined(best):
            continue
        eligible += 1
        if best and best.get("run_correct") is True:
            solved += 1
    if not eligible:
        return None
    return round(100 * solved / eligible)


def extract_data(
    results_dir: Path, version: str, modes: list[str]
) -> tuple[dict[str, dict], list[str], list[Path], set[tuple[str, str]]]:
    """Extract pass@1 (% solved) percentages for every MODEL × MODE.

    Args:
        results_dir: Directory containing JSONL result files.
        version: Bench version (e.g. "0.0.16").
        modes: Mode labels to extract, in display order. Must be keys in
            MODE_PATTERNS.

    Returns (tiers, warnings, used_paths, missing).
    tiers: dict[tier_key] -> dict[display_name] -> dict[mode_label] -> int
        percentage. Tier keys appear in TIER_TITLES order (unknown tiers
        last, in MODELS order); only tiers with at least one model are
        present — an unpopulated tier gets no empty panel.
    warnings: human-readable list of missing files.
    used_paths: the actual JSONL files consulted (one per successful lookup).
        Downstream code should derive subtitle metadata (compiler version,
        problem count) from this list rather than re-globbing — re-globbing
        can pick up stale files that _find_result_file's mtime tie-breaker
        would have rejected.
    missing: {(display_name, mode_label)} for which no result file existed.

        A missing cell is still written into `tiers` as 0, because the
        comprehensive doc chart deliberately renders it as a visible 0%
        gap you can go and fill. But 0-because-absent and 0-because-the
        -model-scored-nothing are then indistinguishable in `tiers`
        alone, and for the specialised slides that difference is the
        whole point: plotting an un-run language at 0% on the
        zero-training-data slide would read as a catastrophic result for
        that language rather than as no data. Renderers that must not
        fabricate a bar consult this set.
    """
    tiers: dict[str, dict[str, dict[str, int]]] = {}
    warnings: list[str] = []
    used_paths: list[Path] = []
    missing: set[tuple[str, str]] = set()

    # Historical versions ran a different lineup; anything else uses the
    # live matrix (which plot_slide may have patched for its own render).
    for model in lineup_for(version):
        row: dict[str, int] = {}
        for mode in modes:
            path = _find_result_file(results_dir, model, mode, version)
            if path is None:
                warnings.append(
                    f"  {model.display} / {mode}: no file matching bench-{version}"
                )
                row[mode] = 0
                missing.add((model.display, mode))
                continue
            used_paths.append(path)
            data = _load_jsonl(path)
            pass1 = _pass_at_1_pct(data, version)
            if pass1 is None:
                # No gradeable problem produced a verdict — the file has
                # none, or every attempt infra-failed. Distinguish from a
                # genuine 0% (the missing set keeps it off the chart as a
                # gap): absent *data* rather than an absent *file*.
                errored = compute_metrics(data).errored
                warnings.append(
                    f"  {model.display} / {mode}: no gradeable result "
                    f"({errored} errored) — {path.name}"
                )
                row[mode] = 0
                missing.add((model.display, mode))
                continue
            row[mode] = pass1

        tiers.setdefault(model.tier, {})[model.display] = row

    # Order tiers: TIER_TITLES order first, then any unknown tiers in
    # first-seen order.
    ordered = {k: tiers[k] for k in TIER_TITLES if k in tiers}
    ordered.update({k: v for k, v in tiers.items() if k not in ordered})
    return ordered, warnings, used_paths, missing


def complete_models(
    all_data: dict, missing: set[tuple[str, str]] | None, modes: list[str]
) -> list[str]:
    """Models with a real result file for every mode in `modes`.

    `extract_data` writes 0 for an absent file, so `mode in row` cannot
    answer this — every key is always present.

    A *bar* of 0 is the documented doc-chart behaviour: a visible gap you
    go and fill. A *delta* against an absent file is a different animal.
    It fabricates a number that carries a sign and a colour, and on the
    "Does Vera beat Python?" panel an un-run Python target renders as
    Vera winning by 100 — the strongest possible version of the claim
    the chart exists to make, produced entirely by missing data. Any
    renderer computing a difference must filter through this.
    """
    absent = missing or set()
    return [m for m in all_data if all((m, mode) not in absent for mode in modes)]


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
    # A tier is not a fixed size — opus went from three models to four
    # when Opus 5 landed, and at four the panel is the same width with
    # 33% more bars: the x labels ran together ("Claude Opus 4.8Claude
    # Opus 5") and the value labels overprinted each other. Shrink and
    # tilt past three rather than hardcoding for the lineup of the day.
    crowded = len(models) > 3
    tick_pt = 9 if crowded else 10
    bar_pt = 7 if crowded else 9
    # Drop the per-cent sign once a panel is crowded: the axis is already
    # labelled "% solved", and at four models "100%" beside "100%" is
    # about 20% too wide to clear its neighbour.
    fmt = "{}" if crowded else "{}%"

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
            hatch=LANG_HATCH[lang],
        )
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                fmt.format(val),
                ha="center",
                va="bottom",
                fontsize=bar_pt,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.set_ylabel("% solved", fontsize=10, color=BROWN_500)
    ax.set_title(
        title,
        fontsize=13,
        fontweight="bold",
        pad=12,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.set_xticks(x + width * (len(languages) - 1) / 2)
    ax.set_xticklabels(
        models,
        fontsize=tick_pt,
        rotation=10 if crowded else 0,
        ha="right" if crowded else "center",
    )
    ax.set_ylim(0, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.5, alpha=0.3)
    _style_ax(ax)
    # Below the panel, not inside it. Every bar in this chart now lands
    # near 100%, so there is no longer any interior whitespace for a
    # legend to occupy — "lower left" printed it straight over the bars.
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=len(languages),
        fontsize=8.5,
        framealpha=0.8,
        edgecolor=BROWN_300,
    )


def plot_vera_vs_comparison(
    ax,
    tiers: dict[str, dict],
    comparison_modes: list[str],
    missing: set[tuple[str, str]] | None = None,
):
    """Horizontal bars: Vera % solved minus each comparison language, per model."""
    from matplotlib.patches import Patch  # noqa: E402

    all_data: dict = {}
    for tier_data in tiers.values():
        all_data.update(tier_data)
    # A model missing any of Vera / the comparison languages would yield a
    # fabricated delta rather than a visible gap — see complete_models.
    models = complete_models(all_data, missing, ["Vera", *comparison_modes])
    if not models:
        # Every bar here is a difference, so a partial run leaves nothing
        # to draw. Say so on the panel rather than leaving a clean empty
        # box that reads as "no differences found".
        ax.text(
            0.5,
            0.5,
            "No model ran Vera and every comparison language,\n"
            "so no difference can be computed.",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=11,
            color=BROWN_300,
        )
        ax.set_axis_off()
        return

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

    # Axis limit is needed before drawing, to size the zero stub below.
    # Floor lowered from ±22 (sized for v0.0.7's ±17 spread) so a frontier
    # lineup whose largest delta is 8 does not sit squeezed into the
    # middle third of an empty panel.
    max_abs = max(
        (abs(v) for mode in comparison_modes for v in deltas[mode]), default=0
    )
    limit = max(12, max_abs + 4)
    zero_stub = limit * 0.018

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
        # A zero delta draws a zero-length bar — i.e. nothing — leaving its
        # "0" label floating in white space with no mark to belong to, and
        # no way to tell "tied" from "no data". A neutral stub at the axis
        # gives every row a mark. Deliberately grey, not the green/red
        # polarity colours: a tie has no direction.
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
            # Offset in POINTS, not data units. A fixed ±1-unit offset is a
            # constant fraction of the axis, so as the x-limit shrank with
            # the data the labels drifted off into whitespace instead of
            # sitting at the ends of their bars.
            tip = zero_stub / 2 if val == 0 else val
            sign = "+" if val > 0 else ""
            ax.annotate(
                f"{sign}{val}",
                xy=(tip, bar.get_y() + bar.get_height() / 2),
                xytext=(4 if val >= 0 else -4, 0),
                textcoords="offset points",
                ha="left" if val >= 0 else "right",
                va="center",
                fontsize=9,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.axvline(x=0, color=BROWN_900, linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(models, fontsize=10)
    ax.set_xlabel(
        "Vera % solved minus comparison language (pp)",
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


def plot_all_modes(ax, tiers: dict[str, dict], modes: list[str]):
    """Grouped comparison: all modes (Vera + Vera NL + comparisons) per model."""
    all_data: dict = {}
    for tier_data in tiers.values():
        all_data.update(tier_data)
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
            # Rotated, because 9 models x 4 modes puts 36 bars in one
            # panel: at frontier scores nearly every label is the 3-glyph
            # "100", which is wider than its own bar, so horizontal labels
            # collide no matter how small the type gets. Upright text
            # costs one glyph of width instead of three.
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.5,
                f"{val}",
                ha="center",
                va="bottom",
                rotation=90,
                fontsize=7,
                fontweight="bold",
                color=BROWN_700,
            )

    ax.set_ylabel("% solved", fontsize=10, color=BROWN_500)
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
    ax.set_ylim(0, 128)  # headroom for the rotated value labels
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.5, alpha=0.3)
    _style_ax(ax)
    # Same reason as plot_tier: with every bar at the ceiling there is no
    # interior gap left to drop a legend into.
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        fontsize=8,
        ncol=len(modes),
        framealpha=0.8,
        edgecolor=BROWN_300,
    )


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


def _require_mpl() -> None:
    """Fail clearly if a rendering entrypoint runs without a plotting backend."""
    if plt is None:
        raise SystemExit(
            "plot_results needs matplotlib + numpy to render — "
            "install them: pip install matplotlib numpy"
        )


def main():
    _require_mpl()
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

    tiers, warnings, used_paths, missing = extract_data(results_dir, version, all_modes)
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(w)

    # Refuse to write a chart with no data in it. extract_data records an
    # absent file as 0, which is the right call for one missing cell — a
    # visible gap you go and fill — but when EVERY cell is absent it
    # produces a fully-formed chart of zeros that looks like a result. You
    # find out it is empty once it is already in the slide deck.
    if not used_paths:
        raise SystemExit(
            f"No result files matched bench-{version} in {results_dir}/ — "
            f"refusing to write an empty chart.\n"
            f"Models looked for: "
            f"{', '.join(m.file_prefix for m in lineup_for(version))}\n"
            f"If this version ran a different lineup, add it to "
            f"HISTORICAL_LINEUPS in scripts/plot_results.py."
        )

    vera_version = _detect_vera_version(used_paths)
    problem_count = _detect_problem_count(used_paths)
    subtitle = (
        f"{problem_count} problems \u00d7 {len(lineup_for(version))} models "
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

    # Row 1 holds one panel per populated tier (2 for legacy data,
    # 3 for the v0.0.16 matrix); rows 2-4 span the full width.
    n_tiers = max(len(tiers), 1)
    gs = fig.add_gridspec(
        4,
        n_tiers,
        # Roomier than the original 0.35: the tier panels now carry their
        # legends *below* the axes, which pushed the next row's title
        # into them.
        hspace=0.5,
        wspace=0.3,
        height_ratios=[1, 1, 1, 0.3],
        left=0.10,
        right=0.95,
        top=0.92,
        bottom=0.04,
    )

    # Row 1: one tier panel per populated tier, in TIER_TITLES order.
    for col, (tier_key, tier_data) in enumerate(tiers.items()):
        ax_t = fig.add_subplot(gs[0, col])
        title = TIER_TITLES.get(tier_key, tier_key.title())
        plot_tier(ax_t, tier_data, f"{title} \u2014 % solved", comparison_modes)

    # Row 2: delta chart
    ax3 = fig.add_subplot(gs[1, :])
    plot_vera_vs_comparison(ax3, tiers, comparison_modes, missing=missing)

    # Row 3: all modes
    ax4 = fig.add_subplot(gs[2, :])
    plot_all_modes(ax4, tiers, all_modes)

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
