"""Tests for the CLI commands using Click's CliRunner."""

from __future__ import annotations

import re
import shutil

import pytest
from click.testing import CliRunner

from vera_bench.cli import main


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
                "claude-sonnet-4-20250514",
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
                "claude-sonnet-4-20250514",
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
