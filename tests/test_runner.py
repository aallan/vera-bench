"""Tests for the LLM runner, models, metrics, and report modules."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vera_bench.metrics import compute_metrics
from vera_bench.models import LLMResponse, create_client
from vera_bench.runner import (
    ProblemResult,
    _aver_literal,
    _strip_aver_main,
    extract_code,
    extract_vera_code,
)

# === extract_vera_code ===


class TestExtractVeraCode:
    def test_plain_code(self):
        code = "public fn foo(@Int -> @Int)\n  requires(true)\n"
        assert extract_vera_code(code) == code

    def test_single_vera_fence(self):
        response = (
            "Here is the code:\n\n"
            "```vera\n"
            "public fn foo(@Int -> @Int)\n"
            "  requires(true)\n"
            "```\n\nDone."
        )
        result = extract_vera_code(response)
        assert result.startswith("public fn foo")
        assert "requires(true)" in result

    def test_single_bare_fence(self):
        response = "```\npublic fn bar(@Int -> @Int)\n  effects(pure)\n```"
        result = extract_vera_code(response)
        assert "public fn bar" in result

    def test_multiple_fences_picks_longest(self):
        response = (
            "```vera\nshort\n```\n\n"
            "```vera\n"
            "public fn long_function(@Int -> @Int)\n"
            "  requires(true)\n"
            "  ensures(true)\n"
            "  effects(pure)\n"
            "{\n  @Int.0\n}\n"
            "```"
        )
        result = extract_vera_code(response)
        assert "long_function" in result
        assert "short" not in result

    def test_no_fences_returns_stripped(self):
        response = "  public fn x(@Int -> @Int)  \n"
        result = extract_vera_code(response)
        assert result == "public fn x(@Int -> @Int)\n"


# === ProblemResult ===


class TestProblemResult:
    def test_to_jsonl(self):
        r = ProblemResult(
            problem_id="VB-T1-001",
            model="claude-test",
            language="vera",
            attempt=1,
            check_pass=True,
            verify_pass=True,
            verify_tier1=3,
            verify_tier3=0,
            run_correct=True,
            tests_total=5,
            tests_passed=5,
            input_tokens=1000,
            output_tokens=200,
            wall_time_s=2.5,
            timestamp="2026-01-01T00:00:00Z",
        )
        line = r.to_jsonl()
        d = json.loads(line)
        assert d["problem_id"] == "VB-T1-001"
        assert d["check_pass"] is True
        assert d["verify_tier1"] == 3
        assert d["output_tokens"] == 200

    def test_to_jsonl_drops_none(self):
        r = ProblemResult(
            problem_id="VB-T1-001",
            model="test",
            language="vera",
            attempt=1,
            check_pass=False,
            error_message="type mismatch",
        )
        d = json.loads(r.to_jsonl())
        assert "verify_pass" not in d
        assert "run_correct" not in d

    def test_to_jsonl_includes_versions(self):
        r = ProblemResult(
            problem_id="VB-T1-001",
            model="test",
            language="vera",
            attempt=1,
            check_pass=True,
            bench_version="0.0.5",
            vera_version="0.0.105",
        )
        d = json.loads(r.to_jsonl())
        assert d["bench_version"] == "0.0.5"
        assert d["vera_version"] == "0.0.105"


# === create_client provider detection ===


class TestCreateClient:
    def test_anthropic_prefix(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("claude-sonnet-4-20250514")

    def test_openai_prefix(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("gpt-4o")

    def test_o1_prefix(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("o1-preview")

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown model"):
            create_client("llama-3-70b")


# === Metrics ===


class TestMetrics:
    def _make_results(self) -> list[dict]:
        return [
            {
                "problem_id": "VB-T1-001",
                "attempt": 1,
                "check_pass": True,
                "verify_pass": True,
                "run_correct": True,
            },
            {
                "problem_id": "VB-T1-002",
                "attempt": 1,
                "check_pass": True,
                "verify_pass": True,
                "run_correct": False,
            },
            {
                "problem_id": "VB-T1-003",
                "attempt": 1,
                "check_pass": False,
            },
            {
                "problem_id": "VB-T1-003",
                "attempt": 2,
                "check_pass": True,
                "verify_pass": False,
                "run_correct": True,
            },
            {
                "problem_id": "VB-T2-001",
                "attempt": 1,
                "check_pass": False,
            },
            {
                "problem_id": "VB-T2-001",
                "attempt": 2,
                "check_pass": False,
            },
        ]

    def test_check_rate(self):
        m = compute_metrics(self._make_results())
        # 2 of 4 problems passed check on attempt 1
        assert m.check_rate == 0.5

    def test_fix_rate(self):
        m = compute_metrics(self._make_results())
        # 2 problems failed check on attempt 1
        # 1 of 2 fixed on attempt 2
        assert m.fix_rate == 0.5

    def test_verify_rate(self):
        m = compute_metrics(self._make_results())
        # 3 problems have a passing check (best attempt)
        # 2 of 3 also pass verify
        assert m.verify_rate == pytest.approx(2 / 3, abs=0.01)

    def test_run_correct_rate(self):
        m = compute_metrics(self._make_results())
        # 3 problems with passing check, all have run_correct set
        # 2 of 3 have run_correct=True
        assert m.run_correct_rate == pytest.approx(2 / 3, abs=0.01)

    def test_by_tier(self):
        m = compute_metrics(self._make_results())
        assert 1 in m.by_tier
        assert 2 in m.by_tier
        assert m.by_tier[1].count == 3
        assert m.by_tier[2].count == 1

    def test_empty_results(self):
        m = compute_metrics([])
        assert m.total_problems == 0
        assert m.check_rate is None

    def test_jsonl_round_trip(self, tmp_path):
        results = self._make_results()
        path = tmp_path / "test.jsonl"
        path.write_text(
            "\n".join(json.dumps(r) for r in results) + "\n",
            encoding="utf-8",
        )

        from vera_bench.metrics import load_results

        loaded = load_results(path)
        assert len(loaded) == len(results)


# === Report ===


class TestReport:
    def test_generate_report_no_files(self):
        from vera_bench.report import generate_report

        with tempfile.TemporaryDirectory() as d:
            result = generate_report(Path(d))
            assert "No .jsonl" in result

    def test_generate_report_with_results(self):
        from vera_bench.report import generate_report

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test-model.jsonl"
            p.write_text(
                json.dumps(
                    {
                        "problem_id": "VB-T1-001",
                        "attempt": 1,
                        "check_pass": True,
                        "verify_pass": True,
                        "run_correct": True,
                        "output_tokens": 100,
                        "wall_time_s": 1.5,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report = generate_report(Path(d))
            assert "VeraBench Results" in report
            assert "test-model" in report
            assert "VB-T1-001" in report
            assert (Path(d) / "summary.md").exists()


# === run_single_problem with mocks ===


class TestRunSingleProblemMock:
    def _mock_client(self, response_text: str) -> MagicMock:
        client = MagicMock()
        client.complete.return_value = LLMResponse(
            text=response_text,
            input_tokens=500,
            output_tokens=150,
            wall_time_s=2.0,
            model="mock-model",
        )
        return client

    def _mock_vera(
        self, check_pass: bool = True, verify_pass: bool = True
    ) -> MagicMock:
        vera = MagicMock()

        check_result = MagicMock()
        check_result.passed = check_pass
        check_result.exit_code = 0 if check_pass else 1
        check_result.diagnostics = [] if check_pass else [{"description": "type error"}]
        check_result.stderr = "" if check_pass else "Error"
        vera.check.return_value = check_result

        verify_result = MagicMock()
        verify_result.passed = verify_pass
        verify_result.exit_code = 0 if verify_pass else 1
        verify_result.tier1_verified = 3
        verify_result.tier3_runtime = 0
        vera.verify.return_value = verify_result

        run_result = MagicMock()
        run_result.exit_code = 0
        run_result.stdout = "42\n"
        vera.run_fn.return_value = run_result

        return vera

    def _sample_problem(self) -> dict:
        return {
            "id": "VB-T1-001",
            "description": "Test problem",
            "signature": "public fn test(@Int -> @Int)",
            "contracts": {
                "requires": ["true"],
                "ensures": ["true"],
                "effects": "pure",
            },
            "entry_point": "test",
            "test_cases": [{"args": [42], "expected": 42}],
        }

    def test_passing_first_attempt(self):
        from vera_bench.runner import run_single_problem

        client = self._mock_client("public fn test(@Int -> @Int)\n")
        vera = self._mock_vera(check_pass=True)

        with tempfile.TemporaryDirectory() as d:
            results = run_single_problem(
                problem=self._sample_problem(),
                client=client,
                skill_md="SKILL",
                vera=vera,
                work_dir=Path(d),
            )

        assert len(results) == 1
        assert results[0].attempt == 1
        assert results[0].check_pass is True
        assert results[0].model == "mock-model"

    def test_failing_triggers_retry(self):
        from vera_bench.runner import run_single_problem

        client = self._mock_client("bad code\n")
        vera = self._mock_vera(check_pass=False)

        with tempfile.TemporaryDirectory() as d:
            results = run_single_problem(
                problem=self._sample_problem(),
                client=client,
                skill_md="SKILL",
                vera=vera,
                work_dir=Path(d),
            )

        assert len(results) == 2
        assert results[0].attempt == 1
        assert results[0].check_pass is False
        assert results[1].attempt == 2
        assert client.complete.call_count == 2

    def test_no_retry_when_disabled(self):
        from vera_bench.runner import run_single_problem

        client = self._mock_client("bad code\n")
        vera = self._mock_vera(check_pass=False)

        with tempfile.TemporaryDirectory() as d:
            results = run_single_problem(
                problem=self._sample_problem(),
                client=client,
                skill_md="SKILL",
                vera=vera,
                work_dir=Path(d),
                max_fix_attempts=0,
            )

        assert len(results) == 1
        assert client.complete.call_count == 1


# === CLI ===


class TestCLICommands:
    def test_run_command_exists(self):
        from vera_bench.cli import main

        assert "run" in main.commands

    def test_report_command_exists(self):
        from vera_bench.cli import main

        assert "report" in main.commands

    def test_validate_command_exists(self):
        from vera_bench.cli import main

        assert "validate" in main.commands


# === Python generation ===


class TestNeutralDescription:
    def test_returns_neutral_when_present(self):
        from vera_bench.prompts import _neutral_description

        problem = {
            "description": "Vera-flavoured description",
            "description_neutral": "Neutral description",
        }
        assert _neutral_description(problem) == "Neutral description"

    def test_falls_back_to_original(self):
        from vera_bench.prompts import _neutral_description

        problem = {"description": "Original description"}
        assert _neutral_description(problem) == "Original description"

    def test_falls_back_on_empty_string(self):
        from vera_bench.prompts import _neutral_description

        problem = {"description": "Original", "description_neutral": ""}
        assert _neutral_description(problem) == "Original"


class TestLoadAverLlmsTxt:
    def test_loads_from_file(self, tmp_path):
        from vera_bench.prompts import load_aver_llms_txt

        txt_file = tmp_path / "llms.txt"
        txt_file.write_text("# Aver spec\nfn foo() -> Int", encoding="utf-8")
        content = load_aver_llms_txt(txt_file)
        assert "Aver spec" in content
        assert "fn foo" in content

    def test_raises_on_missing_file(self):
        from vera_bench.prompts import load_aver_llms_txt

        with pytest.raises(FileNotFoundError):
            load_aver_llms_txt("/nonexistent/llms.txt")


class TestPythonPrompt:
    def test_build_python_prompt(self):
        from vera_bench.prompts import build_python_prompt

        problem = {
            "description": "Compute absolute value",
            "entry_point": "absolute_value",
        }
        result = build_python_prompt(problem)
        assert "absolute_value" in result["user"]
        assert "Python" in result["system"]
        assert "Vera" not in result["system"]

    def test_python_prompt_no_contracts(self):
        from vera_bench.prompts import build_python_prompt

        problem = {
            "description": "Test problem",
            "entry_point": "test_fn",
            "contracts": {"requires": ["x > 0"]},
        }
        result = build_python_prompt(problem)
        assert "requires" not in result["user"]


class TestExtractCode:
    def test_python_fence(self):
        response = "```python\ndef foo():\n    return 42\n```"
        result = extract_code(response)
        assert "def foo" in result

    def test_py_fence(self):
        response = "```py\ndef bar():\n    pass\n```"
        result = extract_code(response)
        assert "def bar" in result

    def test_backward_compat(self):
        assert extract_vera_code is extract_code


class TestEvaluatePythonCode:
    def test_correct_code(self, tmp_path):
        from vera_bench.runner import _evaluate_python_code

        code = "def absolute_value(x):\n    return abs(x)\n"
        problem = {
            "id": "VB-T1-001",
            "entry_point": "absolute_value",
            "test_cases": [
                {"args": [42], "expected": 42},
                {"args": [-5], "expected": 5},
            ],
        }
        result = _evaluate_python_code(code, problem, tmp_path, 1)
        assert result["check_pass"] is True
        assert result["run_correct"] is True
        assert result["tests_passed"] == 2

    def test_wrong_code(self, tmp_path):
        from vera_bench.runner import _evaluate_python_code

        code = "def absolute_value(x):\n    return x\n"
        problem = {
            "id": "VB-T1-001",
            "entry_point": "absolute_value",
            "test_cases": [
                {"args": [-5], "expected": 5},
            ],
        }
        result = _evaluate_python_code(code, problem, tmp_path, 1)
        assert result["run_correct"] is False

    def test_no_test_cases(self, tmp_path):
        from vera_bench.runner import _evaluate_python_code

        result = _evaluate_python_code(
            "x = 1\n",
            {"id": "X", "entry_point": "x", "test_cases": []},
            tmp_path,
            1,
        )
        assert result["run_correct"] is None


class TestRunSingleProblemPython:
    def test_python_language(self):
        from vera_bench.runner import run_single_problem

        client = MagicMock()
        client.complete.return_value = LLMResponse(
            text="def absolute_value(x):\n    return abs(x)\n",
            input_tokens=100,
            output_tokens=20,
            wall_time_s=1.0,
            model="mock",
        )
        problem = {
            "id": "VB-T1-001",
            "description": "Absolute value",
            "entry_point": "absolute_value",
            "test_cases": [{"args": [-5], "expected": 5}],
        }
        with tempfile.TemporaryDirectory() as d:
            results = run_single_problem(
                problem=problem,
                client=client,
                skill_md="",
                vera=None,
                work_dir=Path(d),
                language="python",
            )
        assert len(results) == 1
        assert results[0].language == "python"
        assert results[0].check_pass is True
        assert results[0].run_correct is True

    def test_python_no_fix_attempt(self):
        """Python problems should never trigger a fix attempt."""
        from vera_bench.runner import run_single_problem

        client = MagicMock()
        client.complete.return_value = LLMResponse(
            text="def bad():\n    raise Exception('fail')\n",
            input_tokens=100,
            output_tokens=20,
            wall_time_s=1.0,
            model="mock",
        )
        problem = {
            "id": "VB-T1-001",
            "description": "Test",
            "entry_point": "bad",
            "test_cases": [{"args": [], "expected": 0}],
        }
        with tempfile.TemporaryDirectory() as d:
            results = run_single_problem(
                problem=problem,
                client=client,
                skill_md="",
                vera=None,
                work_dir=Path(d),
                language="python",
            )
        # Only 1 result — no fix attempt for Python
        assert len(results) == 1
        assert client.complete.call_count == 1


# === TypeScript generation ===


class TestTypescriptPrompt:
    def test_build_typescript_prompt(self):
        from vera_bench.prompts import build_typescript_prompt

        problem = {
            "description": "Compute absolute value",
            "entry_point": "absolute_value",
        }
        result = build_typescript_prompt(problem)
        assert "absoluteValue" in result["user"]
        assert "TypeScript" in result["system"]

    def test_typescript_prompt_camel_case(self):
        from vera_bench.prompts import build_typescript_prompt

        problem = {
            "description": "Test",
            "entry_point": "max_of_three",
        }
        result = build_typescript_prompt(problem)
        assert "maxOfThree" in result["user"]
        assert "max_of_three" not in result["user"]


_has_tsx = shutil.which("tsx") is not None or shutil.which("npx") is not None


class TestEvaluateTypescriptCode:
    @pytest.mark.skipif(not _has_tsx, reason="tsx/npx not on PATH")
    def test_correct_code(self, tmp_path):
        from vera_bench.runner import _evaluate_typescript_code

        code = "function absoluteValue(x: number): number { return Math.abs(x); }\n"
        problem = {
            "id": "VB-T1-001",
            "entry_point": "absolute_value",
            "test_cases": [
                {"args": [42], "expected": 42},
                {"args": [-5], "expected": 5},
            ],
        }
        result = _evaluate_typescript_code(code, problem, tmp_path, 1)
        assert result["check_pass"] is True
        assert result["run_correct"] is True
        assert result["tests_passed"] == 2

    def test_no_test_cases(self, tmp_path):
        from vera_bench.runner import _evaluate_typescript_code

        result = _evaluate_typescript_code(
            "const x = 1;\n",
            {"id": "X", "entry_point": "x", "test_cases": []},
            tmp_path,
            1,
        )
        assert result["run_correct"] is None


# === Error paths ===


class TestEvaluatePythonErrors:
    def test_syntax_error(self, tmp_path):
        from vera_bench.runner import _evaluate_python_code

        code = "def broken(\n"  # unclosed paren
        problem = {
            "id": "VB-T1-001",
            "entry_point": "broken",
            "test_cases": [{"args": [1], "expected": 1}],
        }
        result = _evaluate_python_code(code, problem, tmp_path, 1)
        # Syntax error causes import failure → run_correct=False
        assert result["run_correct"] is False
        assert result["error_message"] is not None

    def test_runtime_error(self, tmp_path):
        from vera_bench.runner import _evaluate_python_code

        code = "def bad(x):\n    return 1 / 0\n"
        problem = {
            "id": "VB-T1-001",
            "entry_point": "bad",
            "test_cases": [{"args": [1], "expected": 1}],
        }
        result = _evaluate_python_code(code, problem, tmp_path, 1)
        assert result["check_pass"] is True
        assert result["run_correct"] is False

    def test_wrong_output(self, tmp_path):
        from vera_bench.runner import _evaluate_python_code

        code = "def wrong(x):\n    return x + 1\n"
        problem = {
            "id": "VB-T1-001",
            "entry_point": "wrong",
            "test_cases": [{"args": [5], "expected": 5}],
        }
        result = _evaluate_python_code(code, problem, tmp_path, 1)
        assert result["check_pass"] is True
        assert result["run_correct"] is False
        assert result["tests_passed"] == 0


class TestAverLiteral:
    def test_positive_int(self):
        assert _aver_literal(42) == "42"

    def test_zero(self):
        assert _aver_literal(0) == "0"

    def test_negative_int(self):
        assert _aver_literal(-5) == "(0 - 5)"

    def test_bool_true(self):
        assert _aver_literal(True) == "true"

    def test_bool_false(self):
        assert _aver_literal(False) == "false"

    def test_string(self):
        assert _aver_literal("hello") == '"hello"'

    def test_string_with_quotes(self):
        assert _aver_literal('say "hi"') == '"say \\"hi\\""'

    def test_string_with_backslash(self):
        assert _aver_literal("a\\b") == '"a\\\\b"'

    def test_float(self):
        assert _aver_literal(3.14) == "3.14"

    def test_list(self):
        assert _aver_literal([1, 2, 3]) == "[1, 2, 3]"

    def test_nested_list(self):
        assert _aver_literal([[1], [2]]) == "[[1], [2]]"

    def test_empty_list(self):
        assert _aver_literal([]) == "[]"


class TestStripAverMain:
    def test_removes_main(self):
        code = (
            "fn foo(x: Int) -> Int\n"
            "    x + 1\n"
            "\n"
            "fn main() -> Unit\n"
            "    ! [Console.print]\n"
            "    Console.print(foo(5))\n"
        )
        result = _strip_aver_main(code)
        assert "fn foo" in result
        assert "fn main" not in result
        assert "Console.print(foo(5))" not in result

    def test_keeps_code_without_main(self):
        code = "fn foo(x: Int) -> Int\n    x + 1\n"
        result = _strip_aver_main(code)
        assert "fn foo" in result

    def test_preserves_code_after_main(self):
        code = (
            "fn main() -> Unit\n"
            "    ! [Console.print]\n"
            "    Console.print(42)\n"
            "\n"
            "fn bar(x: Int) -> Int\n"
            "    x * 2\n"
        )
        result = _strip_aver_main(code)
        assert "fn main" not in result
        assert "fn bar" in result


class TestEvaluateAverCode:
    def _sample_problem(self, test_cases=None):
        return {
            "id": "VB-T1-001",
            "entry_point": "absolute_value",
            "test_cases": test_cases or [],
        }

    def _mock_subprocess(self, returncode=0, stdout="", stderr=""):
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    @patch("vera_bench.runner.subprocess.run")
    def test_check_pass(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_aver_code

        # check passes, verify passes, no test cases
        mock_run.side_effect = [
            self._mock_subprocess(returncode=0),  # aver check
            self._mock_subprocess(returncode=0),  # aver verify
        ]
        code = (
            "module Test\n"
            '    intent = "test"\n\n'
            "fn absolute_value(x: Int) -> Int\n"
            "    match x < 0\n"
            "        true -> 0 - x\n"
            "        false -> x\n"
        )
        result = _evaluate_aver_code(code, self._sample_problem(), tmp_path, 1)
        assert result["check_pass"] is True
        assert result["verify_pass"] is True
        assert result["run_correct"] is None

    @patch("vera_bench.runner.subprocess.run")
    def test_check_fail(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_aver_code

        mock_run.return_value = self._mock_subprocess(
            returncode=1, stderr="error: type mismatch"
        )
        result = _evaluate_aver_code(
            "fn bad() -> Int\n    true\n",
            self._sample_problem(),
            tmp_path,
            1,
        )
        assert result["check_pass"] is False
        assert "type mismatch" in result["error_message"]

    @patch("vera_bench.runner.subprocess.run")
    def test_aver_not_found(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_aver_code

        mock_run.side_effect = FileNotFoundError
        result = _evaluate_aver_code(
            "fn x() -> Int\n    1\n",
            self._sample_problem(),
            tmp_path,
            1,
        )
        assert result["check_pass"] is False
        assert "aver not found" in result["error_message"]

    @patch("vera_bench.runner.subprocess.run")
    def test_check_timeout(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_aver_code

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aver", timeout=30)
        result = _evaluate_aver_code(
            "fn x() -> Int\n    1\n",
            self._sample_problem(),
            tmp_path,
            1,
        )
        assert result["check_pass"] is False
        assert "timed out" in result["error_message"]

    @patch("vera_bench.runner.subprocess.run")
    def test_with_test_cases(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_aver_code

        mock_run.side_effect = [
            self._mock_subprocess(returncode=0),  # aver check
            self._mock_subprocess(returncode=0),  # aver verify
            self._mock_subprocess(returncode=0, stdout="42\n"),  # aver run tc1
            self._mock_subprocess(returncode=0, stdout="5\n"),  # aver run tc2
        ]
        problem = self._sample_problem(
            test_cases=[
                {"args": [42], "expected": 42},
                {"args": [-5], "expected": 5},
            ]
        )
        result = _evaluate_aver_code(
            'module T\n    intent = "t"\n\nfn absolute_value(x: Int) -> Int\n    x\n',
            problem,
            tmp_path,
            1,
        )
        assert result["check_pass"] is True
        assert result["tests_total"] == 2
        assert result["tests_passed"] == 2
        assert result["run_correct"] is True

    @patch("vera_bench.runner.subprocess.run")
    def test_verify_timeout_counts_as_failure(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_aver_code

        mock_run.side_effect = [
            self._mock_subprocess(returncode=0),  # aver check
            subprocess.TimeoutExpired(cmd="aver", timeout=30),  # aver verify
        ]
        result = _evaluate_aver_code(
            'module T\n    intent = "t"\n\nfn x() -> Int\n    1\n',
            self._sample_problem(),
            tmp_path,
            1,
        )
        assert result["check_pass"] is True
        assert result["verify_pass"] is False


class TestRunSingleProblemAver:
    def _mock_client(self, text):
        client = MagicMock()
        client.complete.return_value = LLMResponse(
            text=text,
            input_tokens=100,
            output_tokens=50,
            wall_time_s=1.0,
            model="mock",
        )
        return client

    @patch("vera_bench.runner.subprocess.run")
    def test_aver_language(self, mock_run, tmp_path):
        from vera_bench.runner import run_single_problem

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # check
            MagicMock(returncode=0, stdout="", stderr=""),  # verify
        ]
        client = self._mock_client(
            'module T\n    intent = "t"\n\nfn test(x: Int) -> Int\n    x\n'
        )
        results = run_single_problem(
            problem={
                "id": "VB-T1-001",
                "description": "Test",
                "entry_point": "test",
                "test_cases": [],
            },
            client=client,
            skill_md="spec",
            vera=None,
            work_dir=tmp_path,
            language="aver",
        )
        assert len(results) == 1
        assert results[0].language == "aver"
        assert results[0].check_pass is True

    @patch("vera_bench.runner.subprocess.run")
    def test_aver_no_retry_on_tooling_error(self, mock_run, tmp_path):
        from vera_bench.runner import run_single_problem

        mock_run.side_effect = FileNotFoundError
        client = self._mock_client("fn bad() -> Int\n    1\n")
        results = run_single_problem(
            problem={
                "id": "VB-T1-001",
                "description": "Test",
                "entry_point": "bad",
                "test_cases": [],
            },
            client=client,
            skill_md="spec",
            vera=None,
            work_dir=tmp_path,
            language="aver",
        )
        # Only 1 attempt — no retry on tooling error
        assert len(results) == 1
        assert results[0].check_pass is False
        assert client.complete.call_count == 1

    @patch("vera_bench.runner.subprocess.run")
    def test_aver_retry_on_check_failure(self, mock_run, tmp_path):
        from vera_bench.runner import run_single_problem

        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: type mismatch"
        )
        client = self._mock_client("fn bad() -> Int\n    true\n")
        results = run_single_problem(
            problem={
                "id": "VB-T1-001",
                "description": "Test",
                "entry_point": "bad",
                "test_cases": [],
            },
            client=client,
            skill_md="spec",
            vera=None,
            work_dir=tmp_path,
            language="aver",
        )
        # 2 attempts — retry on actual check failure
        assert len(results) == 2
        assert client.complete.call_count == 2

    def test_unknown_language_raises(self, tmp_path):
        from vera_bench.runner import run_single_problem

        client = MagicMock()
        client.complete.return_value = LLMResponse(
            text="code",
            input_tokens=10,
            output_tokens=10,
            wall_time_s=0.1,
            model="mock",
        )
        with pytest.raises(ValueError, match="Unknown language"):
            run_single_problem(
                problem={
                    "id": "VB-T1-001",
                    "description": "Test",
                    "entry_point": "test",
                    "test_cases": [],
                },
                client=client,
                skill_md="",
                vera=None,
                work_dir=tmp_path,
                language="rust",
            )


class TestAverPrompt:
    def test_build_aver_prompt(self):
        from vera_bench.prompts import build_aver_prompt

        problem = {
            "description": "Compute absolute value",
            "description_neutral": "Return the absolute value of an integer.",
            "entry_point": "absolute_value",
        }
        result = build_aver_prompt(problem, "# Aver spec")
        assert "absolute_value" in result["user"]
        assert "Aver" in result["system"]
        assert "# Aver spec" in result["system"]
        assert "Return the absolute value" in result["user"]

    def test_aver_prompt_uses_neutral(self):
        from vera_bench.prompts import build_aver_prompt

        problem = {
            "description": "Vera-flavoured description with @Int",
            "description_neutral": "Neutral description",
            "entry_point": "test",
        }
        result = build_aver_prompt(problem, "spec")
        assert "Neutral description" in result["user"]
        assert "Vera-flavoured" not in result["user"]

    def test_build_aver_fix_prompt(self):
        from vera_bench.prompts import build_aver_fix_prompt

        result = build_aver_fix_prompt("bad code", "type error", "spec")
        assert "bad code" in result["user"]
        assert "type error" in result["user"]
        assert "Fix" in result["user"]


class TestAverCLI:
    def test_baselines_command_accepts_aver(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        # Just test that --language aver is accepted (will fail on
        # missing aver binary, but that's the expected path)
        result = CliRunner().invoke(main, ["baselines", "--language", "aver"])
        # Should fail with "aver not found" not "invalid choice"
        assert "invalid" not in (result.output or "").lower()

    def test_run_command_accepts_aver(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(
            main, ["run", "--model", "claude-haiku-4-5-20251001", "--language", "aver"]
        )
        # Should not fail with "invalid choice"
        assert "invalid" not in (result.output or "").lower()


class TestAverOutputMatches:
    def test_exact_int_match(self):
        from vera_bench.baseline_runner import _aver_output_matches

        assert _aver_output_matches("42", 42) is True

    def test_bool_true_from_int(self):
        from vera_bench.baseline_runner import _aver_output_matches

        assert _aver_output_matches("true", 1) is True

    def test_bool_false_from_int(self):
        from vera_bench.baseline_runner import _aver_output_matches

        assert _aver_output_matches("false", 0) is True

    def test_int_not_treated_as_bool(self):
        from vera_bench.baseline_runner import _aver_output_matches

        # 42 should NOT match "true" even though it's truthy
        assert _aver_output_matches("true", 42) is False

    def test_negative_match(self):
        from vera_bench.baseline_runner import _aver_output_matches

        assert _aver_output_matches("-5", -5) is True

    def test_string_match(self):
        from vera_bench.baseline_runner import _aver_output_matches

        assert _aver_output_matches("hello", "hello") is True

    def test_bool_literal_match(self):
        from vera_bench.baseline_runner import _aver_output_matches

        assert _aver_output_matches("true", True) is True
        assert _aver_output_matches("false", False) is True


class TestRunBenchmarkIntegration:
    def test_writes_jsonl(self, tmp_path):
        from vera_bench.runner import run_benchmark

        client = MagicMock()
        client.complete.return_value = LLMResponse(
            text="def absolute_value(x):\n    return abs(x)\n",
            input_tokens=100,
            output_tokens=20,
            wall_time_s=1.0,
            model="mock",
        )
        problem = {
            "id": "VB-T1-001",
            "description": "Abs",
            "entry_point": "absolute_value",
            "signature": "fn abs(@Int -> @Nat)",
            "contracts": {
                "requires": ["true"],
                "ensures": ["true"],
                "effects": "pure",
            },
            "test_cases": [{"args": [-5], "expected": 5}],
        }
        output = tmp_path / "test.jsonl"
        results = run_benchmark(
            problems=[problem],
            client=client,
            skill_md="",
            vera=None,
            language="python",
            output_path=output,
        )
        assert len(results) >= 1
        assert output.exists()
        lines = output.read_text().strip().split("\n")
        assert len(lines) >= 1
