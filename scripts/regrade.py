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

WHY IT REFUSES A TARGET ANOTHER COMPILER GRADED:

"Same code, same problems, a fixed harness" holds only while the
compiler holds too, and nothing held it. Vera 0.1.9 made redeclaring a
built-in effect an error, where under 0.1.8 a bare `throw` needed the
declaration, so re-grading the 0.0.18 files with 0.1.9 installed would
fail programs that were correct when graded, and `--apply` would write
that over published numbers. A target whose name records a compiler
version other than the installed one is skipped and reported instead.
`--allow-compiler-drift` grades it anyway, for a deliberate cross-version
experiment. Python and TypeScript targets are never skipped, since no
compiler of ours grades them.

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
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vera_bench import __version__ as BENCH_VERSION  # noqa: E402
from vera_bench.cli import _parse_version_banner  # noqa: E402
from vera_bench.results_path import (  # noqa: E402
    GRADING_COMPILER,
    compiler_segment,
    recorded_compiler_version,
    version_slug,
)
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


def _same_verdict(before: dict, after: dict) -> bool:
    """Whether two verdicts agree once run-specific noise is discounted.

    Beyond the sandbox path itself, messages are truncated to a fixed
    length — so a path of a different length moves the CUT, and the same
    advice comes back ending "at compile t" instead of "at compile time."
    Every non-message field must still match exactly; only the message is
    allowed to be a truncation of its counterpart. Without this a re-grade
    reports dozens of rows as changed when it has merely re-run them, and
    writing them back would replace the sweep's own message with one from
    a run that never happened.

    Comparing both strings over the shorter one's length IS a prefix test,
    and `bool(n)` is deliberate rather than a typo. An empty string is a
    prefix of everything, so `startswith` would call a message appearing
    or disappearing "the same verdict" — which it is not.

        ma        mb        here     startswith()
        'ab'      'abc'     True     True
        'abc'     'abd'     False    False
        ''        'abc'     False    True    <- must be False
    """
    ca, cb = _canonical(before), _canonical(after)
    if ca == cb:
        return True
    if {k: v for k, v in ca.items() if k != "error_message"} != {
        k: v for k, v in cb.items() if k != "error_message"
    }:
        return False
    ma = ca.get("error_message") or ""
    mb = cb.get("error_message") or ""
    n = min(len(ma), len(mb))
    return bool(n) and ma[:n] == mb[:n]


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
        if _same_verdict(before, after):
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


def installed_versions(vera: VeraRunner) -> dict[str, str]:
    """Each grading compiler's version, read as `vera-bench run` reads it.

    That is `vera version` for Vera, and the first line of `--version`
    through the CLI's own `_parse_version_banner` for Aver and AILANG. The
    drift check compares against the version a filename recorded, so
    reading it any other way could call the right compiler the wrong one.
    A compiler that is missing, or will not say, is `unknown`.
    """
    versions = {"vera": vera.version()}
    for compiler in ("aver", "ailang"):
        try:
            proc = subprocess.run(
                [compiler, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            versions[compiler] = "unknown"
            continue
        versions[compiler] = (
            _parse_version_banner(proc.stdout) if proc.returncode == 0 else "unknown"
        )
    return versions


def compiler_drift(
    filename: str, language: str, installed: dict[str, str]
) -> str | None:
    """Why a target must not be re-graded here, or None if it may be.

    A target may be re-graded only by the compiler that graded it, and its
    name records which one that was. The check builds the segment the
    installed compiler would have written and asks whether the name ends
    with it, so it cannot disagree with how names are made. An installed
    version that is `unknown` builds no segment and so never matches: a
    re-grade that cannot name its compiler cannot claim it is the same one.
    """
    compiler = GRADING_COMPILER.get(language)
    if compiler is None:
        return None  # Python and TypeScript: no compiler of ours grades them
    have = installed.get(compiler, "unknown")
    segment = compiler_segment(language, have)
    if segment and filename.endswith(f"-{segment}.jsonl"):
        return None
    had = recorded_compiler_version(filename, language)
    graded = f"{compiler} {had}" if had else f"an unrecorded {compiler}"
    return f"graded by {graded}, installed {compiler} {have}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--bench-version", default=BENCH_VERSION)
    ap.add_argument("--language", help="only this language's targets")
    ap.add_argument("--model", help="only targets for this model string")
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument(
        "--allow-compiler-drift",
        action="store_true",
        help="also re-grade targets that a different compiler version graded, "
        "for a deliberate cross-version experiment",
    )
    ap.add_argument("--apply", action="store_true", help="execute; else dry run")
    args = ap.parse_args(argv)

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
    installed = installed_versions(vera)
    total: Counter = Counter()
    print(
        f"  {len(targets)} target(s), bench {args.bench_version}"
        f"{' — DRY RUN' if not args.apply else ''}"
    )
    print("  installed: " + ", ".join(f"{c} {v}" for c, v in installed.items()) + "\n")

    for path in targets:
        head = json.loads(path.read_text().splitlines()[0])
        if args.language and head.get("language") != args.language:
            continue
        drift = compiler_drift(path.name, head.get("language") or "vera", installed)
        if drift and not args.allow_compiler_drift:
            total["compiler-drift"] += 1
            print(f"    {path.name[:64]:66} skipped: {drift}", flush=True)
            continue
        if drift:
            print(f"    {path.name[:64]:66} drift allowed: {drift}", flush=True)
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
        f"   compiler-drift {total['compiler-drift']}"
    )
    if total["compiler-drift"]:
        print(
            f"\n  {total['compiler-drift']} target(s) skipped: graded by a "
            "different compiler version than the one installed. Install that "
            "version to re-grade them, or pass --allow-compiler-drift to grade "
            "them with this one."
        )
    if not args.apply and total["changed"]:
        print("\n  dry run — re-run with --apply to write these verdicts")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
