"""Test-suite hermeticity.

The baseline/integration tests shell out to real toolchains. The Node one is
special: `run_typescript_baseline` invokes `npx tsx <file>` under a per-run
timeout, and the *first* `npx tsx` in a process resolves (and may fetch/compile)
the tsx package — on a cold CI runner that first call can approach the timeout
and flake the test, even though every subsequent call is sub-second. Locally the
cache is already warm, so it passes; in CI it's cold, so it fails. That
local-vs-CI divergence is the root cause behind the intermittent
`TestRunTypescriptBaseline` / `TestBaselinesCommand` timeouts.

Warming tsx once here, in (untimed) session setup, moves that cost out of every
timed test so they all run warm. Best-effort: if Node/npx isn't installed the
tests guard themselves, so a failed or absent warmup must never fail the suite.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


@pytest.fixture(scope="session", autouse=True)
def _warm_toolchains() -> None:
    npx = shutil.which("npx")
    if not npx:
        return
    try:
        # Resolve + prime the tsx package cache. The heavy first-call cost is
        # paid here, not inside a 30s-bounded baseline run.
        subprocess.run(
            [npx, "--yes", "tsx", "--version"],
            capture_output=True,
            timeout=180,
        )
    except Exception:
        pass  # warmup is an optimisation, never a gate
