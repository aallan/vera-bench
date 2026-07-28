#!/usr/bin/env python3
"""Re-grade a finished sweep from the code it stored, without re-running it.

A grading bug found after a sweep used to mean paying for the sweep again.
Since #109 every row records a `code_path`, so the model's actual output is
on disk and the verdict can simply be recomputed: same code, same problems,
a fixed harness. That turns a $100 overnight re-run into a few minutes of
local subprocesses, and it is the only reason the ADT-mapper fix could be
applied to the 0.0.18 results at all.

WHY IT RE-GRADES EVERY ROW, not just the ones that failed:

Re-grading only the rows a fix was expected to help is cherry-picking — it
would import every improvement while hiding any regression the same change
caused elsewhere. Grading the whole set under one harness version is both
the honest choice and a free regression test: rows the fix should not touch
must come back byte-identical, and this prints how many did.

What is replaced is only the VERDICT. Token counts, timings, the model's
identity and the code path are properties of the original run and are
carried through untouched, so a re-graded file still reports what that
sweep actually cost.

Dry run by default; `--apply` writes each file atomically.

    python scripts/regrade.py                        # census, changes nothing
    python scripts/regrade.py --apply                # rewrite the verdicts
    python scripts/regrade.py --language python --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vera_bench import __version__ as BENCH_VERSION  # noqa: E402
from vera_bench.results_path import version_slug  # noqa: E402
from vera_bench.runner import (  # noqa: E402
    _evaluate_ailang_code,
    _evaluate_aver_code,
    _evaluate_code,
    _evaluate_python_code,
    _evaluate_typescript_code,
)
from vera_bench.vera_runner import VeraRunner  # noqa: E402

#: The fields a grader owns. Everything else on a row describes the ORIGINAL
#: run — what it cost, how long it took, which model produced it — and must
#: survive re-grading untouched, or the file stops being a record of the
#: sweep that happened.
VERDICT_FIELDS = (
    "check_pass",
    "verify_pass",
    "verify_tier1",
    "verify_tier3",
    "run_correct",
    "tests_total",
    "tests_passed",
    "error_message",
)


#: Sandbox paths an evaluator bakes into its own error text. They differ on
#: every run by construction, so comparing them raw made a re-grade look
#: like it had changed 64 rows it had merely re-run — and writing those back
#: would replace the original sweep's message with a path from a run that
#: never happened.
_TMP_PATH = re.compile(r"/(?:private/)?(?:var|tmp)/[^\s'\"]*")


def _canonical(v: dict) -> dict:
    """A verdict with run-specific noise removed, for comparison only."""
    out = dict(v)
    msg = out.get("error_message")
    if isinstance(msg, str):
        out["error_message"] = _TMP_PATH.sub("<tmp>", msg)
    return out


def _load_problems() -> dict[str, dict]:
    """Every problem JSON, keyed by id — the same set the CLI loads."""
    root = Path(__file__).resolve().parent.parent
    out: dict[str, dict] = {}
    for pf in sorted((root / "problems").rglob("VB_*.json")):
        p = json.loads(pf.read_text(encoding="utf-8"))
        out[p["id"]] = p
    return out


def evaluate(row: dict, code: str, problem: dict, work: Path, vera: VeraRunner) -> dict:
    """Run the language's evaluator over stored code, as the sweep would."""
    lang = row.get("language") or "vera"
    attempt = int(row.get("attempt") or 1)
    if lang == "python":
        return _evaluate_python_code(code, problem, work, attempt)
    if lang == "typescript":
        return _evaluate_typescript_code(code, problem, work, attempt)
    if lang == "aver":
        return _evaluate_aver_code(code, problem, work, attempt)
    if lang == "ailang":
        return _evaluate_ailang_code(code, problem, work, attempt)
    return _evaluate_code(code, problem, vera, work, attempt)


