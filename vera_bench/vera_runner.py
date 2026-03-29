"""Subprocess wrapper for the Vera CLI (check, verify, run)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def _vera_bin() -> str:
    custom = os.environ.get("VERA_PATH")
    if custom:
        return custom
    found = shutil.which("vera")
    if found:
        return found
    raise FileNotFoundError(
        "vera not found on PATH. Install with: pip install git+https://github.com/aallan/vera.git"
    )


@dataclass
class CheckResult:
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    diagnostics: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)


@dataclass
class VerifyResult:
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    tier1_verified: int = 0
    tier3_runtime: int = 0
    total: int = 0
    diagnostics: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str


class VeraRunner:
    def __init__(
        self, timeout_check: int = 30, timeout_verify: int = 60, timeout_run: int = 30
    ):
        self.vera = _vera_bin()
        self.timeout_check = timeout_check
        self.timeout_verify = timeout_verify
        self.timeout_run = timeout_run

    def check(self, file_path: str | Path) -> CheckResult:
        cmd = [self.vera, "check", "--json", str(file_path)]
        result = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, timeout=self.timeout_check, check=False
        )
        combined = result.stdout + result.stderr
        try:
            data = json.loads(combined)
        except json.JSONDecodeError:
            return CheckResult(
                passed=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return CheckResult(
            passed=data.get("ok", False),
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            diagnostics=data.get("diagnostics", []),
            warnings=data.get("warnings", []),
        )

    def verify(self, file_path: str | Path) -> VerifyResult:
        cmd = [self.vera, "verify", "--json", str(file_path)]
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_verify,
            check=False,
        )
        combined = result.stdout + result.stderr
        try:
            data = json.loads(combined)
        except json.JSONDecodeError:
            return VerifyResult(
                passed=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        verification = data.get("verification", {})
        return VerifyResult(
            passed=data.get("ok", False),
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            tier1_verified=verification.get("tier1_verified", 0),
            tier3_runtime=verification.get("tier3_runtime", 0),
            total=verification.get("total", 0),
            diagnostics=data.get("diagnostics", []),
            warnings=data.get("warnings", []),
        )

    def run_fn(
        self, file_path: str | Path, fn_name: str, args: list | None = None
    ) -> RunResult:
        cmd = [self.vera, "run", str(file_path), "--fn", fn_name]
        if args:
            cmd.append("--")
            cmd.extend(str(a) for a in args)
        result = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, timeout=self.timeout_run, check=False
        )
        return RunResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
