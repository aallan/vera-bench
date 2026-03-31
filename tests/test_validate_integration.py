"""Integration tests for validate.py — requires vera on PATH."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vera_bench.validate import (
    REQUIRED_FIELDS,
    find_vera_file,
    normalize_output,
    run_validation,
    validate_problem,
)
from vera_bench.vera_runner import VeraRunner

REPO_ROOT = Path(__file__).parent.parent
PROBLEMS_DIR = REPO_ROOT / "problems"
SOLUTIONS_DIR = REPO_ROOT / "solutions"

pytestmark = pytest.mark.skipif(
    shutil.which("vera") is None, reason="vera not available"
)


class TestFindVeraFile:
    def test_found(self):
        path = find_vera_file("VB-T1-001", SOLUTIONS_DIR)
        assert path is not None
        assert "absolute_value" in path.name

    def test_not_found(self):
        path = find_vera_file("VB-T99-999", SOLUTIONS_DIR)
        assert path is None


class TestNormalizeOutput:
    def test_int(self):
        actual, expected = normalize_output("42\n", 42)
        assert actual == "42"
        assert expected == "42"

    def test_bool_true(self):
        actual, expected = normalize_output("1\n", True)
        assert actual == "1"
        assert expected == "1"

    def test_bool_false(self):
        actual, expected = normalize_output("0\n", False)
        assert actual == "0"
        assert expected == "0"

    def test_string_true(self):
        actual, expected = normalize_output("1\n", "true")
        assert actual == "1"
        assert expected == "1"

    def test_string_false(self):
        actual, expected = normalize_output("0\n", "false")
        assert actual == "0"
        assert expected == "0"

    def test_strips_whitespace(self):
        actual, expected = normalize_output("  42  \n", 42)
        assert actual == "42"


class TestValidateProblem:
    @pytest.fixture()
    def runner(self):
        return VeraRunner()

    def test_valid_problem(self, runner):
        pf = PROBLEMS_DIR / "tier1" / "VB_T1_001_absolute_value.json"
        result = validate_problem(pf, SOLUTIONS_DIR, runner)
        assert result["fields_ok"] is True
        assert result["vera_found"] is True
        assert result["check_pass"] is True
        assert result["verify_pass"] is True
        assert not result["errors"]

    def test_valid_problem_with_tests(self, runner):
        pf = PROBLEMS_DIR / "tier1" / "VB_T1_001_absolute_value.json"
        result = validate_problem(pf, SOLUTIONS_DIR, runner)
        assert result["tests_run"] > 0
        assert result["tests_pass"] == result["tests_run"]

    def test_missing_fields(self, runner, tmp_path):
        bad_json = tmp_path / "VB_T1_999_bad.json"
        bad_json.write_text(
            json.dumps({"id": "VB-T1-999", "tier": 1}),
            encoding="utf-8",
        )
        result = validate_problem(bad_json, SOLUTIONS_DIR, runner)
        assert result["fields_ok"] is False
        assert any("Missing fields" in e for e in result["errors"])

    def test_no_vera_file(self, runner, tmp_path):
        problem = {k: "test" for k in REQUIRED_FIELDS}
        problem["id"] = "VB-T99-999"
        problem["tier"] = 99
        problem["test_cases"] = []
        problem["vera_check_must_pass"] = True
        problem["vera_verify_tier1"] = False
        problem["tags"] = []
        problem["contracts"] = {
            "requires": ["true"],
            "ensures": ["true"],
            "effects": "pure",
        }
        pf = tmp_path / "VB_T99_999_test.json"
        pf.write_text(json.dumps(problem), encoding="utf-8")
        result = validate_problem(pf, SOLUTIONS_DIR, runner)
        assert result["vera_found"] is False
        assert any("No .vera file" in e for e in result["errors"])

    def test_bad_json(self, runner, tmp_path):
        pf = tmp_path / "VB_T1_999_bad.json"
        pf.write_text("not json at all", encoding="utf-8")
        result = validate_problem(pf, SOLUTIONS_DIR, runner)
        assert any("JSON load error" in e for e in result["errors"])

    def test_malformed_test_case(self, runner, tmp_path):
        """Test that non-dict test cases are skipped gracefully."""
        problem = {k: "test" for k in REQUIRED_FIELDS}
        problem["id"] = "VB-T1-001"
        problem["tier"] = 1
        problem["test_cases"] = ["not a dict", 42]
        problem["vera_check_must_pass"] = True
        problem["vera_verify_tier1"] = True
        problem["tags"] = []
        problem["entry_point"] = "absolute_value"
        problem["contracts"] = {
            "requires": ["true"],
            "ensures": ["true"],
            "effects": "pure",
        }
        pf = tmp_path / "VB_T1_001_absolute_value.json"
        pf.write_text(json.dumps(problem), encoding="utf-8")
        result = validate_problem(pf, SOLUTIONS_DIR, runner)
        # Should still pass check/verify since the .vera file is valid
        assert result["check_pass"] is True


class TestRunValidation:
    def test_full_validation(self):
        exit_code = run_validation()
        assert exit_code == 0
