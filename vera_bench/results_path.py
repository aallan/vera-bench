"""Where a sweep target's results live — one construction, one source.

A result filename encodes the target AND every version that produced it:
`claude-fable-5-bench-0-0-18-vera-0-1-8.jsonl`. That makes the file
self-describing, which is why the sweep can tell a finished target from
an absent one just by looking.

It also makes the name a CONTRACT between two programs. `vera-bench run`
writes it; `scripts/run_sweep.sh` predicts it, to decide whether a target
is already done. When the two disagree the failure is silent and
expensive: run_sweep.sh spelled the bench version into its own copy of
the pattern, so on 0.0.18 it waited for a file that would never appear,
declared every successful target dirty, and retried the entire matrix to
the limit — pro tier included — before reporting total failure over
perfectly good data.

So the construction lives here, once, and both callers use it. The shell
reaches it through `python -m vera_bench.results_path`, which prints the
name for one target — a subprocess per target is nothing against an LLM
call, and it removes the possibility of drift rather than documenting it.
"""

from __future__ import annotations

import argparse
import sys


def version_slug(version: str) -> str:
    """`0.0.18` -> `0-0-18`, the spelling filenames use."""
    return version.replace(".", "-")


def result_filename(
    model: str,
    bench_version: str,
    language: str = "vera",
    mode: str = "full-spec",
    vera_version: str | None = None,
    aver_version: str | None = None,
    ailang_version: str | None = None,
) -> str:
    """The JSONL filename `vera-bench run` writes for one target.

    A target carries only the compiler version that GRADED it — Vera for
    the two Vera modes, Aver for Aver, AILANG for AILANG, and none at all
    for Python and TypeScript, which need no compiler of their own. That
    rule lives here rather than in the caller: leaving it to callers is
    how a Python result could pick up whichever other compiler happened
    to be installed on the sweep machine. `unknown` and empty are
    likewise omitted, since an unmatchable name is worse than a short one.
    """
    parts = [model.replace("/", "-")]
    if language != "vera":
        parts.append(language)
    if language == "vera" and mode != "full-spec":
        parts.append(mode)
    parts.append(f"bench-{version_slug(bench_version)}")
    relevant = {
        "vera": ("vera", vera_version),
        "aver": ("aver", aver_version),
        "ailang": ("ailang", ailang_version),
    }.get(language)
    if relevant:
        label, value = relevant
        if value and value != "unknown":
            parts.append(f"{label}-{version_slug(value)}")
    return f"{'-'.join(parts)}.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Print one target's filename, for the shell to consume."""
    ap = argparse.ArgumentParser(
        prog="python -m vera_bench.results_path",
        description="Print the result filename vera-bench run would write.",
    )
    ap.add_argument("--model", required=True)
    ap.add_argument("--bench-version", required=True)
    ap.add_argument("--language", default="vera")
    ap.add_argument("--mode", default="full-spec")
    ap.add_argument("--vera-version")
    ap.add_argument("--aver-version")
    ap.add_argument("--ailang-version")
    a = ap.parse_args(argv)
    print(
        result_filename(
            a.model,
            a.bench_version,
            a.language,
            a.mode,
            a.vera_version,
            a.aver_version,
            a.ailang_version,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
