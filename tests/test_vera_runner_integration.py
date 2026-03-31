"""Integration tests for vera_runner — requires vera on PATH."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("vera") is None, reason="vera not available"
)

REPO_ROOT = Path(__file__).parent.parent
SOLUTIONS_DIR = REPO_ROOT / "solutions" / "vera"


class TestVeraBin:
    def test_found_on_path(self):
        from vera_bench.vera_runner import _vera_bin

        assert _vera_bin() is not None

    def test_custom_path(self, monkeypatch):
        import shutil

        from vera_bench.vera_runner import _vera_bin

        real = shutil.which("vera")
        monkeypatch.setenv("VERA_PATH", real)
        assert _vera_bin() == real

    def test_not_found(self, monkeypatch):
        from vera_bench.vera_runner import _vera_bin

        monkeypatch.delenv("VERA_PATH", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        with pytest.raises(FileNotFoundError):
            _vera_bin()


class TestVeraRunnerIntegration:
    def test_version(self):
        from vera_bench.vera_runner import VeraRunner

        ver = VeraRunner().version()
        assert ver != "unknown"
        assert "." in ver

    def test_check_good_file(self):
        from vera_bench.vera_runner import VeraRunner

        r = VeraRunner()
        result = r.check(SOLUTIONS_DIR / "VB-T1-001_absolute_value.vera")
        assert result.passed is True
        assert result.exit_code == 0
        assert result.diagnostics == []

    def test_check_bad_file(self, tmp_path):
        from vera_bench.vera_runner import VeraRunner

        bad = tmp_path / "bad.vera"
        bad.write_text("this is not vera code\n", encoding="utf-8")
        r = VeraRunner()
        result = r.check(bad)
        assert result.passed is False
        assert result.exit_code != 0

    def test_check_json_parse_failure(self, tmp_path):
        """Non-existent file — vera outputs JSON error."""
        from vera_bench.vera_runner import VeraRunner

        r = VeraRunner()
        result = r.check(tmp_path / "nonexistent.vera")
        assert result.passed is False

    def test_verify_good_file(self):
        from vera_bench.vera_runner import VeraRunner

        r = VeraRunner()
        result = r.verify(SOLUTIONS_DIR / "VB-T1-001_absolute_value.vera")
        assert result.passed is True
        assert result.tier1_verified > 0
        assert result.tier3_runtime == 0

    def test_verify_tier_breakdown(self):
        from vera_bench.vera_runner import VeraRunner

        r = VeraRunner()
        result = r.verify(SOLUTIONS_DIR / "VB-T5-001_counter.vera")
        assert result.passed is True
        assert result.tier1_verified > 0
        assert result.tier3_runtime > 0  # State handler → Tier 3

    def test_run_fn(self):
        from vera_bench.vera_runner import VeraRunner

        r = VeraRunner()
        result = r.run_fn(
            SOLUTIONS_DIR / "VB-T1-001_absolute_value.vera",
            "absolute_value",
            [-42],
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "42"

    def test_run_fn_no_args(self):
        from vera_bench.vera_runner import VeraRunner

        r = VeraRunner()
        result = r.run_fn(
            SOLUTIONS_DIR / "VB-T5-001_counter.vera",
            "count_three",
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "3"

    def test_run_fn_multi_args(self):
        from vera_bench.vera_runner import VeraRunner

        r = VeraRunner()
        result = r.run_fn(
            SOLUTIONS_DIR / "VB-T1-002_clamp.vera",
            "clamp",
            [150, 0, 100],
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "100"
