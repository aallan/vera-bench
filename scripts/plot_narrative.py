#!/usr/bin/env python3
"""Narrative 16:9 slides that need raw result rows, not just pass@1.

`plot_slide.py` renders the four slides whose input is a single number per
(model, mode) — exactly what `plot_results.extract_data` returns. The
slides here need something that aggregate cannot express:

- `refusal`    — WHICH problem a model declined, and whether that same
                 model solved that same problem in another language.
                 Needs per-row `error_message`, not a rate.
- `generation` — one model family across consecutive releases, every
                 language. A slope chart, so the reader sees direction
                 rather than two bar heights they must subtract by eye.
- `saturation` — every (model, language) score as its own dot, to show
                 the frontier is bunched against the ceiling and that the
                 headline deltas are one or two problems wide.
- `coverage`   — where the static gate and the runtime disagree: the
                 programs that cleared `vera check` and still failed,
                 named individually, against the count that were wrongly
                 refused.

Kept out of `plot_slide.py` deliberately. That module's data path is
`extract_data` -> tier dict of ints; threading a second, row-level path
through it would make every renderer there ask which of two shapes it
holds. These four own their loading instead.

Axis policy, applied per form rather than globally: bar charts start at
zero (a bar's length IS the quantity, so a cut baseline lies about
ratios). Dot and slope charts may zoom, because a dot encodes position
only and carries no area to misread — which is the whole reason
`saturation` and `generation` are dots and slopes rather than bars. With
every score between 89 and 100, bars would render as nine identical
full-height blocks and show nothing.

Colour is never the only channel. The categorical language palette fails
a colourblind-safety audit on its single most important pair — Vera green
vs Python orange sit at ΔE 4.4 under protanopia, because green-vs-orange
IS the red-green axis and no reassignment fixes it while Vera stays green.
Rather than rebrand, every series here carries a second, redundant
channel: a fixed hatch on bars, a fixed marker shape on dots, and a direct
value label on every mark. See `LANG_HATCH` / `LANG_MARKER`.

Usage:
    python scripts/plot_narrative.py --version 0.0.16
    python scripts/plot_narrative.py --version 0.0.16 --type refusal
    python scripts/plot_narrative.py --type saturation --output ~/s.png
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Guarded: the test job imports this module for solved(), best_by_problem()
# and find_refusals(), none of which draw anything. See plot_results.
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402
    import numpy as np  # noqa: E402
    from matplotlib.lines import Line2D  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - only where matplotlib absent
    matplotlib = plt = np = None
    Line2D = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.plot_slide as _slide  # noqa: E402
from scripts.plot_results import (  # noqa: E402
    BROWN_300,
    BROWN_500,
    BROWN_700,
    BROWN_900,
    COLORS,
    CREAM,
    FONT_HEADING,
    GREEN,
    LANG_MARKER,
    MODELS,
    RED,
    _default_version,
    _find_result_file,
    _gradeable_ids,
    extract_data,
    lineup_for,
)
from scripts.plot_slide import (  # noqa: E402
    AXIS_LABEL_PT,
    BACKGROUNDS,
    BAR_LABEL_PT_MEDIUM,
    BAR_LABEL_PT_SMALL,
    DEFAULT_BACKGROUND,
    LEGEND_PT,
    SUBTITLE_PT,
    TICK_PT_MEDIUM,
    TICK_PT_SMALL,
    TITLE_PT,
    _merge_tiers,
    _save,
    _slide_rcparams,
    _style_ax,
)
from scripts.sweep_status import is_refusal  # noqa: E402

ALL_MODES = ["Vera", "Vera NL", "Python", "TypeScript", "Aver", "AILANG"]

# The Anthropic ceiling line, oldest first, as (bench version, display).
# Cross-version by design: each model is pinned to a release that actually
# swept it — Opus 4 only ever ran under 0.0.9 — so the trajectory cannot
# be read out of a single results generation.
#
# TWO confounds ride along, and both are printed on the slide rather than
# buried here. First, ATTRIBUTION: the compiler and its stdlib
# (0.0.112 -> 0.1.8), SKILL.md (fetched at runtime, so never pinned) and
# the problem definitions all moved under the FIRST step, so it measures
# the ecosystem improving as much as the model — a stdlib expansion lands
# hardest on Tier 2, which tests built-in function discovery. Second,
# DENOMINATOR: 0.0.9 grades 36 problems, 0.0.18 all 60. Both confounds
# now sit on that one step; every later link shares a release, a
# compiler and a problem set, so the rest of the line is like-for-like.
#
# Read the slope for direction, never for the size of any single step.
# Python and TypeScript touch none of the Vera toolchain, which is what
# makes their lines the control. For a step with NO confound, use
# CONTROLLED_PAIR (--pair-only).
GENERATION_CHAIN = [
    ("0.0.9", "Claude Opus 4"),
    ("0.0.18", "Claude Opus 4.8"),
    ("0.0.18", "Claude Opus 5"),
    ("0.0.18", "Claude Fable 5"),
]

# The controlled step, named separately rather than taken as the chain's
# last two links — those stopped coinciding once a fourth link landed.
# It is now a genuine sub-segment of the chain: same models, same bench
# version, same numbers. That matters because both slides go in one deck.
# While the chain read these two from 0.0.16 and this pair read them from
# 0.0.18, the two slides disagreed about the SAME pair — Opus 4.8 to Opus
# 5 in TypeScript fell 6 points on one and rose 3 on the other — because
# 0.0.16 grades 36 problems and 0.0.18 grades 60. A model appears at one
# score per deck, so every link that HAS 0.0.18 data reads it.
CONTROLLED_PAIR = [
    ("0.0.18", "Claude Opus 4.8"),
    ("0.0.18", "Claude Opus 5"),
]

# The default mode set for every slide here. Aver and AILANG belong on
# the dedicated zero-training-data slide, where they are the subject and
# only the five models that actually ran them appear. Everywhere else
# they add columns that most of the lineup never ran, and on a slide
# about direction (generation) they contribute near-flat ones. Opt back
# in with --include-ztd.
GENERATION_MARKERS = ["o", "s", "D", "^", "v"]

CORE_MODES = ["Vera", "Vera NL", "Python", "TypeScript"]


# ----------------------------------------------------------------------
# Row-level loading (what extract_data's aggregate cannot answer)
# ----------------------------------------------------------------------


def load_rows(
    results_dir: Path, version: str, modes: list[str]
) -> dict[tuple[str, str], list[dict]]:
    """Raw JSONL rows keyed by (model display name, mode label).

    Absent (model, mode) combinations are simply missing from the dict
    rather than present-and-empty: callers here distinguish "this model
    never ran this language" from "it ran and refused nothing", and an
    empty list would collapse those two into the same value.
    """
    out: dict[tuple[str, str], list[dict]] = {}
    # Historical versions ran a different lineup; looking up today's
    # models against their files matches nothing at all.
    for model in lineup_for(version):
        for mode in modes:
            path = _find_result_file(results_dir, model, mode, version)
            if path is None:
                continue
            rows = [
                json.loads(line)
                for line in path.read_text().splitlines()
                if line.strip()
            ]
            if rows:
                out[(model.display, mode)] = rows
    return out


def best_by_problem(rows: list[dict]) -> dict[str, dict]:
    """One row per problem: the attempt a grader would score.

    Mirrors `compute_metrics`/`_pass_at_1_pct`: a second attempt supersedes
    the first only when it actually compiled, so a failed fix never
    displaces a passing original.
    """
    attempts: dict[str, dict[int | None, dict]] = defaultdict(dict)
    for r in rows:
        attempts[r.get("problem_id")][r.get("attempt")] = r
    best: dict[str, dict] = {}
    for pid, by_attempt in attempts.items():
        a2, a1 = by_attempt.get(2), by_attempt.get(1)
        chosen = a2 if (a2 and a2.get("check_pass")) else a1
        if chosen:
            best[pid] = chosen
    return best


def solved(row: dict | None, problem_id: str, version: str | None = None) -> bool:
    """Did this attempt succeed, by the strongest verdict available?

    Gradeability decides which verdict applies. Problems without test
    cases (none as of v0.0.18; version-pinned) carry `run_correct`
    None by construction — never because anything failed. Testing `run_correct is
    True` alone therefore reports a problem the model compiled and
    verified everywhere as solved NOWHERE, which on the refusal slide
    inverts the argument: the line exists to prove the model *could* do
    the problem, and it would instead assert that it could not.

    So: output-graded where output can be graded, compilation (which for
    Vera means the contracts checked) where it cannot.
    """
    if row is None:
        return False
    if problem_id in _gradeable_ids(version):
        return row.get("run_correct") is True
    return row.get("check_pass") is True


def find_refusals(
    rows_by_target: dict[tuple[str, str], list[dict]],
    version: str | None = None,
) -> list[dict]:
    """Every refusal, with the languages that same model solved it in.

    The cross-language column is the entire evidential weight of the
    refusal slide: a refusal alone is ambiguous between "the model would
    not" and "the model could not". Showing the same model solving the
    same problem elsewhere removes the second reading.
    """
    best_cache = {k: best_by_problem(v) for k, v in rows_by_target.items()}
    found: list[dict] = []
    for (model, mode), best in best_cache.items():
        for pid, row in best.items():
            if not is_refusal(row.get("error_message") or ""):
                continue
            solved_in = sorted(
                other_mode
                for (other_model, other_mode), other_best in best_cache.items()
                if other_model == model
                and other_mode != mode
                and solved(other_best.get(pid), pid, version)
            )
            found.append(
                {"model": model, "mode": mode, "problem": pid, "solved_in": solved_in}
            )
    # Stable, readable order: by model as listed in the matrix, then mode.
    order = {m.display: i for i, m in enumerate(MODELS)}
    found.sort(key=lambda f: (order.get(f["model"], 99), f["mode"], f["problem"]))
    return found


# ----------------------------------------------------------------------
# Slide 1 — the refusal matrix
# ----------------------------------------------------------------------


def render_refusal(
    results_dir: Path,
    version: str,
    output: Path,
    background: str = DEFAULT_BACKGROUND,
) -> None:
    """Where models declined to answer — a model x language grid.

    A bar chart of refusal counts would plot five bars of height 1 and 2
    against a field of zeros; the reader would take away "refusals are
    rare" and miss the structure. The grid makes the structure the
    subject: the eye lands on which COLUMNS are empty, and the
    zero-training-data block being blank is the finding.
    """
    rows_by_target = load_rows(results_dir, version, ALL_MODES)
    refusals = find_refusals(rows_by_target, version)

    model_names = [m.display for m in lineup_for(version)]
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in refusals:
        counts[(r["model"], r["mode"])] += 1

    fig = plt.figure(figsize=(16, 9), dpi=180)
    # Grid left, the annotated roll-call right. The list is what turns
    # the grid from a curiosity into an argument, so it gets real estate
    # rather than a footnote.
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.32, 1],
        wspace=0.16,
        left=0.13,
        right=0.975,
        top=0.80,
        bottom=0.10,
    )
    ax = fig.add_subplot(gs[0, 0])

    n_rows, n_cols = len(model_names), len(ALL_MODES)
    for j, mode in enumerate(ALL_MODES):
        # Tint the zero-training-data columns so "the empty block" is
        # legible as a group rather than three unrelated empty columns.
        if mode in ("Vera", "Vera NL", "Aver", "AILANG"):
            ax.add_patch(
                plt.Rectangle(
                    (j - 0.5, -0.5), 1, n_rows, facecolor=GREEN, alpha=0.05, zorder=0
                )
            )
        for i, model in enumerate(model_names):
            ran = (model, mode) in rows_by_target
            c = counts.get((model, mode), 0)
            if not ran:
                ax.text(
                    j,
                    i,
                    "·",
                    ha="center",
                    va="center",
                    fontsize=20,
                    color=BROWN_300,
                    alpha=0.45,
                    zorder=3,
                )
                continue
            if c:
                ax.add_patch(
                    plt.Rectangle(
                        (j - 0.42, i - 0.40),
                        0.84,
                        0.80,
                        facecolor=RED,
                        alpha=0.88,
                        edgecolor=CREAM,
                        linewidth=1.2,
                        zorder=2,
                    )
                )
                ax.text(
                    j,
                    i,
                    str(c),
                    ha="center",
                    va="center",
                    fontsize=22,
                    fontweight="bold",
                    color="white",
                    zorder=3,
                )
            else:
                ax.text(
                    j,
                    i,
                    "0",
                    ha="center",
                    va="center",
                    fontsize=17,
                    color=BROWN_300,
                    alpha=0.75,
                    zorder=3,
                )

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(ALL_MODES, fontsize=TICK_PT_SMALL - 1)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(model_names, fontsize=TICK_PT_SMALL - 1)
    ax.set_xlim(-0.5, n_cols - 0.5)
    ax.set_ylim(n_rows - 0.5, -0.5)
    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which="minor", color=BROWN_300, linewidth=0.6, alpha=0.35)
    ax.tick_params(which="minor", length=0)
    ax.tick_params(which="major", length=0, colors=BROWN_500)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(
        "refusals by model × language",
        fontsize=SUBTITLE_PT,
        color=BROWN_500,
        pad=14,
    )

    # --- the roll-call ---
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis("off")
    ax2.text(
        0,
        1.0,
        "Every refusal, and where that\nsame model solved it:",
        transform=ax2.transAxes,
        fontsize=SUBTITLE_PT,
        va="top",
        color=BROWN_700,
        fontweight="bold",
        linespacing=1.35,
    )
    y = 0.845
    for r in refusals:
        ax2.text(
            0,
            y,
            f"{r['model']}  —  {r['mode']}",
            transform=ax2.transAxes,
            fontsize=17,
            va="top",
            color=BROWN_900,
            fontweight="bold",
        )
        ax2.text(
            0,
            y - 0.052,
            f"refused {r['problem']}",
            transform=ax2.transAxes,
            fontsize=16,
            va="top",
            color=RED,
        )
        solved_in = ", ".join(r["solved_in"]) if r["solved_in"] else "nowhere"
        ax2.text(
            0,
            y - 0.102,
            f"solved it in: {solved_in}",
            transform=ax2.transAxes,
            fontsize=15,
            va="top",
            color=GREEN,
        )
        y -= 0.185
    if not refusals:
        ax2.text(
            0,
            0.8,
            "No refusals in this run.",
            transform=ax2.transAxes,
            fontsize=18,
            va="top",
            color=BROWN_500,
        )

    ztd_total = sum(
        c
        for (mdl, mode), c in counts.items()
        if mode in ("Vera", "Vera NL", "Aver", "AILANG")
    )
    headline = (
        "Models refuse in Python and TypeScript — never in Vera"
        if ztd_total == 0
        else "Refusals cluster in the training-rich languages"
    )
    fig.suptitle(
        headline,
        fontsize=TITLE_PT - 2,
        fontweight="bold",
        y=0.955,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    fig.text(
        0.5,
        0.878,
        f"{len(refusals)} refusals across the sweep — "
        f"{len(refusals) - ztd_total} in a training-rich language, "
        f"{ztd_total} in a zero-training-data one",
        ha="center",
        fontsize=SUBTITLE_PT,
        color=BROWN_500,
    )
    # "Solved" is gradeability-dependent (see solved()), and a slide that
    # claims a model solved something owes the reader the definition.
    fig.text(
        0.5,
        0.035,
        "solved = output matched the test cases, or — for problems with "
        "no test cases — the code compiled and passed its contracts.     "
        "·  =  language not run for that model",
        ha="center",
        fontsize=13,
        color=BROWN_300,
    )
    _save(fig, output, background)


# ----------------------------------------------------------------------
# Slide 2 — one model family, consecutive releases
# ----------------------------------------------------------------------


def render_generation(
    results_dir: Path,
    version: str,
    output: Path,
    background: str = DEFAULT_BACKGROUND,
    modes: list[str] | None = None,
    span_versions: bool = True,
) -> None:
    """Consecutive flagship releases across every language, as a slope.

    Grouped bars would force the reader to subtract two heights by eye,
    per language, and the quantity that matters here is the DIRECTION of
    each pair. A slope encodes direction as slope, which needs no
    arithmetic. The y-axis is zoomed because these are position-only
    marks with no area to misread.
    """
    wanted = modes or CORE_MODES
    chain = GENERATION_CHAIN if span_versions else CONTROLLED_PAIR
    # The chain pins its own bench version per link, because the trajectory
    # spans releases by design. --version therefore cannot steer it, and
    # saying so beats rendering the 0.0.16 chain under a 0.0.9 heading.
    if version != chain[-1][0]:
        print(
            f"  generation slide: --version {version} does not apply; the "
            f"chain pins its own versions ({', '.join(v for v, _ in chain)})"
        )

    # Each link may come from a different bench version, so load per
    # version rather than once.
    points: list[tuple[str, dict[str, int], set]] = []
    for ver, display in chain:
        tiers, _warn, _used, miss = extract_data(results_dir, ver, wanted)
        data = _merge_tiers(tiers)
        if display not in data:
            print(f"  generation slide: no {display} in bench-{ver} — skipping")
            return
        points.append((display, data[display], miss))

    # A mode counts only when EVERY link really ran it: extract_data
    # writes 0 for an absent file, and a 0 here would render as a
    # catastrophic regression that never happened.
    modes = [
        m for m in wanted if all((disp, m) not in miss for disp, _row, miss in points)
    ]
    if not modes:
        print("  generation slide: no mode ran on every release — skipping")
        return

    fig, ax = plt.subplots(figsize=(16, 9), dpi=180)
    x = np.arange(len(modes))
    n_pts = len(points)
    # Spread the chain's points across the column.
    spread = 0.34 if n_pts > 2 else 0.17
    dxs = [
        (-spread + 2 * spread * i / (n_pts - 1)) if n_pts > 1 else 0.0
        for i in range(n_pts)
    ]

    for xi, mode in zip(x, modes):
        vals = [row[mode] for _disp, row, _m in points]
        for k in range(n_pts - 1):
            a, b = vals[k], vals[k + 1]
            seg = GREEN if b > a else (RED if b < a else BROWN_300)
            ax.plot(
                [xi + dxs[k], xi + dxs[k + 1]],
                [a, b],
                color=seg,
                linewidth=5,
                alpha=0.85,
                zorder=2,
                solid_capstyle="round",
            )
        # The newest point takes the DIRECTION colour of the step into it,
        # not the language colour. Language was the old encoding and it
        # made green mean two unrelated things on one slide: Vera's marker
        # was green because Vera is green, its line green because it rose
        # — so the reader learns "green = up", then meets TypeScript's
        # brown marker on the end of a green rising line and cannot tell
        # which rule applies. Nothing is lost by dropping it: the x-axis
        # already names the language, and the marker SHAPE still carries
        # the model. One colour, one meaning.
        last_dir = (
            (
                GREEN
                if vals[-1] > vals[-2]
                else (RED if vals[-1] < vals[-2] else BROWN_300)
            )
            if n_pts > 1
            else BROWN_500
        )
        for k, v in enumerate(vals):
            # Fill deepens along the chain, so the reading order is
            # visible without consulting the legend.
            frac = k / (n_pts - 1) if n_pts > 1 else 1.0
            ax.scatter(
                [xi + dxs[k]],
                [v],
                s=460,
                facecolor=last_dir if k == n_pts - 1 else "white",
                edgecolor=CREAM if k == n_pts - 1 else BROWN_500,
                linewidth=2.5 if k == n_pts - 1 else 3,
                alpha=0.35 + 0.65 * frac,
                zorder=3,
                marker=GENERATION_MARKERS[k % len(GENERATION_MARKERS)],
            )
        for k, v in enumerate(vals[:-1]):
            ax.text(
                xi + dxs[k],
                v - 1.5,
                str(v),
                ha="center",
                va="top",
                fontsize=BAR_LABEL_PT_SMALL,
                color=BROWN_500,
            )
        ax.text(
            xi + dxs[-1],
            vals[-1] + 1.3,
            str(vals[-1]),
            ha="center",
            va="bottom",
            fontsize=BAR_LABEL_PT_MEDIUM,
            fontweight="bold",
            color=BROWN_900,
        )
        d = vals[-1] - vals[0]
        sign = "+" if d > 0 else ""
        ax.text(
            xi,
            76.5,
            f"{sign}{d}" if d else "0",
            ha="center",
            va="center",
            fontsize=BAR_LABEL_PT_MEDIUM,
            fontweight="bold",
            color=GREEN if d > 0 else (RED if d < 0 else BROWN_300),
        )

    ax.text(
        -0.72,
        76.5,
        "net Δ pp",
        ha="center",
        va="center",
        fontsize=BAR_LABEL_PT_SMALL,
        color=BROWN_500,
        style="italic",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(modes, fontsize=TICK_PT_MEDIUM)
    ax.set_xlim(-1.0, len(modes) - 0.3)
    ax.set_ylim(74, 103)
    ax.set_yticks([80, 85, 90, 95, 100])  # no tick below the data
    ax.tick_params(axis="y", labelsize=TICK_PT_SMALL)
    ax.set_ylabel("% solved", fontsize=AXIS_LABEL_PT, color=BROWN_500)
    ax.axhline(y=100, color=BROWN_300, linestyle="--", linewidth=0.9, alpha=0.45)
    _style_ax(ax)
    # Punchy title in the brand heading face; the pair and the finding go
    # in the body-font subtitle. Georgia has no U+2192, so the arrow must
    # not live in a FONT_HEADING string — matplotlib drops the glyph and
    # only warns.
    # Title and subtitle DESCRIBE; they no longer assert. The old pair
    # said "Three flagships, one trajectory" and "the Vera line rises at
    # every step" — both true of the 3-link chain and both false the
    # moment a fourth link landed: the count was wrong, and Fable 5 falls
    # in three of four languages (Vera NL 100 -> 97). A caption that
    # states a finding has to be computed from the points, or it quietly
    # becomes a claim the chart underneath contradicts.
    ax.set_title(
        "One generation later"
        if len(points) < 3
        else "The Anthropic line, oldest to newest",
        fontsize=TITLE_PT,
        fontweight="bold",
        pad=46,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )

    def _net(mode: str) -> int | None:
        first, last = points[0][1].get(mode), points[-1][1].get(mode)
        return None if first is None or last is None else last - first

    # The model names live in the legend already; repeating them here is
    # what pushed this line off both edges of a 16:9 canvas at four links.
    moved = [f"{m} {_net(m):+d}" for m in (wanted or CORE_MODES) if _net(m) is not None]
    ax.text(
        0.5,
        1.016,
        "net change across the whole line, in percentage points:  " + "   ".join(moved),
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=SUBTITLE_PT if len(points) < 3 else SUBTITLE_PT - 3,
        color=BROWN_500,
    )
    ax.legend(
        handles=[
            Line2D(
                [],
                [],
                marker=GENERATION_MARKERS[k % len(GENERATION_MARKERS)],
                linestyle="none",
                markersize=17,
                markerfacecolor="white",
                markeredgecolor=CREAM if k == len(points) - 1 else BROWN_500,
                markeredgewidth=2.5,
                alpha=0.35 + 0.65 * (k / max(len(points) - 1, 1)),
                label=disp,
            )
            for k, (disp, _row, _m) in enumerate(points)
        ],
        # Below the axes, not inside them: an in-axes legend sits on the
        # Δ row, and the two rightmost languages are exactly where a
        # "lower right" box lands — it hid their deltas entirely.
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=len(points),
        fontsize=LEGEND_PT,
        framealpha=0.9,
        edgecolor=BROWN_300,
    )
    if span_versions:
        # Both confounds, stated on the slide rather than in a footnote
        # nobody reads: the Vera toolchain changed under the first link,
        # and the graded problem set grew under the last. The denominator
        # is derived rather than written down, so a future release that
        # changes it again cannot leave this caption quietly wrong.
        counts = [len(_gradeable_ids(v)) for v, _ in chain]
        grew = (
            f"Only the first point is graded over {counts[0]} problems; every "
            f"later one over {counts[-1]}, so read that first step as a change "
            f"of base, not a gain.\n"
            if len(set(counts)) > 1
            else ""
        )
        fig.text(
            0.5,
            0.028,
            "Opus 4 ran under Vera 0.0.112, every later point under 0.1.8; "
            "every problem carries a verdict in each era.\n"
            "The compiler, its stdlib and SKILL.md all moved between the "
            "first two points: that step measures the ecosystem improving as "
            "much as the model.\n"
            f"{grew}"
            "Python and TypeScript use no Vera toolchain, which is what makes "
            "their lines the control.",
            ha="center",
            fontsize=13,
            color=BROWN_300,
            linespacing=1.4,
        )
    fig.tight_layout(rect=(0.02, 0.10, 0.98, 0.94))
    _save(fig, output, background)


# ----------------------------------------------------------------------
# Slide 3 — saturation
# ----------------------------------------------------------------------


def render_saturation(
    results_dir: Path,
    version: str,
    output: Path,
    background: str = DEFAULT_BACKGROUND,
    modes: list[str] | None = None,
) -> None:
    """Every (model, language) score as a dot, on a zoomed axis.

    The honest companion to the delta slide, and a pre-emptive answer to
    "your differences are noise": it shows the frontier bunched against
    the ceiling, and prints how many percentage points one problem is
    worth, so a reader can size any gap in problems rather than points.
    """
    wanted = modes or CORE_MODES
    tiers, _warn, _used, missing = extract_data(results_dir, version, wanted)
    all_data = _merge_tiers(tiers)
    n_gradeable = len(_gradeable_ids(version))
    per_problem = 100 / n_gradeable if n_gradeable else 0

    fig, ax = plt.subplots(figsize=(16, 9), dpi=180)
    rows = list(reversed(wanted))  # first mode at the top
    all_values: list[int] = []

    for i, mode in enumerate(rows):
        values = [all_data[m][mode] for m in all_data if (m, mode) not in missing]
        if not values:
            continue
        # Fan exact ties vertically so N models on the same score read as
        # N dots. Overplotted, a 9-model pile-up at 100 looks like one.
        by_value: dict[int, int] = defaultdict(int)
        ys, xs = [], []
        for v in sorted(values):
            k = by_value[v]
            by_value[v] += 1
            # Spacing must keep the tallest stack inside its own row: with
            # 9 models bunched on 100, a wider fan grows past the row
            # pitch of 1.0 and the languages visually merge.
            ys.append(i + (k - (values.count(v) - 1) / 2) * 0.075)
            xs.append(v)
        ax.scatter(
            xs,
            ys,
            s=250,
            marker=LANG_MARKER[mode],
            color=COLORS[mode],
            edgecolor=CREAM,
            linewidth=1.8,
            zorder=3,
            alpha=0.95,
        )
        all_values.extend(values)
        mean = sum(values) / len(values)
        ax.plot(
            [mean, mean],
            [i - 0.34, i + 0.34],
            color=BROWN_900,
            linewidth=2.6,
            zorder=4,
            solid_capstyle="round",
        )
        ax.text(
            mean,
            i + 0.44,
            f"mean {mean:.1f}",
            ha="center",
            va="bottom",
            fontsize=BAR_LABEL_PT_SMALL - 1,
            color=BROWN_700,
            fontweight="bold",
        )
        ax.text(
            101.0,
            i,
            f"n={len(values)}",
            ha="left",
            va="center",
            fontsize=BAR_LABEL_PT_SMALL - 2,
            color=BROWN_300,
        )

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=TICK_PT_MEDIUM)
    ax.set_ylim(-1.35, len(rows) - 0.3)
    # Derived, not fixed at 86: a lower-scoring lineup would otherwise
    # be drawn outside the axes and silently vanish.
    floor = min(88, min(all_values, default=88) - 3)
    ax.set_xlim(floor, 102.6)
    ax.set_xticks([t for t in range(88, 101, 2) if t >= floor])
    ax.tick_params(axis="x", labelsize=TICK_PT_SMALL)
    ax.set_xlabel(
        "% solved (one dot per model)",
        fontsize=AXIS_LABEL_PT,
        color=BROWN_500,
        labelpad=12,
    )
    ax.axvline(x=100, color=BROWN_300, linestyle="--", linewidth=1.0, alpha=0.5)

    # The scale bar: converts any horizontal gap into problems. Sits in
    # the empty band below the lowest row, with its caption ABOVE the
    # arrow — below, it lands on the x tick labels.
    y0 = -0.95
    ax.annotate(
        "",
        xy=(100, y0),
        xytext=(100 - per_problem, y0),
        arrowprops=dict(arrowstyle="<->", color=BROWN_700, linewidth=2),
    )
    ax.text(
        100 - per_problem / 2,
        y0 + 0.12,
        f"1 problem = {per_problem:.1f} pp",
        ha="center",
        va="bottom",
        fontsize=BAR_LABEL_PT_SMALL - 1,
        color=BROWN_700,
        fontweight="bold",
    )
    _style_ax(ax)
    ax.set_title(
        "The frontier is at the ceiling",
        fontsize=TITLE_PT,
        fontweight="bold",
        pad=46,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.text(
        0.5,
        1.016,
        f"every model × language score — {n_gradeable} gradeable "
        "problems, so most gaps are one or two problems wide",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=SUBTITLE_PT,
        color=BROWN_500,
    )
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.94))
    _save(fig, output, background)


# ----------------------------------------------------------------------
# Slide 4 — what pass@1 cannot see
# ----------------------------------------------------------------------


def _problem_structure(version: str | None = None) -> dict[int, tuple[int, int]]:
    """Per tier: (total problems, gradeable problems)."""
    root = Path(__file__).resolve().parent.parent / "problems"
    gradeable = _gradeable_ids(version)
    out: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for pf in sorted(root.rglob("VB_*.json")):
        try:
            pid = json.loads(pf.read_text()).get("id", "")
            tier = int(pid.split("-")[1][1:])
        except (OSError, ValueError, IndexError):
            continue
        out[tier][0] += 1
        if pid in gradeable:
            out[tier][1] += 1
    return {t: (v[0], v[1]) for t, v in sorted(out.items())}


def _escape_cause(row: dict) -> str:
    """Why a program that cleared the static gate still failed.

    Three outcomes, and they are not equivalent. A runtime contract firing
    is the safety net WORKING — the prover could not discharge the
    obligation, so it was left as a runtime check and that check caught the
    violation. Non-termination is the gap Vera's `decreases` clause exists
    to close, so an accepted-but-diverging program is a real miss. Everything
    else is the honest limit of contracts-as-written: the program satisfied
    everything it promised and still computed the wrong answer.
    """
    msg = row.get("error_message") or ""
    if "condition violation" in msg.lower():
        return "runtime contract fired"
    if "timed out" in msg.lower():
        return "did not terminate"
    return "contracts satisfied, wrong output"


#: Ordered worst-to-least-worst for display, each with the colour that
#: carries its meaning: a fired contract is Vera working (green), a
#: divergence is a miss (red), a wrong answer under satisfied contracts is
#: the specification gap (brown).
CAUSE_ORDER = [
    ("contracts satisfied, wrong output", "BROWN"),
    ("did not terminate", "RED"),
    ("runtime contract fired", "GREEN"),
]


def render_coverage(
    results_dir: Path,
    version: str,
    output: Path,
    background: str = DEFAULT_BACKGROUND,
) -> None:
    """Where the static gate and the runtime disagree.

    This slide used to argue that pass@1 had a blind spot — the problems
    with no test cases — which contracts and a prover covered. Closing that
    gap retired the argument: every problem now carries test cases, so the
    old rendering degenerated to "0 of 60" with a 0% hero stat, which reads
    as Vera failing everything.

    The successor question is sharper and this data answers it directly.
    `vera check` and `vera run` are independent verdicts on the same
    program, so every (model, problem) pair is a two-by-two: the gate
    passed or not, the program was right or not. Two cells are agreement.
    The other two are the interesting ones — an ESCAPE (the gate passed,
    the program was still wrong) bounds what contracts miss, and a FALSE
    ALARM (the gate refused a working program) would bound what they cost.
    Reporting both is what keeps this honest rather than promotional: the
    escapes are named individually, with the cause of each.
    """
    rows_by_target = load_rows(results_dir, version, ["Vera"])
    if not rows_by_target:
        print(f"  coverage slide: no Vera results for {version} — skipping")
        return

    escapes: list[tuple[str, str, str]] = []  # (model, problem, cause)
    agree = false_alarms = graded = 0
    for (model, mode), rows in sorted(rows_by_target.items()):
        if mode != "Vera":
            continue
        for pid, r in sorted(best_by_problem(rows).items()):
            run = r.get("run_correct")
            if run is None:
                # Ungraded (a harness decline) is neither agreement nor
                # disagreement — there is no runtime verdict to compare
                # the gate against, so it must not enter the denominator.
                continue
            graded += 1
            gate = r.get("check_pass") is True
            if gate and run is False:
                escapes.append((model, pid, _escape_cause(r)))
            elif not gate and run is True:
                false_alarms += 1
            else:
                agree += 1

    if graded == 0:
        print("  coverage slide: no graded Vera rows — skipping")
        return
    esc_pct = 100 * len(escapes) / graded

    fig = plt.figure(figsize=(16, 9), dpi=180)
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.5, 1],
        wspace=0.10,
        top=0.60,
        left=0.055,
        right=0.965,
        bottom=0.10,
    )

    # --- left: the escapes, named ---
    # A list, not a chart. Six items against a 539 denominator have no
    # plottable shape — a bar would be a sliver next to a wall, and the
    # reader would learn less than from reading the six.
    ax = fig.add_subplot(gs[0, 0])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    colour = {"BROWN": BROWN_700, "RED": RED, "GREEN": GREEN}
    ax.text(
        0.0,
        0.98,
        f"The {len(escapes)} that cleared `vera check` and still failed:",
        fontsize=SUBTITLE_PT - 4,
        color=BROWN_900,
        fontweight="bold",
        va="top",
    )
    order = {c: i for i, (c, _) in enumerate(CAUSE_ORDER)}
    rows_sorted = sorted(escapes, key=lambda e: (order.get(e[2], 9), e[0], e[1]))
    y = 0.855
    for model, pid, cause in rows_sorted:
        tag = next((k for c, k in CAUSE_ORDER if c == cause), "BROWN")
        ax.text(
            0.0,
            y,
            pid,
            fontsize=TICK_PT_SMALL,
            color=BROWN_900,
            fontweight="bold",
            va="top",
            family="monospace",
        )
        ax.text(0.20, y, model, fontsize=TICK_PT_SMALL, color=BROWN_500, va="top")
        # The longest string on the slide. Set one step down and started
        # well left of the panel edge, so it cannot run under the hero
        # number in the right-hand column.
        ax.text(
            0.48,
            y,
            cause,
            fontsize=TICK_PT_SMALL - 2,
            color=colour[tag],
            va="top",
            fontweight="bold",
        )
        y -= 0.125

    # --- right: the two numbers that bound the claim ---
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis("off")
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.text(
        0.0,
        0.90,
        f"{esc_pct:.1f}%",
        fontsize=86,
        color=BROWN_900,
        fontweight="bold",
        va="top",
        family=FONT_HEADING,
    )
    ax2.text(
        0.0,
        0.60,
        "escaped the static gate",
        fontsize=SUBTITLE_PT - 3,
        color=BROWN_900,
        fontweight="bold",
        va="top",
    )
    ax2.text(
        0.0,
        0.525,
        f"{len(escapes)} of {graded} (model, problem) pairs\n"
        "compiled, satisfied their contracts,\nand were still wrong",
        fontsize=TICK_PT_SMALL,
        color=BROWN_500,
        va="top",
        linespacing=1.5,
    )
    ax2.text(
        0.0,
        0.30,
        str(false_alarms),
        fontsize=86,
        color=GREEN if false_alarms == 0 else RED,
        fontweight="bold",
        va="top",
        family=FONT_HEADING,
    )
    ax2.text(
        0.0,
        0.045,
        "working programs rejected",
        fontsize=SUBTITLE_PT - 3,
        color=BROWN_900,
        fontweight="bold",
        va="top",
    )
    ax2.text(
        0.0,
        -0.03,
        "the gate never refused code that ran correctly",
        fontsize=TICK_PT_SMALL,
        color=BROWN_500,
        va="top",
    )

    fig.text(
        0.5,
        0.955,
        "What the contracts cannot see",
        ha="center",
        va="top",
        fontsize=TITLE_PT,
        color=BROWN_900,
        fontweight="bold",
        family=FONT_HEADING,
    )
    fig.text(
        0.5,
        0.865,
        f"`vera check` and `vera run` are independent verdicts on the same "
        f"program — {graded} pairs across {len(rows_by_target)} models.\n"
        "Contracts bound what a program may do; they do not say everything "
        "it must do, so a few satisfy them and are still wrong.\n"
        "The cost of that gate is the number worth watching, and it is zero.",
        ha="center",
        va="top",
        fontsize=SUBTITLE_PT - 3,
        color=BROWN_500,
        linespacing=1.5,
    )
    _save(fig, output, background)


RENDERERS = {
    "refusal": render_refusal,
    "generation": render_generation,
    "saturation": render_saturation,
    "coverage": render_coverage,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--type",
        choices=[*RENDERERS, "all"],
        default="all",
        help="Which slide to render (default: all four).",
    )
    parser.add_argument(
        "--version",
        default=_default_version(),
        help="Bench version to plot (default: the installed vera-bench).",
    )
    parser.add_argument(
        "--results-dir", default="results", help="Directory of JSONL result files."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output PNG. Only valid with a single --type. "
        "Default: assets/vera-bench_slide_{type}.png",
    )
    parser.add_argument(
        "--background",
        choices=list(BACKGROUNDS),
        default=DEFAULT_BACKGROUND,
        help=f"Slide background colour (default: {DEFAULT_BACKGROUND}).",
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
        "--pair-only",
        action="store_true",
        help=(
            "Restrict the `generation` slide to the last two releases — the "
            "controlled comparison (same compiler, SKILL.md and problems). "
            "The full chain spans bench versions and so also carries "
            "ecosystem change."
        ),
    )
    parser.add_argument(
        "--include-ztd",
        action="store_true",
        help=(
            "Add Aver and AILANG to the `generation` slide. Off by "
            "default: between these two releases they move +2 and 0, so "
            "they add flat columns to a slide about direction."
        ),
    )
    args = parser.parse_args()
    if args.output and args.type == "all":
        parser.error("--output is only valid when --type is a single slide type")

    _slide.BARE = args.bare
    _slide_rcparams()
    results_dir = Path(args.results_dir)
    extra = {"modes": ALL_MODES} if args.include_ztd else {}
    gen_extra = {"span_versions": not args.pair_only}
    for t in list(RENDERERS) if args.type == "all" else [args.type]:
        out = (
            Path(args.output)
            if args.output
            else Path(f"assets/vera-bench_slide_{t}.png")
        )
        # `modes` applies to the two mode-axis slides. `refusal` always
        # shows every language (an empty ZTD column is its finding) and
        # `coverage` has no language axis at all.
        kwargs = extra if t in ("generation", "saturation") else {}
        if t == "generation":
            kwargs = {**kwargs, **gen_extra}
        RENDERERS[t](
            results_dir, args.version, out, background=args.background, **kwargs
        )


if __name__ == "__main__":
    main()
