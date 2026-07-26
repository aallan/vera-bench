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
- `coverage`   — what pass@1 structurally cannot see: the 24 of 60
                 problems with no test cases, and Vera's check/verify
                 rates over the full 60.

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
from scripts.sweep_status import REFUSAL  # noqa: E402

ALL_MODES = ["Vera", "Vera NL", "Python", "TypeScript", "Aver", "AILANG"]

# The Anthropic flagship line, oldest first, as (bench version, display).
# Cross-version by design: Opus 4 was only ever swept under bench 0.0.9,
# so the trajectory cannot be read out of a single results generation.
# The arithmetic is sound: 0.0.9 covered the same 36 graded problems and
# every one carries a real verdict, so no score is depressed by test cases
# that only existed later. The ATTRIBUTION is what is confounded. Three
# things moved between the first and second links, all of them Vera-side:
# the compiler and its stdlib (0.0.112 -> 0.1.7), SKILL.md (fetched at
# runtime, so never pinned), and the problem definitions. That step
# therefore measures the ecosystem improving as much as the model — and a
# stdlib expansion lands hardest on Tier 2, which tests built-in function
# discovery. Only the 4.8 -> 5 step is controlled: same bench version,
# compiler, prompt and problems. Python and TypeScript touch none of the
# Vera toolchain, which is what makes their line the control.
GENERATION_CHAIN = [
    ("0.0.9", "Claude Opus 4"),
    ("0.0.16", "Claude Opus 4.8"),
    ("0.0.16", "Claude Opus 5"),
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

    Gradeability decides which verdict applies. 24 of the 60 problems
    carry no test cases, so `run_correct` is None for them by
    construction — never because anything failed. Testing `run_correct is
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
            if not REFUSAL.search(row.get("error_message") or ""):
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
        "solved = output matched the test cases, or — for the 24 problems "
        "with no test cases — the code compiled and passed its contracts.     "
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
    chain = GENERATION_CHAIN if span_versions else GENERATION_CHAIN[-2:]
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
        for k, v in enumerate(vals):
            # Fill deepens along the chain, so the reading order is
            # visible without consulting the legend.
            frac = k / (n_pts - 1) if n_pts > 1 else 1.0
            ax.scatter(
                [xi + dxs[k]],
                [v],
                s=460,
                facecolor=COLORS[mode] if k == n_pts - 1 else "white",
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
    ax.set_title(
        "One generation later"
        if len(points) < 3
        else "Three flagships, one trajectory",
        fontsize=TITLE_PT,
        fontweight="bold",
        pad=46,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    ax.text(
        0.5,
        1.016,
        " → ".join(d for d, _r, _m in points)
        + " — the Vera line rises at every step;"
        + " Python and TypeScript peak and fall back",
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
                markerfacecolor=BROWN_500 if k == len(points) - 1 else "white",
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
        # The one confound, stated on the slide rather than in a footnote
        # nobody reads: the Vera toolchain changed under the first link.
        fig.text(
            0.5,
            0.028,
            "Opus 4 ran under Vera 0.0.112, the later two under 0.1.7 — same "
            "36 graded problems, every one with a verdict in both eras.\n"
            "But the compiler, its stdlib and SKILL.md all moved between the "
            "first two points: that step measures the ecosystem improving as "
            "much as the model.\n"
            "Opus 4.8 → Opus 5 is the controlled step — identical toolchain, "
            "prompt and problems. Python and TypeScript use no Vera toolchain.",
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


def render_coverage(
    results_dir: Path,
    version: str,
    output: Path,
    background: str = DEFAULT_BACKGROUND,
) -> None:
    """The benchmark's blind spot, and the metric that covers it.

    pass@1 needs expected output to compare against, so it can only see
    the problems that have test cases. The ones it cannot see are not a
    random sample — they are concentrated in the tiers built around ADTs,
    exhaustive match and effect handlers, which is precisely the machinery
    Vera exists to check. This slide states that plainly and then shows
    check@1 / verify, which do cover all 60.
    """
    structure = _problem_structure(version)
    tiers_n = sorted(structure)
    if not tiers_n:
        print("  coverage slide: no problems found under problems/ — skipping")
        return
    rows_by_target = load_rows(results_dir, version, ["Vera"])
    gradeable = _gradeable_ids(version)

    # Restricted to the problems pass@1 CANNOT see. Rates over all 60
    # would merely restate the headline chart on a second axis; the claim
    # worth making is about the invisible 24 specifically. Averaged
    # across models, so this is "the typical frontier model".
    check_pcts: list[float] = []
    verify_pcts: list[float] = []
    n_models = 0
    for (model, mode), rows in rows_by_target.items():
        if mode != "Vera":
            continue
        best = best_by_problem(rows)
        blind = {p: r for p, r in best.items() if p not in gradeable}
        if not blind:
            continue
        # Only after the blind check: a target with nothing to measure
        # contributes no percentage, so it must not enlarge the mean's
        # reported denominator either.
        n_models += 1
        check_pcts.append(
            100 * sum(1 for r in blind.values() if r.get("check_pass")) / len(blind)
        )
        verified = [r for r in blind.values() if r.get("verify_pass") is not None]
        if verified:
            verify_pcts.append(
                100 * sum(1 for r in verified if r.get("verify_pass")) / len(verified)
            )
    check_avg = sum(check_pcts) / len(check_pcts) if check_pcts else 0.0
    verify_avg = sum(verify_pcts) / len(verify_pcts) if verify_pcts else 0.0

    fig = plt.figure(figsize=(16, 9), dpi=180)
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.15, 1],
        wspace=0.18,
        # Axes top sits low enough that the legend — anchored just above
        # it — clears the two-line subtitle instead of butting against it.
        top=0.60,
        left=0.075,
        right=0.97,
        bottom=0.13,
    )

    # --- left: what pass@1 can and cannot see ---
    ax = fig.add_subplot(gs[0, 0])
    y = np.arange(len(tiers_n))
    grad = [structure[t][1] for t in tiers_n]
    ungr = [structure[t][0] - structure[t][1] for t in tiers_n]
    ax.barh(
        y,
        grad,
        0.62,
        color=GREEN,
        alpha=0.88,
        edgecolor=CREAM,
        linewidth=1.5,
        label="graded by pass@1 (has test cases)",
    )
    ax.barh(
        y,
        ungr,
        0.62,
        left=grad,
        color=BROWN_300,
        alpha=0.55,
        edgecolor=CREAM,
        linewidth=1.5,
        hatch="//",
        label="can not be output-tested (no test cases)",
    )
    for yi, g, u in zip(y, grad, ungr):
        ax.text(
            g / 2,
            yi,
            str(g),
            ha="center",
            va="center",
            fontsize=17,
            fontweight="bold",
            color="white",
        )
        if u:
            ax.text(
                g + u / 2,
                yi,
                str(u),
                ha="center",
                va="center",
                fontsize=17,
                fontweight="bold",
                color=BROWN_900,
            )
    ax.set_yticks(y)
    ax.set_yticklabels([f"Tier {t}" for t in tiers_n], fontsize=TICK_PT_SMALL)
    ax.invert_yaxis()
    ax.set_xlabel("problems", fontsize=AXIS_LABEL_PT - 2, color=BROWN_500)
    ax.set_xlim(0, max(structure[t][0] for t in tiers_n) + 1)
    ax.tick_params(axis="x", labelsize=TICK_PT_SMALL - 2)
    _style_ax(ax)
    # Above the axes, right-aligned. Inside, it lands on the shortest
    # tier's segment labels — the numbers the panel exists to show —
    # and below, it falls off the bottom of the canvas.
    ax.legend(
        loc="lower right",
        bbox_to_anchor=(1.0, 1.01),
        ncol=1,
        fontsize=LEGEND_PT - 5,
        framealpha=0.92,
        edgecolor=BROWN_300,
    )

    # --- right: hero stats on the invisible problems ---
    # Deliberately not a chart. Every value here is ~100, and five
    # near-identical full-height bars communicate nothing a number does
    # not — the bar's own length stops being informative once the whole
    # series sits on the ceiling.
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis("off")
    n_blind = sum(structure[t][0] - structure[t][1] for t in tiers_n)
    ax2.text(
        0.5,
        1.02,
        f"on those {n_blind} untestable problems,\nVera still grades every one:",
        transform=ax2.transAxes,
        ha="center",
        va="top",
        fontsize=SUBTITLE_PT,
        color=BROWN_700,
        linespacing=1.4,
    )
    for i, (val, label, sub) in enumerate(
        (
            (check_avg, "check@1", "compiled and passed\nits contracts"),
            (verify_avg, "verify", "discharged by\nthe Z3 prover"),
        )
    ):
        yy = 0.64 - i * 0.38
        # Left-anchored, not centred: Georgia's '%' is far wider than a
        # digit, so a centred number silently grows rightwards into the
        # label column and overprints it.
        ax2.text(
            0.0,
            yy,
            f"{val:.0f}%",
            transform=ax2.transAxes,
            ha="left",
            va="center",
            fontsize=74,
            fontweight="bold",
            color=GREEN,
            fontfamily=FONT_HEADING,
        )
        ax2.text(
            0.60,
            yy + 0.075,
            f"Vera {label}",
            transform=ax2.transAxes,
            ha="left",
            va="center",
            fontsize=24,
            fontweight="bold",
            color=BROWN_900,
        )
        ax2.text(
            0.60,
            yy - 0.055,
            sub,
            transform=ax2.transAxes,
            ha="left",
            va="center",
            fontsize=16,
            color=BROWN_500,
            linespacing=1.35,
        )
    ax2.text(
        0.5,
        -0.06,
        f"mean across {n_models} models, Vera full-spec",
        transform=ax2.transAxes,
        ha="center",
        va="center",
        fontsize=15,
        color=BROWN_300,
    )

    total = sum(structure[t][0] for t in tiers_n)
    n_grad = sum(structure[t][1] for t in tiers_n)
    fig.suptitle(
        "What pass@1 cannot see",
        fontsize=TITLE_PT,
        fontweight="bold",
        y=0.955,
        fontfamily=FONT_HEADING,
        color=BROWN_900,
    )
    fig.text(
        0.5,
        0.865,
        f"{total - n_grad} of {total} problems have no test cases — not an oversight.\n"
        "Their entry points take or produce shapes the harness cannot "
        "yet grade through `vera run`.\n"
        "They are the ADT, match and effect problems — exactly what "
        "contracts and a prover are for.",
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
    parser.add_argument("--version", default="0.0.16", help="Bench version to plot.")
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
