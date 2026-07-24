#!/usr/bin/env python3
"""Live status of an in-progress full-matrix sweep — the visibility the
tee'd logs can't give.

`vera-bench run` renders progress with `rich`, which blanks itself when
stdout is not a TTY, so `run_sweep.sh`'s per-target `*.log` files capture
only the banner. The JSONL result rows are the real ground truth. This
script reads them and classifies each target's error rows into buckets
that imply *different remedies* — a distinction `run_sweep.sh`'s single
`is_clean` gate flattens into one "dirty":

  refusal   the model declined (`stop_reason=refusal` / "no text block").
            A real verdict. The file is COMPLETE — retrying re-asks a
            question already answered and would overwrite good data.
  length    `finish_reason=length` — the model exhausted its output
            budget. Deterministic; a blind retry hits the same wall.
            Remedy is a higher --max-tokens, not a re-run.
  transient rate-limit / timeout / connection / overload / empty content.
            The only bucket a blind retry actually fixes.

Usage:
    python scripts/sweep_status.py                 # census of results/
    python scripts/sweep_status.py --dir results   # explicit dir
    watch -n30 python scripts/sweep_status.py      # live dashboard
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re

# Ordered: first match wins, so length (which also says "empty content")
# is classified as a token wall, not a transient blip.
REFUSAL = re.compile(r"stop_reason=refusal|no text block", re.I)
LENGTH = re.compile(r"finish_reason=length", re.I)
TRANSIENT = re.compile(
    r"rate.?limit|429|timed out|timeout|killed by signal|connection|"
    r"overloaded|empty content|503|529|API error",
    re.I,
)


def _expected_problems() -> int:
    """Full problem count — the coverage a complete target must reach. Unique
    problem ids, not rows, because one problem can emit two rows (fix attempt)."""
    root = pathlib.Path(__file__).resolve().parent.parent
    return len(list(root.glob("problems/**/VB_*.json"))) or 60


def classify(msg: str) -> str:
    if REFUSAL.search(msg):
        return "refusal"
    if LENGTH.search(msg):
        return "length"
    if TRANSIENT.search(msg):
        return "transient"
    return "other"


def load_rows(path: str) -> list[dict]:
    rows = []
    # A sweep writes concurrently; tolerate a half-flushed final line.
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def verdict(n_solved: int, expected: int, buckets: dict[str, int]) -> tuple[str, str]:
    """Return (category, human-readable detail).

    Completeness is measured in unique problems solved, not rows: one problem
    can emit two rows (attempt 1 + a fix), so a partial run can reach 60 rows
    while still missing problems. Only two buckets mean the sweep lacks a
    trustworthy answer and should act: `transient` (blind retry fixes) and
    `length` (retry needs a bigger budget). A refusal or a compile/runtime
    error is a *real result* — complete, must not be re-run. Refusals are
    still counted in the detail because they are the talk's "model declined"
    story."""
    if n_solved < expected:
        return "in-flight", f"in-flight ({n_solved}/{expected})"
    # A file can need BOTH a plain re-run and a bigger budget; show both so
    # a "RE-RUN" verdict never hides that --max-tokens is also required.
    actions = []
    if buckets["transient"]:
        actions.append(f"RE-RUN {buckets['transient']} transient")
    if buckets["length"]:
        actions.append(f"RAISE --max-tokens {buckets['length']} length")
    if actions:
        cat = "re-run" if buckets["transient"] else "raise-tokens"
        return cat, " + ".join(actions)
    if buckets["refusal"]:
        return "complete", f"complete — keep ({buckets['refusal']} refusal)"
    return "complete", "complete"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="results")
    ap.add_argument("--glob", default="*bench-0-0-16*.jsonl")
    ap.add_argument("--expect", type=int, default=40, help="target file count")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, args.glob)))
    expected = _expected_problems()
    # oth = error rows classify() left unclassified. These are overwhelmingly
    # real compile/runtime failures (the harness prefixes genuine infra with
    # "API error", which classify routes to transient), so they do not force a
    # re-run — but the count is shown so a missed pattern is never invisible.
    hdr = f"{'file':<58} {'rows':>4} {'ref':>3} {'len':>3} {'trn':>3} {'oth':>3}"
    print(f"{hdr}  verdict")
    print("-" * 108)
    tally: dict[str, int] = {}
    for f in files:
        rows = load_rows(f)
        buckets = {"refusal": 0, "length": 0, "transient": 0, "other": 0}
        for r in rows:
            msg = r.get("error_message")
            if msg:
                buckets[classify(msg)] += 1
        n_solved = len({r["problem_id"] for r in rows if r.get("problem_id")})
        cat, detail = verdict(n_solved, expected, buckets)
        tally[cat] = tally.get(cat, 0) + 1
        print(
            f"{os.path.basename(f):<58} {len(rows):>4} "
            f"{buckets['refusal']:>3} {buckets['length']:>3} "
            f"{buckets['transient']:>3} {buckets['other']:>3}  {detail}"
        )

    print()
    n = len(files)
    summary = "  ".join(f"{v} {k}" for k, v in sorted(tally.items()))
    print(summary)
    print(f"{n}/{args.expect} target files present", end="")
    if n < args.expect:
        # A target is absent either because it hasn't started OR because the
        # sweep is re-running it right now: vera-bench run unlinks the file at
        # startup (no resume), so it vanishes until the first row lands. The
        # count is therefore not monotonic across polls.
        print(f"  ({args.expect - n} absent — not-started or mid-re-run)", end="")
    print()


if __name__ == "__main__":
    main()
