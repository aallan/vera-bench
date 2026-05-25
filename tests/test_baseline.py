"""Tests for the baseline runner module."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vera_bench.baseline_runner import (
    _build_python_wrapper,
    _find_baseline_file,
    _snake_to_camel,
    run_ailang_baseline,
    run_python_baseline,
    run_typescript_baseline,
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

    def test_bool_string_normalization(self, tmp_path):
        problem = {
            "id": "VB-T4-003",
            "entry_point": "is_even",
            "test_cases": [
                {"args": [4], "expected": "true"},
                {"args": [7], "expected": "false"},
            ],
        }
        result = run_python_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.run_correct is True
        assert result.tests_passed == 2

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


class TestSnakeToCamel:
    def test_simple(self):
        assert _snake_to_camel("absolute_value") == "absoluteValue"

    def test_single_word(self):
        assert _snake_to_camel("clamp") == "clamp"

    def test_multiple_words(self):
        assert _snake_to_camel("max_of_three") == "maxOfThree"

    def test_already_camel(self):
        assert _snake_to_camel("gcd") == "gcd"


class TestFindTypeScriptBaseline:
    def test_finds_tier1(self):
        path = _find_baseline_file("VB-T1-001", SOLUTIONS_DIR, "typescript")
        assert path is not None
        assert path.suffix == ".ts"

    def test_returns_none_for_unknown(self):
        path = _find_baseline_file("VB-T99-999", SOLUTIONS_DIR, "typescript")
        assert path is None


_has_tsx = shutil.which("tsx") is not None or shutil.which("npx") is not None


@pytest.mark.skipif(not _has_tsx, reason="tsx/npx not on PATH")
class TestRunTypescriptBaseline:
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
        result = run_typescript_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.language == "typescript"
        assert result.model == "baseline"
        assert result.check_pass is True
        assert result.run_correct is True
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
        result = run_typescript_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.run_correct is True

    def test_no_test_cases(self, tmp_path):
        problem = {
            "id": "VB-T2-001",
            "entry_point": "sum_array",
            "test_cases": [],
        }
        result = run_typescript_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.run_correct is None

    def test_missing_file_returns_error(self, tmp_path):
        problem = {
            "id": "VB-T99-999",
            "entry_point": "nonexistent",
            "test_cases": [{"args": [1], "expected": 1}],
        }
        result = run_typescript_baseline(problem, SOLUTIONS_DIR, tmp_path)
        assert result.check_pass is False
        assert "No TypeScript baseline" in result.error_message


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

    def test_baselines_populates_bench_version(self, tmp_path):
        # Regression for #66: baseline JSONL lines used to ship with
        # bench_version="" because the baseline runner didn't plumb
        # version info. Every row should now carry the installed
        # bench version.
        import json

        from click.testing import CliRunner

        import vera_bench
        from vera_bench.cli import main

        result = CliRunner().invoke(main, ["baselines", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        jsonl_path = tmp_path / "python-baseline.jsonl"
        assert jsonl_path.exists()

        lines = [
            json.loads(ln) for ln in jsonl_path.read_text().splitlines() if ln.strip()
        ]
        assert lines, "expected at least one baseline row"
        for row in lines:
            assert row.get("bench_version") == vera_bench.__version__, (
                f"row {row.get('problem_id')!r} has "
                f"bench_version={row.get('bench_version')!r}, "
                f"expected {vera_bench.__version__!r}"
            )


class TestRunAilangBaseline:
    """Mocked-subprocess tests for the AILANG baseline runner.

    Mirrors the Aver test pattern: the AILANG binary is not assumed to
    be on PATH in CI, so every subprocess call is intercepted at the
    `vera_bench.baseline_runner.subprocess.run` boundary. The `solutions`
    tree is also bypassed via `patch(_find_baseline_file)` since the
    runner's real responsibility is dispatch/result-shape, not file I/O.
    """

    def _problem(
        self, test_cases: list[dict[str, object]] | None = None
    ) -> dict[str, object]:
        return {
            "id": "VB-T1-001",
            "entry_point": "absolute_value",
            "test_cases": test_cases or [],
        }

    def _proc(
        self, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> MagicMock:
        m = MagicMock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_baseline_file_missing(self, tmp_path):
        # No solutions dir -> _find_baseline_file returns None.
        result = run_ailang_baseline(self._problem(), tmp_path, tmp_path)
        assert result.problem_id == "VB-T1-001"
        assert result.language == "ailang"
        assert result.model == "baseline"
        assert result.check_pass is False
        assert "No AILANG baseline" in result.error_message

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_no_test_cases_check_pass(self, mock_run, mock_find, tmp_path):
        # No test cases -> uses `ailang check` only
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.return_value = self._proc(returncode=0)

        result = run_ailang_baseline(self._problem(), tmp_path, tmp_path)
        assert result.check_pass is True
        assert result.run_correct is None
        # confirm it was the check command, not run
        args = mock_run.call_args.args[0]
        assert args[:2] == ["ailang", "check"]

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_no_test_cases_check_fail(self, mock_run, mock_find, tmp_path):
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.return_value = self._proc(
            returncode=1, stderr="Error PAR_001: bad syntax"
        )

        result = run_ailang_baseline(self._problem(), tmp_path, tmp_path)
        assert result.check_pass is False
        assert "bad syntax" in result.error_message

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_no_test_cases_ailang_not_found(self, mock_run, mock_find, tmp_path):
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.side_effect = FileNotFoundError

        result = run_ailang_baseline(self._problem(), tmp_path, tmp_path)
        assert result.check_pass is False
        assert "ailang not found" in result.error_message

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_no_test_cases_check_timeout(self, mock_run, mock_find, tmp_path):
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ailang", timeout=30)

        result = run_ailang_baseline(self._problem(), tmp_path, tmp_path)
        assert result.check_pass is False
        assert "timed out" in result.error_message

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_with_test_cases_all_pass(self, mock_run, mock_find, tmp_path):
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        # 3 test cases -> stdout has 3 lines, all matching expected
        mock_run.return_value = self._proc(returncode=0, stdout="0\n42\n42")

        problem = self._problem(
            test_cases=[
                {"args": [0], "expected": 0},
                {"args": [42], "expected": 42},
                {"args": [-42], "expected": 42},
            ]
        )
        result = run_ailang_baseline(problem, tmp_path, tmp_path)
        assert result.check_pass is True
        assert result.tests_total == 3
        assert result.tests_passed == 3
        assert result.run_correct is True

        # confirm `ailang run` was invoked (with-test-cases path)
        args = mock_run.call_args.args[0]
        assert args[:2] == ["ailang", "run"]

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_with_test_cases_bool_normalisation(self, mock_run, mock_find, tmp_path):
        """Pins the bool-normalisation contract for AILANG output: AILANG
        prints `true`/`false` (lowercase) for booleans, and the baseline
        runner reuses `_aver_output_matches`, which handles both the
        string-expected and Vera-style int-expected (1/0) forms."""
        baseline = tmp_path / "VB_T4_003.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        # AILANG's `println(show(true))` emits lowercase — same as Aver.
        mock_run.return_value = self._proc(
            returncode=0, stdout="true\nfalse\ntrue\nfalse"
        )

        problem = self._problem(
            test_cases=[
                # String-form expected (problem JSON often uses this)
                {"args": [4], "expected": "true"},
                {"args": [7], "expected": "false"},
                # Vera-style int-form expected (1/0 -> true/false carve-out
                # in _aver_output_matches)
                {"args": [4], "expected": 1},
                {"args": [7], "expected": 0},
            ]
        )
        result = run_ailang_baseline(problem, tmp_path, tmp_path)
        assert result.tests_total == 4
        assert result.tests_passed == 4
        assert result.run_correct is True

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_with_test_cases_partial_pass(self, mock_run, mock_find, tmp_path):
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        # 2nd test case fails
        mock_run.return_value = self._proc(returncode=0, stdout="0\n99")

        problem = self._problem(
            test_cases=[
                {"args": [0], "expected": 0},
                {"args": [42], "expected": 42},
            ]
        )
        result = run_ailang_baseline(problem, tmp_path, tmp_path)
        assert result.tests_total == 2
        assert result.tests_passed == 1
        assert result.run_correct is False

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_with_test_cases_compile_error(self, mock_run, mock_find, tmp_path):
        # AILANG compile error -> check_pass=False even from `ailang run`.
        # Tagged errors (Error PAR/TC/MOD) are distinguished from runtime.
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.return_value = self._proc(
            returncode=1, stderr="Error TC_042: type mismatch"
        )

        problem = self._problem(
            test_cases=[{"args": [42], "expected": 42}],
        )
        result = run_ailang_baseline(problem, tmp_path, tmp_path)
        assert result.check_pass is False  # compile error
        assert result.run_correct is False
        assert "type mismatch" in result.error_message

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_with_test_cases_runtime_error(self, mock_run, mock_find, tmp_path):
        # Non-tagged stderr -> runtime error -> check_pass stays True
        # (the program compiled but blew up at runtime).
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.return_value = self._proc(
            returncode=1, stderr="panic: division by zero"
        )

        problem = self._problem(
            test_cases=[{"args": [42], "expected": 42}],
        )
        result = run_ailang_baseline(problem, tmp_path, tmp_path)
        assert result.check_pass is True
        assert result.run_correct is False
        assert "division by zero" in result.error_message

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_with_test_cases_run_timeout(self, mock_run, mock_find, tmp_path):
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ailang", timeout=30)

        problem = self._problem(
            test_cases=[{"args": [42], "expected": 42}],
        )
        result = run_ailang_baseline(problem, tmp_path, tmp_path)
        assert result.check_pass is True
        assert result.run_correct is False
        assert "timed out" in result.error_message

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_with_test_cases_ailang_not_found(self, mock_run, mock_find, tmp_path):
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.side_effect = FileNotFoundError

        problem = self._problem(
            test_cases=[{"args": [42], "expected": 42}],
        )
        result = run_ailang_baseline(problem, tmp_path, tmp_path)
        assert result.check_pass is False
        assert "ailang not found" in result.error_message

    @patch("vera_bench.baseline_runner._find_baseline_file")
    @patch("vera_bench.baseline_runner.subprocess.run")
    def test_short_stdout_truncates_test_pass_count(
        self, mock_run, mock_find, tmp_path
    ):
        # Fewer output lines than test cases -> missing ones count as fail.
        baseline = tmp_path / "VB_T1_001.ail"
        baseline.write_text("module M\n")
        mock_find.return_value = baseline
        mock_run.return_value = self._proc(returncode=0, stdout="0\n42")  # only 2 lines

        problem = self._problem(
            test_cases=[
                {"args": [0], "expected": 0},
                {"args": [42], "expected": 42},
                {"args": [-42], "expected": 42},  # no stdout line for this
            ]
        )
        result = run_ailang_baseline(problem, tmp_path, tmp_path)
        assert result.tests_total == 3
        assert result.tests_passed == 2
        assert result.run_correct is False
