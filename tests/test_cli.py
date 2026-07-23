"""Tests for the CLI commands using Click's CliRunner."""

from __future__ import annotations

import re
import shutil

import pytest
from click.testing import CliRunner

from vera_bench.cli import _parse_version_banner, main


class TestParseVersionBanner:
    """Compiler version fragments are hyphen-joined into result filenames,
    so anything but a bare version number corrupts the name."""

    def test_single_line_banner(self):
        assert _parse_version_banner("aver 0.27.1\n") == "0.27.1"

    def test_multi_line_banner_takes_first_line_only(self):
        # ailang --version prints seven lines. Before the fix the whole
        # blob — newlines, colons and all — landed in the filename.
        banner = (
            "AILANG v0.30.0\n"
            "Commit: e37b370\n"
            "Full:   e37b370d1d7a9c4e7136b319e38bec4d5f2bd9a0\n"
            "Built:  2026-07-19T09:27:00Z\n"
            "\n"
            "The AI-First Programming Language\n"
            "Copyright (c) 2025-2026"
        )
        assert _parse_version_banner(banner) == "0.30.0"

    def test_v_prefix_stripped(self):
        assert _parse_version_banner("AILANG v0.30.0") == "0.30.0"

    def test_two_component_version(self):
        assert _parse_version_banner("vera 0.1.6") == "0.1.6"
        assert _parse_version_banner("toolchain 1.2") == "1.2"

    @pytest.mark.parametrize("raw", ["", "   \n\n  ", "no digits here"])
    def test_unparseable_yields_unknown(self, raw):
        # Callers special-case "unknown" by omitting the version from the
        # filename, which is the correct degradation.
        assert _parse_version_banner(raw) == "unknown"

    def test_result_is_filename_safe(self):
        banner = "AILANG v0.30.0\nCommit: e37b370\nCopyright (c) 2025-2026"
        parsed = _parse_version_banner(banner)
        assert not set(parsed) & set("\n\r\t /:")


class TestValidateCommand:
    def test_runs_successfully(self):
        result = CliRunner().invoke(main, ["validate"])
        assert result.exit_code == 0
        assert re.search(r"\d+/\d+ problems passed", result.output)

    def test_bad_problems_dir(self):
        result = CliRunner().invoke(
            main, ["validate", "--problems-dir", "/nonexistent"]
        )
        assert result.exit_code != 0


class TestRunCommand:
    def test_missing_model(self):
        result = CliRunner().invoke(main, ["run"])
        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output

    def test_python_warns_on_mode(self):
        """--mode with --language python should warn."""
        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-sonnet-4-6",
                "--language",
                "python",
                "--mode",
                "spec-from-nl",
                "--problem",
                "VB-T1-001",
            ],
        )
        # Will fail on API key, but warning should appear before that
        assert "Warning" in result.output

    def test_python_warns_on_skill_md(self, tmp_path):
        skill = tmp_path / "test.md"
        skill.write_text("test", encoding="utf-8")
        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-sonnet-4-6",
                "--language",
                "python",
                "--skill-md",
                str(skill),
                "--problem",
                "VB-T1-001",
            ],
        )
        assert "Warning" in result.output


class TestBaselinesCommand:
    def test_python_baselines(self, tmp_path):
        result = CliRunner().invoke(
            main,
            ["baselines", "--output-dir", str(tmp_path)],
        )
        assert result.exit_code == 0
        jsonl = list(tmp_path.glob("*.jsonl"))
        assert len(jsonl) == 1
        assert "python" in jsonl[0].name

    @pytest.mark.skipif(
        shutil.which("tsx") is None and shutil.which("npx") is None,
        reason="tsx/npx not on PATH",
    )
    def test_typescript_baselines(self, tmp_path):
        result = CliRunner().invoke(
            main,
            [
                "baselines",
                "--language",
                "typescript",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0


class TestReportCommand:
    def test_no_results(self, tmp_path):
        result = CliRunner().invoke(main, ["report", str(tmp_path)])
        assert result.exit_code == 0
        assert "No .jsonl" in result.output

    def test_with_results(self, tmp_path):
        import json

        jf = tmp_path / "test-model.jsonl"
        jf.write_text(
            json.dumps(
                {
                    "problem_id": "VB-T1-001",
                    "attempt": 1,
                    "check_pass": True,
                    "verify_pass": True,
                    "run_correct": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        result = CliRunner().invoke(main, ["report", str(tmp_path)])
        assert result.exit_code == 0
        assert "VeraBench Results" in result.output
