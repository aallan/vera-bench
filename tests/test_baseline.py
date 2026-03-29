"""Tests for the baseline runner module."""

from __future__ import annotations

import json
from pathlib import Path

from vera_bench.baseline_runner import (
    _build_python_wrapper,
    _find_baseline_file,
    run_python_baseline,
)

REPO_ROOT = Path(__file__).parent.parent
SOLUTIONS_DIR = REPO_ROOT / "solutions"
PROBLEMS_DIR = REPO_ROOT / "problems"


class TestFindBaselineFile:
    def test_finds_tier1_problem(self):
        path = _find_baseline_file("VB-T1-001", SOLUTIONS_DIR, "python")
        assert path is not None
        assert path.name == "VB_T1_001_absolute_value.py"

    def test_finds_tier4_problem(self):
        path = _find_baseline_file("VB-T4-002", SOLUTIONS_DIR, "python")
        assert path is not None
        assert "greatest_common_divisor" in path.name

    def test_returns_none_for_unknown(self):
        path = _find_baseline_file("VB-T99-999", SOLUTIONS_DIR, "python")
        assert path is None


class TestBuildPythonWrapper:
    def test_generates_valid_python(self):
        problem = {
            "id": "VB-T1-001",
            "entry_point": "absolute_value",
            "test_cases": [
                {"args": [42], "expected": 42},
                {"args": [-5], "expected": 5},
            ],
        }
        baseline_path = SOLUTIONS_DIR / "python" / "VB_T1_001_absolute_value.py"
        wrapper = _build_python_wrapper(problem, baseline_path)
        assert "import json" in wrapper
        assert "absolute_value" in wrapper
        assert "results.append" in wrapper
        assert "print(json.dumps(results))" in wrapper

    def test_wrapper_handles_empty_test_cases(self):
        problem = {
            "id": "VB-T2-001",
            "entry_point": "sum_array",
            "test_cases": [],
        }
        baseline_path = SOLUTIONS_DIR / "python" / "VB_T2_001_sum_array.py"
        wrapper = _build_python_wrapper(problem, baseline_path)
        assert "print(json.dumps(results))" in wrapper


class TestRunPythonBaseline:
    def test_tier1_absolute_value(self, tmp_path):
        problem = {
            "id": "VB-T1-001",
            "entry_point": "absolute_value",
            "test_cases": [
                {"args": [0], "expected": 0},
                {"args": [42], "expected": 42},
                {"args": [-42], "expected": 42},
            ],
        }
        result = run_python_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.problem_id == "VB-T1-001"
        assert result.language == "python"
        assert result.model == "baseline"
        assert result.check_pass is True
        assert result.run_correct is True
        assert result.tests_total == 3
        assert result.tests_passed == 3

    def test_tier4_gcd(self, tmp_path):
        problem = {
            "id": "VB-T4-002",
            "entry_point": "gcd",
            "test_cases": [
                {"args": [12, 8], "expected": 4},
                {"args": [7, 0], "expected": 7},
            ],
        }
        result = run_python_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.run_correct is True
        assert result.tests_passed == 2

    def test_no_test_cases_returns_none(self, tmp_path):
        problem = {
            "id": "VB-T2-001",
            "entry_point": "sum_array",
            "test_cases": [],
        }
        result = run_python_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.run_correct is None

    def test_missing_file_returns_error(self, tmp_path):
        problem = {
            "id": "VB-T99-999",
            "entry_point": "nonexistent",
            "test_cases": [{"args": [1], "expected": 1}],
        }
        result = run_python_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.check_pass is False
        assert "No Python baseline" in result.error_message

    def test_result_serializes_to_jsonl(self, tmp_path):
        problem = {
            "id": "VB-T1-001",
            "entry_point": "absolute_value",
            "test_cases": [{"args": [5], "expected": 5}],
        }
        result = run_python_baseline(problem, SOLUTIONS_DIR, tmp_path)
        d = json.loads(result.to_jsonl())
        assert d["language"] == "python"
        assert d["model"] == "baseline"


class TestBaselinesCLI:
    def test_baselines_command_exists(self):
        from vera_bench.cli import main

        assert "baselines" in main.commands

    def test_baselines_runs_and_produces_output(self, tmp_path):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(main, ["baselines", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        jsonl_files = list(tmp_path.glob("*.jsonl"))
        assert len(jsonl_files) == 1
        assert jsonl_files[0].name == "python-baseline.jsonl"