def regrade_file(
    path: Path, results_dir: Path, problems: dict, vera: VeraRunner, workers: int
) -> tuple[list[dict], Counter]:
    """Return (new rows, tally of what moved) for one target file."""
    rows = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
    tally: Counter = Counter()

    def one(row: dict) -> dict:
        cp = row.get("code_path")
        problem = problems.get(row.get("problem_id"))
        if not cp or problem is None:
            # No stored code (an API error row never produced any) or a
            # problem that no longer exists. Left exactly as found: a row
            # this tool cannot re-derive must not be silently rewritten.
            tally["no-code"] += 1
            return row
        src = results_dir / cp
        if not src.exists():
            tally["missing-file"] += 1
            return row
        before = {k: row.get(k) for k in VERDICT_FIELDS}
        with tempfile.TemporaryDirectory(prefix="vb-regrade-") as tmp:
            try:
                fresh = evaluate(
                    row, src.read_text(encoding="utf-8"), problem, Path(tmp), vera
                )
            except Exception as exc:  # a grader crash is not a verdict
                tally["grader-error"] += 1
                row["regrade_error"] = f"{type(exc).__name__}: {exc}"[:200]
                return row
        new = dict(row)
        new.update({k: v for k, v in fresh.items() if k in VERDICT_FIELDS})
        after = {k: new.get(k) for k in VERDICT_FIELDS}
        if _canonical(before) == _canonical(after):
            # Same verdict, different sandbox path. Return the ORIGINAL row
            # so the file keeps the message the sweep actually recorded.
            tally["unchanged"] += 1
            return row
        else:
            tally["changed"] += 1
            was, now = _bucket(before), _bucket(after)
            tally[f"{was} -> {now}"] += 1
        return new

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            out = list(pool.map(one, rows))
    else:
        out = [one(r) for r in rows]
    return out, tally


def _bucket(v: dict) -> str:
    """Coarse verdict label, for reporting what a re-grade moved."""
    msg = v.get("error_message") or ""
    if msg.startswith("test wrapper unavailable"):
        return "declined"
    if v.get("run_correct") is True:
        return "solved"
    if v.get("run_correct") is False:
        return "wrong"
    return "ungraded"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--bench-version", default=BENCH_VERSION)
    ap.add_argument("--language", help="only this language's targets")
    ap.add_argument("--model", help="only targets for this model string")
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--apply", action="store_true", help="execute; else dry run")
    args = ap.parse_args()

    results_dir = Path(args.results_dir)
    pattern = f"*bench-{version_slug(args.bench_version)}*.jsonl"
    targets = sorted(
        p
        for p in results_dir.glob(pattern)
        if "-baseline" not in p.name
        and (not args.model or p.name.startswith(args.model.replace("/", "-")))
    )
    if not targets:
        print(f"no targets matching {pattern} in {results_dir}/")
        return 1

    problems = _load_problems()
    vera = VeraRunner()
    total: Counter = Counter()
    print(
        f"  {len(targets)} target(s), bench {args.bench_version}"
        f"{' — DRY RUN' if not args.apply else ''}\n"
    )

    for path in targets:
        head = json.loads(path.read_text().splitlines()[0])
        if args.language and head.get("language") != args.language:
            continue
        rows, tally = regrade_file(path, results_dir, problems, vera, args.parallel)
        total.update(tally)
        moved = tally["changed"]
        flag = "" if not moved else f"   {moved} changed"
        print(f"    {path.name[:64]:66} {tally['unchanged']:3} same{flag}", flush=True)
        if moved and args.apply:
            fd, tmp = tempfile.mkstemp(dir=str(results_dir), suffix=".jsonl")
            with os.fdopen(fd, "w") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
            os.replace(tmp, path)

    print("\n  transitions:")
    for k, v in sorted(total.items()):
        if "->" in k:
            print(f"    {k:28} {v}")
    print(
        f"\n  unchanged {total['unchanged']}   changed {total['changed']}"
        f"   no-code {total['no-code']}   grader-error {total['grader-error']}"
    )
    if not args.apply and total["changed"]:
        print("\n  dry run — re-run with --apply to write these verdicts")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
