#!/usr/bin/env python3
"""Surgically re-run only the *transiently failed* problems of a sweep
target, and splice the fresh rows back into the canonical results file —
instead of re-running all 60 problems to repair one timeout.

Why this is not the obvious one-liner: `vera-bench run` derives its output
filename from model·language·mode·versions (never the problem id) and
unlinks that file at startup (there is no resume). So a naive
`vera-bench run --problem VB-T3-002` would delete the 59 good rows to
rewrite one. The escape is `--output-dir`: point each re-run at a private
scratch dir, then merge its rows into the canonical file keyed by
`problem_id`.

Buckets (shared with sweep_status.py):
  transient  rate-limit / timeout / connection / empty content. Re-run
             as-is; the fault does not recur deterministically.
  length     finish_reason=length — output-budget wall. Re-running at the
             SAME budget hits the same wall, so length problems are only
             included with --include-length, and you should pass a bigger
             --max-tokens (forwarded to vera-bench run) alongside it.

Refusals and compile/runtime-error rows are real results and are never
re-run.

Examples:
    # Show what a target needs, cost-free (default is a dry run):
    python scripts/rerun_failed.py --model moonshot/kimi-k3 --mode full-spec

    # Actually repair the transient failures:
    python scripts/rerun_failed.py --model moonshot/kimi-k3 --mode full-spec --apply

    # Repair length walls too, with a bigger budget:
    python scripts/rerun_failed.py --model moonshot/kimi-k2.6 --mode spec-from-nl \
        --include-length --max-tokens 32000 --apply

Run this only on targets the sweep has finished (>=60 rows); it refuses an
in-flight file unless --force, to avoid racing the sweep's own writer.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep_status import _expected_problems, classify, load_rows  # noqa: E402

from vera_bench import __version__ as BENCH_VERSION  # noqa: E402
from vera_bench.results_path import version_slug  # noqa: E402


def canonical_basename_prefix(
    model: str, language: str, mode: str, bench_version: str
) -> str:
    """Reconstruct the leading part of the filename cli.py builds, up to
    (not including) the COMPILER version tag — enough to glob for one file.

    The bench version has to be in the prefix. `results/` accumulates every
    release side by side, so a prefix ending at `-bench-` matches one file
    per era and the glob goes ambiguous the moment a second release lands —
    which is how this stopped working on 0.0.18 with 0.0.16 still on disk.
    The compiler segment stays a wildcard because a target's Vera/Aver/
    AILANG version is whatever produced it, not whatever is installed now.
    """
    parts = [model.replace("/", "-")]
    if language != "vera":
        parts.append(language)
    if language == "vera" and mode != "full-spec":
        parts.append(mode)
    return "-".join(parts) + f"-bench-{version_slug(bench_version)}"


def find_canonical(
    results_dir: str, model: str, language: str, mode: str, bench_version: str
) -> str:
    prefix = canonical_basename_prefix(model, language, mode, bench_version)
    # The version token has to end at a separator. `prefix + "*"` let
    # 0.0.18 match `bench-0-0-180-...`, so a repair aimed at one release
    # could splice fresh rows into a different one's file. After the
    # bench segment a name either continues with a compiler segment or
    # ends, so those are exactly the two shapes to accept.
    hits = sorted(
        set(glob.glob(os.path.join(results_dir, prefix + "-*.jsonl")))
        | set(glob.glob(os.path.join(results_dir, prefix + ".jsonl")))
    )
    if not hits:
        sys.exit(
            f"no results file matching {prefix}* in {results_dir}/\n"
            f"(bench version {bench_version} — pass --bench-version to repair "
            f"an older era)"
        )
    if len(hits) > 1:
        joined = "\n  ".join(os.path.basename(h) for h in hits)
        sys.exit(f"ambiguous — {len(hits)} files match {prefix}*:\n  {joined}")
    return hits[0]


def failed_pids(rows: list[dict], include_length: bool) -> list[str]:
    wanted = {"transient", "length"} if include_length else {"transient"}
    seen: dict[str, None] = {}  # ordered set
    for r in rows:
        msg = r.get("error_message")
        if msg and classify(msg) in wanted:
            seen.setdefault(r["problem_id"], None)
    return list(seen)


def rerun_one(
    model: str,
    language: str,
    mode: str,
    pid: str,
    extra: list[str],
    scratch: str,
    timeout: int,
) -> list[dict]:
    cmd = [
        "vera-bench",
        "run",
        "--model",
        model,
        "--problem",
        pid,
        "--output-dir",
        scratch,
    ]
    if language != "vera":
        cmd += ["--language", language]
    if language == "vera" and mode != "full-spec":
        cmd += ["--mode", mode]
    cmd += extra
    print(f"  $ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        sys.exit(f"re-run of {pid} exceeded {timeout}s — not splicing")
    except subprocess.CalledProcessError as e:
        sys.exit(f"re-run of {pid} exited {e.returncode} — not splicing")
    produced = glob.glob(os.path.join(scratch, "*.jsonl"))
    if not produced:
        sys.exit(f"re-run of {pid} produced no output file in {scratch}")
    rows = load_rows(produced[0])
    # Guard the splice: only rows that are non-empty AND all belong to this
    # problem may replace the canonical group. Empty or mismatched output must
    # abort before splice() overwrites good data.
    if not rows:
        sys.exit(f"re-run of {pid} produced an empty file — not splicing")
    stray = {r.get("problem_id") for r in rows} - {pid}
    if stray:
        sys.exit(f"re-run of {pid} returned rows for {sorted(stray)} — not splicing")
    return rows


def copy_code(scratch: str, canonical: str, pid: str) -> None:
    """Bring a re-run problem's stored code across with its rows.

    code_path strings are relative to the results dir and the filename
    stem carries no directory, so a spliced row would otherwise resolve
    to the ORIGINAL failed attempt's file under the canonical tree —
    fresh rows, stale code, under identical names. Runs inside the
    per-pid scratch's lifetime; splice() happens after it is deleted.
    """
    # The scratch run names its output with the CURRENT bench and
    # compiler versions, which need not match the canonical file being
    # repaired. Deriving the stem from the canonical name silently found
    # nothing and left the spliced row pointing at the original failed
    # attempt's code, so read whatever stem the scratch actually wrote.
    stem = os.path.splitext(os.path.basename(canonical))[0]
    code_root = os.path.join(scratch, "code")
    if not os.path.isdir(code_root):
        return
    scratch_stems = os.listdir(code_root)
    src = os.path.join(code_root, stem)
    if not os.path.isdir(src):
        if len(scratch_stems) != 1:
            return
        src = os.path.join(code_root, scratch_stems[0])
    dest = os.path.join(os.path.dirname(canonical), "code", stem)
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(src):
        if name.split("_attempt")[0] == pid:
            shutil.copy2(os.path.join(src, name), os.path.join(dest, name))


def splice(canonical: str, fresh_by_pid: dict[str, list[dict]]) -> None:
    """Replace each re-run problem's row group in-place, preserving the
    original first-seen order, and write atomically."""
    order: list[str] = []
    groups: dict[str, list[dict]] = {}
    for r in load_rows(canonical):
        pid = r["problem_id"]
        if pid not in groups:
            groups[pid] = []
            order.append(pid)
        groups[pid].append(r)
    for pid, rows in fresh_by_pid.items():
        if pid not in groups:
            order.append(pid)
        groups[pid] = rows
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(canonical), suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        for pid in order:
            for r in groups[pid]:
                fh.write(json.dumps(r) + "\n")
    os.replace(tmp, canonical)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--model", required=True, help="CLI model string, e.g. moonshot/kimi-k3"
    )
    ap.add_argument("--language", default="vera")
    ap.add_argument(
        "--mode", default="full-spec", help="full-spec | spec-from-nl (vera only)"
    )
    ap.add_argument("--results-dir", default="results")
    ap.add_argument(
        "--bench-version",
        default=BENCH_VERSION,
        help="which release's results to repair (default: installed version). "
        "results/ holds every era side by side, so this is what keeps the "
        "target unambiguous",
    )
    ap.add_argument(
        "--include-length",
        action="store_true",
        help="also re-run finish_reason=length problems (pair with --max-tokens)",
    )
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="forwarded to vera-bench run (needed to clear length walls)",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="per-problem re-run timeout (s); a stall aborts before splice",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="splice even a file that does not yet cover every problem",
    )
    ap.add_argument(
        "--apply", action="store_true", help="execute; without it, dry-run only"
    )
    args = ap.parse_args()

    canonical = find_canonical(
        args.results_dir, args.model, args.language, args.mode, args.bench_version
    )
    rows = load_rows(canonical)
    print(f"target: {os.path.basename(canonical)}  ({len(rows)} rows)")

    # Coverage is counted in unique problem ids, not rows: a fix attempt
    # emits a second row for the same problem, so a file can reach 60 rows
    # while still missing problems the sweep has not written yet. Counting
    # rows called that finished and spliced into a file still being
    # written. Same denominator `sweep_status.verdict` uses.
    covered = len({r.get("problem_id") for r in rows})
    if covered < _expected_problems() and not args.force:
        sys.exit(
            f"file covers {covered}/{_expected_problems()} problems — looks "
            "in-flight; wait for the sweep or pass --force"
        )

    pids = failed_pids(rows, args.include_length)
    if not pids:
        print(
            "nothing to re-run (no transient"
            + ("/length" if args.include_length else "")
            + " failures)"
        )
        return
    print(f"would re-run {len(pids)} problem(s): {', '.join(pids)}")

    extra: list[str] = []
    if args.max_tokens is not None:
        extra += ["--max-tokens", str(args.max_tokens)]
    if args.include_length and args.max_tokens is None:
        print("  ! --include-length without --max-tokens will likely hit the same wall")

    if not args.apply:
        print("\ndry run — re-run with --apply to execute and splice")
        return

    fresh_by_pid: dict[str, list[dict]] = {}
    with tempfile.TemporaryDirectory(prefix="vb-rerun-") as base:
        for pid in pids:
            scratch = os.path.join(base, pid)
            os.makedirs(scratch)
            fresh_by_pid[pid] = rerun_one(
                args.model, args.language, args.mode, pid, extra, scratch, args.timeout
            )
            copy_code(scratch, canonical, pid)
    splice(canonical, fresh_by_pid)
    print(
        f"\nspliced {len(fresh_by_pid)} problem(s) into {os.path.basename(canonical)}"
    )
    print("re-run scripts/sweep_status.py to confirm it now reads clean")


if __name__ == "__main__":
    main()
