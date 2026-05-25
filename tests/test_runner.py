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
    _ailang_literal,
    _aver_literal,
    _strip_ailang_main,
    _strip_aver_main,
    _strip_module_effects,
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

    def test_exclude_tiers(self):
        results = self._make_results() + [
            {
                "problem_id": "VB-T5-001",
                "attempt": 1,
                "check_pass": True,
                "verify_pass": True,
                "run_correct": True,
            },
        ]
        m_all = compute_metrics(results)
        m_no_t5 = compute_metrics(results, exclude_tiers={5})

        assert m_all.total_problems == 5
        assert 5 in m_all.by_tier
        assert m_no_t5.total_problems == 4
        assert 5 not in m_no_t5.by_tier
        assert m_no_t5.check_rate == 0.5

    def test_exclude_tiers_none_is_default(self):
        results = self._make_results()
        m1 = compute_metrics(results)
        m2 = compute_metrics(results, exclude_tiers=None)
        assert m1.total_problems == m2.total_problems
        assert m1.check_rate == m2.check_rate

    def test_exclude_tiers_empty_set(self):
        results = self._make_results() + [
            {
                "problem_id": "VB-T5-001",
                "attempt": 1,
                "check_pass": True,
            },
        ]
        m = compute_metrics(results, exclude_tiers=set())
        assert m.total_problems == 5

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
            assert "All Tiers" in report
            assert "Comparable" in report
            assert (Path(d) / "summary.md").exists()

    def test_report_t1t4_shows_different_counts(self):
        from vera_bench.report import generate_report

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test-model.jsonl"
            lines = [
                json.dumps(
                    {
                        "problem_id": "VB-T1-001",
                        "attempt": 1,
                        "check_pass": True,
                        "run_correct": True,
                    }
                ),
                json.dumps(
                    {
                        "problem_id": "VB-T5-001",
                        "attempt": 1,
                        "check_pass": True,
                        "run_correct": True,
                    }
                ),
            ]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report = generate_report(Path(d))
            all_section, comparable_section = report.split(
                "### Comparable",
                1,
            )
            # All tiers: 2 problems
            assert "test-model" in all_section
            assert "| 2 |" in all_section
            # T1-T4 comparable: 1 problem
            assert "test-model" in comparable_section
            assert "| 1 |" in comparable_section
            assert "Tier 5 tests algebraic effect handlers" in report

    def test_report_comparable_hidden_when_only_t5(self):
        from vera_bench.report import generate_report

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test-model.jsonl"
            p.write_text(
                json.dumps(
                    {
                        "problem_id": "VB-T5-001",
                        "attempt": 1,
                        "check_pass": True,
                        "run_correct": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report = generate_report(Path(d))
            assert "All Tiers" in report
            assert "### Comparable" not in report


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


class TestStripModuleEffects:
    def test_removes_inline_empty_effects(self):
        code = (
            "module M\n"
            '    intent = "t"\n'
            "    effects []\n"
            "\n"
            "fn f(x: Int) -> Int\n"
            "    x + 1\n"
        )
        result = _strip_module_effects(code)
        assert "effects []" not in result
        assert "fn f" in result
        assert "module M" in result

    def test_removes_inline_listed_effects(self):
        code = (
            "module M\n"
            '    intent = "t"\n'
            "    effects [Console.print, Disk.readText]\n"
            "\n"
            "fn f() -> Unit\n"
            "    ! [Console.print]\n"
            '    Console.print("hi")\n'
        )
        result = _strip_module_effects(code)
        assert "effects [" not in result
        assert "fn f" in result
        assert "Console.print" in result  # body still has it

    def test_removes_multiline_effects(self):
        code = (
            "module M\n"
            '    intent = "t"\n'
            "    effects [\n"
            "        Console.print,\n"
            "        Disk.readText,\n"
            "    ]\n"
            "\n"
            "fn f() -> Unit\n"
            "    ! [Console.print]\n"
            '    Console.print("hi")\n'
        )
        result = _strip_module_effects(code)
        assert "effects [" not in result
        assert "Disk.readText" not in result.split("fn f")[0]
        assert "fn f" in result

    def test_no_op_when_no_effects(self):
        code = 'module M\n    intent = "t"\n\nfn f(x: Int) -> Int\n    x + 1\n'
        result = _strip_module_effects(code)
        assert result == code

    def test_no_op_when_no_module_declaration(self):
        # Without a `module X` header there is no module-effect
        # boundary to strip; an `effects [...]` token at the top
        # level is something else, so we must leave the code
        # untouched. The bench-side wrapper synthesises a `module
        # Test{safe_id}` for these cases — it never owned the
        # boundary in the first place.
        code = 'effects [Console.print]\n\nfn f() -> Unit\n    Console.print("hi")\n'
        result = _strip_module_effects(code)
        assert result == code

    def test_strips_arbitrary_whitespace_between_keyword_and_bracket(self):
        # LLM-formatted output may emit any whitespace between
        # `effects` and `[`; the strip must catch every variant the
        # Aver parser accepts, not just the canonical single space.
        for opener in ("effects[", "effects [", "effects  [", "effects\t["):
            code = (
                "module M\n"
                '    intent = "t"\n'
                f"    {opener}Console.print]\n"
                "\n"
                "fn f() -> Unit\n"
                "    ! [Console.print]\n"
                '    Console.print("hi")\n'
            )
            result = _strip_module_effects(code)
            header_part = result.split("fn f")[0]
            assert "Console.print]" not in header_part, (
                f"failed to strip header with opener: {opener!r}"
            )
            assert "fn f" in result

    def test_only_strips_inside_module_header(self):
        # An `effects [...]`-shaped line that appears below a
        # function body must not be removed; only the module-header
        # occurrence is the bench's concern.
        code = (
            "module M\n"
            '    intent = "t"\n'
            "    effects [Console.print]\n"
            "\n"
            "fn f() -> Unit\n"
            "    effects [Console.print]\n"
            '    Console.print("hi")\n'
        )
        result = _strip_module_effects(code)
        lines = result.split("\n")
        # Header `effects` line gone, fn-body `effects` line kept.
        assert sum(1 for line in lines if "effects [Console.print]" in line) == 1

    def test_strips_inline_effects_with_trailing_comment(self):
        # Aver allows `// ...` line comments; an inline `effects
        # [...] // comment` declaration must be detected as
        # single-line, not fall into the multi-line skip path that
        # would chew through the function body.
        code = (
            "module M\n"
            '    intent = "t"\n'
            "    effects [Console.print] // pure module\n"
            "\n"
            "fn f() -> Unit\n"
            "    ! [Console.print]\n"
            '    Console.print("hi")\n'
        )
        result = _strip_module_effects(code)
        # Header `effects` line is gone.
        assert "effects [Console.print]" not in result
        # And critically: the function body is intact, NOT eaten by
        # a runaway skip_until_close.
        assert "fn f() -> Unit" in result
        assert 'Console.print("hi")' in result

    def test_strips_multiline_effects_with_trailing_comment_on_close(self):
        # Same hazard on the closing line of a multi-line list:
        # `]` can be followed by a trailing comment.
        code = (
            "module M\n"
            '    intent = "t"\n'
            "    effects [\n"
            "        Console.print,\n"
            "    ] // pure module\n"
            "\n"
            "fn f() -> Unit\n"
            "    ! [Console.print]\n"
            '    Console.print("hi")\n'
        )
        result = _strip_module_effects(code)
        # Whole effects block gone (header through close).
        assert "effects [" not in result
        assert "Console.print," not in result
        # Function body intact.
        assert "fn f() -> Unit" in result
        assert 'Console.print("hi")' in result


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


class TestRunSingleProblemAilang:
    """I6 (PR #70): integration-level coverage of `language == "ailang"`
    dispatch + retry behavior in run_single_problem. Mirrors the Aver
    pattern at TestRunSingleProblemAver. This is the class whose absence
    let C2 ship (the missing `language == "ailang"` retry branch was
    only catchable here, not in unit tests of `_evaluate_ailang_code`)."""

    def _mock_client(self, text: str) -> MagicMock:
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
    def test_ailang_language_dispatches_to_evaluate(self, mock_run, tmp_path):
        """Smoke test: `language="ailang"` routes to `_evaluate_ailang_code`
        (which calls `ailang check`, mocked here)."""
        from vera_bench.runner import run_single_problem

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # ailang check
        ]
        client = self._mock_client(
            "module benchmark/solution\n\nexport func test(x: int) -> int = x\n"
        )
        results = run_single_problem(
            problem={
                "id": "VB-T1-001",
                "description": "Test",
                "description_neutral": "Test",
                "entry_point": "test",
                "test_cases": [],
            },
            client=client,
            skill_md="# AILANG spec",
            vera=None,
            work_dir=tmp_path,
            language="ailang",
        )
        assert len(results) == 1
        assert results[0].language == "ailang"
        assert results[0].check_pass is True
        # The client was called exactly once with the AILANG prompt
        assert client.complete.call_count == 1
        sys_msg = client.complete.call_args.kwargs["system"]
        assert "AILANG" in sys_msg

    @patch("vera_bench.runner.subprocess.run")
    def test_ailang_no_retry_on_tooling_error(self, mock_run, tmp_path):
        """C2 + I1 regression: `--max-fix-attempts > 0` must NOT retry
        when the failure is a tooling problem ("ailang not found" /
        "timed out") — retrying with the same broken toolchain is waste.
        Tests _is_tooling_error guard covers the AILANG strings now."""
        from vera_bench.runner import run_single_problem

        mock_run.side_effect = FileNotFoundError  # ailang not found
        client = self._mock_client("module M\n\nexport func bad(x: int) -> int = x\n")
        results = run_single_problem(
            problem={
                "id": "VB-T1-001",
                "description": "Test",
                "description_neutral": "Test",
                "entry_point": "bad",
                "test_cases": [],
            },
            client=client,
            skill_md="# AILANG spec",
            vera=None,
            work_dir=tmp_path,
            language="ailang",
            max_fix_attempts=2,  # would normally trigger retry
        )
        # Single attempt; no retry call
        assert len(results) == 1
        assert results[0].check_pass is False
        assert "ailang not found" in (results[0].error_message or "")
        assert client.complete.call_count == 1

    @patch("vera_bench.runner.subprocess.run")
    def test_ailang_retry_on_check_failure(self, mock_run, tmp_path):
        """C2 regression: the missing dispatch leg meant max_fix_attempts
        was silently no-op for AILANG, undercounting it vs Aver/Vera.
        Mirror TestRunSingleProblemAver.test_aver_retry_on_check_failure."""
        from vera_bench.runner import run_single_problem

        # Both attempts fail check the same way
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Error TC_001: type mismatch"
        )
        client = self._mock_client(
            "module M\n\nexport func bad(x: int) -> int = true\n"
        )
        results = run_single_problem(
            problem={
                "id": "VB-T1-001",
                "description": "Test",
                "description_neutral": "Test",
                "entry_point": "bad",
                "test_cases": [],
            },
            client=client,
            skill_md="# AILANG spec",
            vera=None,
            work_dir=tmp_path,
            language="ailang",
            max_fix_attempts=2,
        )
        # 2 attempts — retry on real check failure
        assert len(results) == 2
        assert results[0].attempt == 1
        assert results[1].attempt == 2
        # Client called twice (initial + fix prompt). The second call's
        # user message must reference the original code + error.
        assert client.complete.call_count == 2
        fix_user = client.complete.call_args_list[1].kwargs["user"]
        assert "type mismatch" in fix_user
        assert "Fix" in fix_user

    @patch("vera_bench.runner.subprocess.run")
    def test_ailang_no_retry_when_max_fix_attempts_zero(self, mock_run, tmp_path):
        """max_fix_attempts=0 must skip the retry path entirely, regardless
        of whether the check failed."""
        from vera_bench.runner import run_single_problem

        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Error TC_001: type mismatch"
        )
        client = self._mock_client(
            "module M\n\nexport func bad(x: int) -> int = true\n"
        )
        results = run_single_problem(
            problem={
                "id": "VB-T1-001",
                "description": "Test",
                "description_neutral": "Test",
                "entry_point": "bad",
                "test_cases": [],
            },
            client=client,
            skill_md="# AILANG spec",
            vera=None,
            work_dir=tmp_path,
            language="ailang",
            max_fix_attempts=0,
        )
        # Single attempt; no retry
        assert len(results) == 1
        assert client.complete.call_count == 1


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

        result = CliRunner().invoke(main, ["baselines", "--language", "aver"])
        assert "invalid" not in (result.output or "").lower()

    def test_baselines_aver_not_on_path(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        with patch("shutil.which", return_value=None):
            result = CliRunner().invoke(main, ["baselines", "--language", "aver"])
        assert result.exit_code != 0
        assert "aver not found" in (result.output or "")

    def test_run_command_accepts_aver(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--language",
                "aver",
            ],
        )
        assert "invalid" not in (result.output or "").lower()

    def test_run_aver_version_not_found(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        # Mock llms.txt loading to isolate the aver version check
        with (
            patch("vera_bench.models.create_client"),
            patch(
                "vera_bench.prompts.load_aver_llms_txt",
                return_value="# mock spec",
            ),
            patch(
                "subprocess.run",
                side_effect=FileNotFoundError,
            ),
        ):
            result = CliRunner().invoke(
                main,
                [
                    "run",
                    "--model",
                    "claude-haiku-4-5-20251001",
                    "--language",
                    "aver",
                ],
            )
        assert result.exit_code != 0
        assert "aver not found" in (result.output or "")

    def test_run_aver_mode_warning(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--language",
                "aver",
                "--mode",
                "spec-from-nl",
            ],
        )
        assert "mode" in (result.output or "").lower()

    def test_run_python_skill_md_warning(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--language",
                "python",
                "--mode",
                "spec-from-nl",
            ],
        )
        assert "ignored" in (result.output or "").lower()

    def test_run_no_matching_problems(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--problem",
                "VB-T99-999",
            ],
        )
        assert result.exit_code != 0
        assert "No matching" in (result.output or "")


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


# === --parallel N ===


class TestRunBenchmarkParallel:
    """Tests for the ThreadPoolExecutor path in run_benchmark.

    All tests stub out `run_single_problem` so we exercise the dispatch
    layer (sequential vs threaded, exception handling, write-lock) without
    touching the LLM / subprocess machinery underneath.
    """

    def _problem(self, pid: str) -> dict:
        # Minimal problem shape — run_benchmark only reads `.get("id", ...)`
        # in the parallel-path exception handler, so this is enough.
        return {"id": pid, "entry_point": "fn", "test_cases": []}

    def _result(self, pid: str) -> ProblemResult:
        return ProblemResult(
            problem_id=pid,
            model="mock",
            language="python",
            attempt=1,
            check_pass=True,
            run_correct=True,
            tests_total=0,
            tests_passed=0,
            timestamp="2026-05-22T00:00:00Z",
        )

    @patch("vera_bench.runner.run_single_problem")
    def test_parallel_one_uses_sequential_path(self, mock_run, tmp_path):
        """`parallel=1` (the default) must use the sequential path: all
        calls to `run_single_problem` happen on the main thread, i.e. no
        worker thread is ever spawned.

        Assertion is on observable behaviour (the calling thread identity)
        rather than the implementation detail of which class gets imported —
        a future refactor that hoisted `ThreadPoolExecutor` to module
        scope (legitimate change) would still pass this test."""
        import threading

        from vera_bench.runner import run_benchmark

        calling_threads: list[threading.Thread] = []

        def _record_thread(
            problem: dict[str, object], **kw: object
        ) -> list[ProblemResult]:
            calling_threads.append(threading.current_thread())
            return [self._result(problem["id"])]

        mock_run.side_effect = _record_thread
        problems = [self._problem(f"VB-X-{i}") for i in range(3)]
        output = tmp_path / "seq.jsonl"

        results = run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=output,
            parallel=1,
        )

        assert len(results) == 3
        assert mock_run.call_count == 3
        # Behaviour assertion: every call ran on the main thread (no spawn).
        main = threading.main_thread()
        assert all(t is main for t in calling_threads), (
            f"expected all calls on main thread; got {calling_threads}"
        )
        # And the JSONL output is correct.
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 3
        ids = {json.loads(line)["problem_id"] for line in lines}
        assert ids == {"VB-X-0", "VB-X-1", "VB-X-2"}

    @patch("vera_bench.runner.run_single_problem")
    def test_parallel_two_actually_spawns_worker_threads(self, mock_run, tmp_path):
        """Counterpoint to the sequential-path test: `parallel>1` does
        spawn worker threads (not all calls run on the main thread)."""
        import threading

        from vera_bench.runner import run_benchmark

        calling_threads: list[threading.Thread] = []

        def _record_thread(
            problem: dict[str, object], **kw: object
        ) -> list[ProblemResult]:
            calling_threads.append(threading.current_thread())
            return [self._result(problem["id"])]

        mock_run.side_effect = _record_thread
        problems = [self._problem(f"VB-X-{i}") for i in range(5)]

        run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=None,
            parallel=3,
        )

        main = threading.main_thread()
        worker_calls = [t for t in calling_threads if t is not main]
        assert worker_calls, (
            "parallel>1 should spawn worker threads — got all main-thread calls"
        )

    @patch("vera_bench.runner.run_single_problem")
    def test_parallel_two_runs_all_problems(self, mock_run, tmp_path):
        """`parallel>1` runs every problem and collects every result."""
        from vera_bench.runner import run_benchmark

        mock_run.side_effect = lambda problem, **kw: [self._result(problem["id"])]
        problems = [self._problem(f"VB-X-{i}") for i in range(5)]
        output = tmp_path / "par.jsonl"

        results = run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=output,
            parallel=2,
        )

        assert len(results) == 5
        assert mock_run.call_count == 5
        # All 5 problem_ids appear (order may differ — completion order)
        ids_in_results = {r.problem_id for r in results}
        assert ids_in_results == {f"VB-X-{i}" for i in range(5)}

    @patch("vera_bench.runner.run_single_problem")
    def test_parallel_worker_exception_continues(self, mock_run, tmp_path):
        """One worker raising must not kill the whole sweep — other
        problems still complete, AND the crashed problem appears as a
        visible row in the JSONL output (with traceback in `error_message`).

        Regression guard for the silent-denominator-change bug: prior
        behaviour was that crashes vanished from JSONL, so a 60-problem
        sweep with 2 crashes reported 58/58 (100%). Now every problem
        produces a row — successes carry the normal fields, crashes
        carry `check_pass=False, run_correct=False, error_message=<tb>`."""
        from vera_bench.runner import run_benchmark

        def _side_effect(
            problem: dict[str, object], **kw: object
        ) -> list[ProblemResult]:
            if problem["id"] == "VB-X-2":
                raise RuntimeError("simulated worker crash")
            return [self._result(problem["id"])]

        mock_run.side_effect = _side_effect
        problems = [self._problem(f"VB-X-{i}") for i in range(4)]
        output = tmp_path / "crash.jsonl"

        results = run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=output,
            parallel=2,
        )

        # ALL 4 problems produce a result row — 3 successes + 1 crash.
        assert len(results) == 4
        ids = {r.problem_id for r in results}
        assert ids == {"VB-X-0", "VB-X-1", "VB-X-2", "VB-X-3"}
        # JSONL has 4 lines (the crash row IS written so report doesn't
        # silently shrink the denominator).
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 4
        # The crash row carries diagnostic detail in `error_message`.
        # Select by problem_id (the structural identifier), not by message
        # substring — message wording shouldn't be load-bearing in a row
        # selector.
        rows = [json.loads(ln) for ln in lines]
        crash_row = next(row for row in rows if row["problem_id"] == "VB-X-2")
        assert crash_row["check_pass"] is False
        assert "simulated worker crash" in crash_row["error_message"]
        assert "RuntimeError" in crash_row["error_message"]
        # And a traceback is included for post-hoc debugging.
        assert "Traceback" in crash_row["error_message"]

    @patch("vera_bench.runner.run_single_problem")
    def test_sequential_worker_exception_also_continues(self, mock_run, tmp_path):
        """Sequential (parallel=1) path has the SAME fault semantics as
        the parallel path: a single crashed problem doesn't abort the
        whole sweep, and the crash is recorded in JSONL.

        Closes the prior asymmetry where `--parallel 1` and `--parallel 2`
        had different fault behaviour on the same input (sequential aborted
        on a transient model-response error, parallel logged-and-continued).
        Four-hour sweeps now survive problem 47 of 60 regardless of N."""
        from vera_bench.runner import run_benchmark

        def _side_effect(
            problem: dict[str, object], **kw: object
        ) -> list[ProblemResult]:
            if problem["id"] == "VB-X-1":
                raise ValueError("LLM returned None mid-sweep")
            return [self._result(problem["id"])]

        mock_run.side_effect = _side_effect
        problems = [self._problem(f"VB-X-{i}") for i in range(3)]
        output = tmp_path / "seq-crash.jsonl"

        results = run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=output,
            parallel=1,
        )

        assert len(results) == 3
        ids = {r.problem_id for r in results}
        assert ids == {"VB-X-0", "VB-X-1", "VB-X-2"}
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 3
        rows = [json.loads(ln) for ln in lines]
        crash_row = next(row for row in rows if row["problem_id"] == "VB-X-1")
        assert "LLM returned None" in crash_row["error_message"]
        assert "ValueError" in crash_row["error_message"]

    @patch("vera_bench.runner.run_single_problem")
    def test_parallel_writes_are_serialised(self, mock_run, tmp_path):
        """JSONL writes from a parallel run must each be a complete,
        parseable JSON object (no torn writes from interleaving).

        Serialisation is provided by the `for fut in as_completed(...)`
        loop running on the main thread — workers only run `_run_one`
        and never touch `output_path`. This test exercises the property
        under load (20 problems × 8 workers) so a future refactor that
        accidentally moved the file write into workers would fail here."""
        from vera_bench.runner import run_benchmark

        mock_run.side_effect = lambda problem, **kw: [self._result(problem["id"])]
        # 20 problems × 8 workers gives many completion-order opportunities
        # for interleaved writes if a future refactor moved the file write
        # into workers. Note: this test does NOT prove anything about POSIX
        # O_APPEND atomicity (short writes < PIPE_BUF on POSIX would be
        # atomic anyway) — it proves the main-thread `as_completed` loop
        # is the actual serialisation source.
        problems = [self._problem(f"VB-X-{i:03d}") for i in range(20)]
        output = tmp_path / "concurrent.jsonl"

        run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=output,
            parallel=8,
        )

        # Every line must be parseable JSON; we lose data on torn writes.
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 20, f"expected 20 lines, got {len(lines)}"
        for ln in lines:
            obj = json.loads(ln)  # would raise if a line is torn
            assert obj["problem_id"].startswith("VB-X-")
        # Every expected ID is present exactly once
        ids = [json.loads(ln)["problem_id"] for ln in lines]
        assert sorted(ids) == sorted([f"VB-X-{i:03d}" for i in range(20)])

    @patch("vera_bench.runner.run_single_problem")
    def test_parallel_no_output_path_still_collects_results(self, mock_run, tmp_path):
        """`output_path=None` is a valid call shape — used by callers that
        only care about the in-memory list. Parallel path must skip the
        write block cleanly."""
        from vera_bench.runner import run_benchmark

        mock_run.side_effect = lambda problem, **kw: [self._result(problem["id"])]
        problems = [self._problem(f"VB-X-{i}") for i in range(3)]

        results = run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=None,
            parallel=4,  # more workers than problems is fine
        )

        assert len(results) == 3

    @patch("vera_bench.runner.Progress")
    @patch("vera_bench.runner.run_single_problem")
    def test_progress_advances_on_crash_path(self, mock_run, mock_progress, tmp_path):
        """`progress.advance` must fire even when a worker raises — both
        sequential and parallel paths. Otherwise the bar hangs at N-1/N
        if any problem crashes, misleading anyone watching the run.

        Catches a refactor that accidentally moved `advance` into an
        `else:` branch only reached on the success path."""
        from vera_bench.runner import run_benchmark

        def _side_effect(
            problem: dict[str, object], **kw: object
        ) -> list[ProblemResult]:
            if problem["id"] == "VB-X-1":
                raise RuntimeError("boom")
            return [self._result(problem["id"])]

        mock_run.side_effect = _side_effect

        progress_inst = MagicMock()
        mock_progress.return_value.__enter__.return_value = progress_inst
        progress_inst.add_task.return_value = "task-token"

        problems = [self._problem(f"VB-X-{i}") for i in range(4)]
        # Parallel path
        run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=tmp_path / "par.jsonl",
            parallel=2,
        )
        assert progress_inst.advance.call_count == 4, (
            f"parallel: advance should fire for every problem (3 successes "
            f"+ 1 crash = 4); got {progress_inst.advance.call_count}"
        )

        # Sequential path (reset and re-run)
        progress_inst.advance.reset_mock()
        run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=tmp_path / "seq.jsonl",
            parallel=1,
        )
        assert progress_inst.advance.call_count == 4, (
            f"sequential: advance should fire for every problem; "
            f"got {progress_inst.advance.call_count}"
        )

    @patch("vera_bench.runner.run_single_problem")
    def test_bench_and_vera_version_propagate_to_workers(self, mock_run, tmp_path):
        """`bench_version` / `vera_version` are captured by closure into
        `_run_one` in the parallel path; if a future refactor dropped
        them from the kwargs forwarded to `run_single_problem`, JSONL
        rows would silently get empty version strings.

        This test forwards observed kwargs so a regression where the
        closure stops propagating them surfaces immediately."""
        from vera_bench.runner import run_benchmark

        captured: list[dict] = []

        def _capture(problem: dict[str, object], **kw: object) -> list[ProblemResult]:
            captured.append({"id": problem["id"], **kw})
            return [self._result(problem["id"])]

        mock_run.side_effect = _capture
        problems = [self._problem(f"VB-X-{i}") for i in range(3)]

        run_benchmark(
            problems=problems,
            client=MagicMock(_model="mock"),
            skill_md="",
            vera=None,
            language="python",
            output_path=None,
            parallel=3,
            bench_version="0.0.11",
            vera_version="0.0.108",
        )

        assert len(captured) == 3
        for kw in captured:
            assert kw["bench_version"] == "0.0.11", (
                f"bench_version not forwarded: got {kw.get('bench_version')!r}"
            )
            assert kw["vera_version"] == "0.0.108", (
                f"vera_version not forwarded: got {kw.get('vera_version')!r}"
            )

    def test_run_command_accepts_parallel_flag(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        # Verify the flag parses; downstream failures (API key, etc.) are
        # expected and not what this test is about.
        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--parallel",
                "4",
                "--problem",
                "VB-T1-001",
            ],
        )
        assert "no such option" not in (result.output or "").lower()
        # Click signals usage/parse errors with exit_code == 2; anything
        # else (API-key missing, downstream errors) is fine.
        assert result.exit_code != 2

    def test_run_command_rejects_zero_parallel(self):
        """`click.IntRange(min=1)` rejects 0 and negative values at parse
        time (exit_code == 2). Catches the silent-fall-through-to-sequential
        bug that `type=int` would have allowed."""
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--parallel",
                "0",
            ],
        )
        assert result.exit_code == 2
        assert "parallel" in (result.output or "").lower()

    def test_run_command_rejects_negative_parallel(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--parallel",
                "-5",
            ],
        )
        assert result.exit_code == 2

    def test_run_command_parallel_default_is_one(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        # The --parallel help text should mention default=1
        result = CliRunner().invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "--parallel" in result.output
        # `show_default=True` makes Click print `[default: 1]`
        assert "1" in result.output


# === AILANG ===


class TestAilangLiteral:
    def test_positive_int(self):
        assert _ailang_literal(42) == "42"

    def test_zero(self):
        assert _ailang_literal(0) == "0"

    def test_negative_int(self):
        # AILANG parser needs parenthesised negatives to avoid being
        # parsed as subtraction in the harness-generated call site.
        assert _ailang_literal(-5) == "(-5)"

    def test_bool_true(self):
        # bool is a subclass of int in Python — checked first.
        assert _ailang_literal(True) == "true"

    def test_bool_false(self):
        assert _ailang_literal(False) == "false"

    def test_string(self):
        assert _ailang_literal("hello") == '"hello"'

    def test_string_with_quotes(self):
        assert _ailang_literal('say "hi"') == '"say \\"hi\\""'

    def test_string_with_backslash(self):
        assert _ailang_literal("a\\b") == '"a\\\\b"'

    def test_string_with_newline(self):
        assert _ailang_literal("a\nb") == '"a\\nb"'

    def test_string_with_tab(self):
        assert _ailang_literal("a\tb") == '"a\\tb"'

    def test_float(self):
        assert _ailang_literal(3.14) == "3.14"

    def test_list(self):
        assert _ailang_literal([1, 2, 3]) == "[1, 2, 3]"

    def test_nested_list(self):
        assert _ailang_literal([[1], [2]]) == "[[1], [2]]"

    def test_empty_list(self):
        assert _ailang_literal([]) == "[]"

    def test_list_of_strings(self):
        assert _ailang_literal(["a", "b"]) == '["a", "b"]'

    def test_list_of_negatives(self):
        # Each negative gets its own parens; no flattening.
        assert _ailang_literal([-1, -2]) == "[(-1), (-2)]"

    def test_fallback_to_str(self):
        # Unknown types fall through to `str(value)`.
        class Custom:
            def __str__(self):
                return "custom"

        assert _ailang_literal(Custom()) == "custom"


class TestStripAilangMain:
    def test_removes_block_main(self):
        # NB: omit `! {IO}` from the def line — the strip function's brace
        # counting treats `{IO}` as a balanced block (see xfail below).
        code = (
            "module benchmark/solution\n\n"
            "export func foo(x: int) -> int = x + 1\n\n"
            "export func main() -> () {\n"
            "  println(show(foo(5)))\n"
            "}\n"
        )
        result = _strip_ailang_main(code)
        assert "func foo" in result
        assert "func main" not in result
        assert "println" not in result

    def test_removes_single_line_block_main(self):
        # Single-line block form, no effect annotation in the def line.
        code = (
            "module M\n\n"
            "func helper() -> int = 1\n\n"
            'export func main() -> () { println("hi") }\n'
        )
        result = _strip_ailang_main(code)
        assert "func helper" in result
        assert "func main" not in result
        assert "hi" not in result

    def test_removes_equals_form_main(self):
        code = (
            "module M\n\n"
            "export func helper() -> int = 42\n\n"
            "export func main() -> () ! {IO} = println(show(helper()))\n"
        )
        result = _strip_ailang_main(code)
        assert "func helper" in result
        assert "func main" not in result

    def test_removes_main_with_pure_modifier(self):
        # The regex accepts `pure func main` even though pure main is unusual.
        code = "module M\n\nfunc foo() -> int = 1\n\npure func main() -> () = ()\n"
        result = _strip_ailang_main(code)
        assert "func foo" in result
        assert "func main" not in result

    def test_removes_main_without_export(self):
        code = 'module M\n\nfunc main() -> () ! {IO} {\n  println("x")\n}\n'
        result = _strip_ailang_main(code)
        assert "func main" not in result

    def test_keeps_code_without_main(self):
        code = "module M\n\nexport func helper(x: int) -> int = x * 2\n"
        result = _strip_ailang_main(code)
        assert "func helper" in result
        assert result.strip() == code.strip()

    def test_preserves_code_after_main(self):
        code = (
            "module M\n\n"
            "export func main() -> () ! {IO} {\n"
            '  println("x")\n'
            "}\n\n"
            "export func helper(x: int) -> int = x + 1\n"
        )
        result = _strip_ailang_main(code)
        assert "func main" not in result
        assert "func helper" in result

    def test_strips_indented_continuation_after_equals(self):
        # `export func main = ...` with continuation lines indented
        # under it should all be eaten. No effect annotation on def line.
        code = (
            "module M\n\n"
            "export func helper() -> int = 1\n\n"
            "export func main() -> () =\n"
            "  println(\n"
            "    show(helper())\n"
            "  )\n"
        )
        result = _strip_ailang_main(code)
        assert "func helper" in result
        assert "func main" not in result
        assert "println" not in result
        assert "show(helper())" not in result

    def test_io_effect_annotation_in_def_line(self):
        """Regression for C1: prior brace-counting heuristic mis-classified
        `! {IO}` effect annotations as balanced single-line blocks and
        left the body in place. The indentation-based strategy handles
        all three multi-line forms (block `{`/`}`, equals form, single
        line) correctly regardless of effect-annotation content.

        This is the canonical AILANG main signature the LLM produces
        when it disobeys the 'no main' instruction — 60 of our own
        baselines use this exact form."""
        code = (
            "module M\n\n"
            "func foo() -> int = 1\n\n"
            "export func main() -> () ! {IO} {\n"
            "  println(show(foo()))\n"
            "}\n"
        )
        result = _strip_ailang_main(code)
        assert "func foo" in result
        assert "func main" not in result
        assert "println" not in result
        assert "show(foo())" not in result

    def test_io_effect_annotation_equals_form(self):
        """Equals form with `! {IO}` annotation — same regression class
        as the block form above. Indented continuation lines are eaten
        as the body."""
        code = (
            "module M\n\n"
            "func foo() -> int = 1\n\n"
            "export func main() -> () ! {IO} =\n"
            "  println(\n"
            "    show(foo())\n"
            "  )\n"
        )
        result = _strip_ailang_main(code)
        assert "func foo" in result
        assert "func main" not in result
        assert "println" not in result

    def test_preserves_comment_attached_to_next_def_after_main(self):
        """Edge case: a comment between a stripped main and the next
        top-level def stays with the def (col-0 lines stop the swallow
        loop), not eaten as part of main's body."""
        code = (
            "module M\n\n"
            "export func main() -> () = ()\n\n"
            "-- helper that does X\n"
            "export func helper() -> int = 1\n"
        )
        result = _strip_ailang_main(code)
        assert "func main" not in result
        assert "-- helper that does X" in result
        assert "func helper" in result

    def test_does_not_match_main_substring(self):
        # `mainframe` should NOT be matched as `main` due to `\b`.
        code = "module M\n\nexport func mainframe() -> int = 7\n"
        result = _strip_ailang_main(code)
        assert "func mainframe" in result


class TestEvaluateAilangCode:
    def _sample_problem(self, test_cases=None, entry_point="absolute_value"):
        return {
            "id": "VB-T1-001",
            "entry_point": entry_point,
            "test_cases": test_cases or [],
        }

    def _mock_subprocess(self, returncode=0, stdout="", stderr=""):
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    @patch("vera_bench.runner.subprocess.run")
    def test_check_pass_no_test_cases(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        mock_run.side_effect = [self._mock_subprocess(returncode=0)]  # ailang check
        code = (
            "module benchmark/solution\n\n"
            "export func absolute_value(x: int) -> int = "
            "if x < 0 then 0 - x else x\n"
        )
        result = _evaluate_ailang_code(code, self._sample_problem(), tmp_path, 1)
        assert result["check_pass"] is True
        assert result["run_correct"] is None
        assert result["error_message"] is None

    @patch("vera_bench.runner.subprocess.run")
    def test_check_fail_real_compile_error(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        mock_run.return_value = self._mock_subprocess(
            returncode=1, stderr="Error TC_001: type mismatch"
        )
        code = (
            "module benchmark/solution\n\n"
            "export func absolute_value(x: int) -> int = true\n"
        )
        result = _evaluate_ailang_code(code, self._sample_problem(), tmp_path, 1)
        assert result["check_pass"] is False
        assert "type mismatch" in result["error_message"]

    @patch("vera_bench.runner.subprocess.run")
    def test_check_fail_missing_main_tolerated(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        # "missing main" on the bare-module check is the ONE non-zero exit
        # we tolerate, because the harness adds the per-test-case main.
        mock_run.side_effect = [
            self._mock_subprocess(returncode=1, stderr="error: missing main"),
            # then for each test case, ailang run
            self._mock_subprocess(returncode=0, stdout="42"),
        ]
        result = _evaluate_ailang_code(
            "module benchmark/solution\n\n"
            "export func absolute_value(x: int) -> int = "
            "if x < 0 then 0 - x else x\n",
            self._sample_problem(test_cases=[{"args": [-42], "expected": 42}]),
            tmp_path,
            1,
        )
        assert result["check_pass"] is True
        assert result["tests_passed"] == 1
        assert result["run_correct"] is True

    @patch("vera_bench.runner.subprocess.run")
    def test_ailang_not_found(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        mock_run.side_effect = FileNotFoundError
        result = _evaluate_ailang_code(
            "module M\n\nexport func absolute_value(x: int) -> int = x\n",
            self._sample_problem(),
            tmp_path,
            1,
        )
        assert result["check_pass"] is False
        assert "ailang not found" in result["error_message"]

    @patch("vera_bench.runner.subprocess.run")
    def test_check_timeout(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ailang", timeout=30)
        result = _evaluate_ailang_code(
            "module M\n\nexport func absolute_value(x: int) -> int = x\n",
            self._sample_problem(),
            tmp_path,
            1,
        )
        assert result["check_pass"] is False
        assert "timed out" in result["error_message"]

    @patch("vera_bench.runner.subprocess.run")
    def test_with_test_cases_all_pass(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        mock_run.side_effect = [
            self._mock_subprocess(returncode=0),  # ailang check
            self._mock_subprocess(returncode=0, stdout="42"),  # tc1
            self._mock_subprocess(returncode=0, stdout="5"),  # tc2
        ]
        problem = self._sample_problem(
            test_cases=[
                {"args": [42], "expected": 42},
                {"args": [-5], "expected": 5},
            ]
        )
        result = _evaluate_ailang_code(
            "module benchmark/solution\n\n"
            "export func absolute_value(x: int) -> int = "
            "if x < 0 then 0 - x else x\n",
            problem,
            tmp_path,
            1,
        )
        assert result["check_pass"] is True
        assert result["tests_total"] == 2
        assert result["tests_passed"] == 2
        assert result["run_correct"] is True

    @patch("vera_bench.runner.subprocess.run")
    def test_with_test_cases_partial_pass(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        mock_run.side_effect = [
            self._mock_subprocess(returncode=0),  # ailang check
            self._mock_subprocess(returncode=0, stdout="42"),  # tc1 pass
            self._mock_subprocess(returncode=0, stdout="99"),  # tc2 fail
        ]
        problem = self._sample_problem(
            test_cases=[
                {"args": [42], "expected": 42},
                {"args": [-5], "expected": 5},
            ]
        )
        result = _evaluate_ailang_code(
            "module M\n\nexport func absolute_value(x: int) -> int = x\n",
            problem,
            tmp_path,
            1,
        )
        assert result["tests_total"] == 2
        assert result["tests_passed"] == 1
        assert result["run_correct"] is False

    @patch("vera_bench.runner.subprocess.run")
    def test_run_timeout_skips_test_case(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        mock_run.side_effect = [
            self._mock_subprocess(returncode=0),  # check
            subprocess.TimeoutExpired(cmd="ailang", timeout=30),  # tc1 times out
        ]
        problem = self._sample_problem(
            test_cases=[{"args": [42], "expected": 42}],
        )
        result = _evaluate_ailang_code(
            "module M\n\nexport func absolute_value(x: int) -> int = x\n",
            problem,
            tmp_path,
            1,
        )
        assert result["check_pass"] is True
        assert result["tests_passed"] == 0
        assert result["run_correct"] is False

    @patch("vera_bench.runner.subprocess.run")
    def test_run_non_zero_exit_skips_test_case(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        mock_run.side_effect = [
            self._mock_subprocess(returncode=0),  # check
            self._mock_subprocess(returncode=1, stderr="runtime error"),  # tc1 fail
        ]
        problem = self._sample_problem(
            test_cases=[{"args": [42], "expected": 42}],
        )
        result = _evaluate_ailang_code(
            "module M\n\nexport func absolute_value(x: int) -> int = x\n",
            problem,
            tmp_path,
            1,
        )
        assert result["tests_passed"] == 0
        assert result["run_correct"] is False

    @patch("vera_bench.runner.subprocess.run")
    def test_missing_entry_point_no_test_cases(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        # Empty module — entry point not defined. Should fail check
        # without ever invoking subprocess.
        problem = self._sample_problem(entry_point="absolute_value")
        result = _evaluate_ailang_code(
            "module benchmark/solution\n",  # no functions defined
            problem,
            tmp_path,
            1,
        )
        assert result["check_pass"] is False
        assert "did not define entry point" in result["error_message"]
        # subprocess.run should never have been called
        assert mock_run.call_count == 0

    @patch("vera_bench.runner.subprocess.run")
    def test_missing_entry_point_with_test_cases(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        problem = self._sample_problem(
            test_cases=[{"args": [42], "expected": 42}],
            entry_point="absolute_value",
        )
        result = _evaluate_ailang_code(
            "module benchmark/solution\n",  # no functions
            problem,
            tmp_path,
            1,
        )
        assert result["check_pass"] is False
        assert result["tests_total"] == 1
        assert result["run_correct"] is False
        assert mock_run.call_count == 0

    @patch("vera_bench.runner.subprocess.run")
    def test_adds_module_header_when_missing(self, mock_run, tmp_path):
        from vera_bench.runner import _evaluate_ailang_code

        # LLM forgot the `module ...` line. Harness should inject one.
        mock_run.side_effect = [self._mock_subprocess(returncode=0)]
        code = "export func absolute_value(x: int) -> int = x\n"
        result = _evaluate_ailang_code(code, self._sample_problem(), tmp_path, 1)
        assert result["check_pass"] is True
        # The file that gets written should contain a synthesised
        # module header — verify by reading what the harness wrote.
        written = list(tmp_path.glob("*_check_*.ail"))
        assert len(written) == 1
        contents = written[0].read_text()
        assert "module benchmark/solution" in contents

    @patch("vera_bench.runner.subprocess.run")
    def test_check_subprocess_contract(self, mock_run, tmp_path):
        """I1 contract test: pin the exact argv + env the `ailang check`
        invocation uses. A regression dropping --quiet would cause tracing
        on stdout → silent test-pass miscount via the line-counting parser.
        A regression dropping *_API_KEY scrubbing could leak credentials."""
        import os

        from vera_bench.runner import _evaluate_ailang_code

        mock_run.side_effect = [self._mock_subprocess(returncode=0)]
        os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"
        try:
            _evaluate_ailang_code(
                "module M\n\nexport func absolute_value(x: int) -> int = x\n",
                self._sample_problem(),
                tmp_path,
                1,
            )
        finally:
            del os.environ["ANTHROPIC_API_KEY"]

        # Verify argv
        argv = mock_run.call_args.args[0]
        assert argv[0] == "ailang"
        assert argv[1] == "check"
        assert "--relax-modules" in argv

        # Verify env: AILANG_TRACE=off and *_API_KEY stripped
        env = mock_run.call_args.kwargs["env"]
        assert env.get("AILANG_TRACE") == "off"
        assert "ANTHROPIC_API_KEY" not in env, (
            "API keys MUST be scrubbed before invoking ailang subprocess"
        )

    @patch("vera_bench.runner.subprocess.run")
    def test_run_subprocess_contract(self, mock_run, tmp_path):
        """I1 contract test: pin the exact argv + env the `ailang run`
        invocation uses (--quiet matters most here — without it, AILANG
        tracing escapes onto stdout and confuses the line-counting parser
        that matches each line to a test_case)."""
        import os

        from vera_bench.runner import _evaluate_ailang_code

        # Two calls: check (success), then run (success)
        mock_run.side_effect = [
            self._mock_subprocess(returncode=0),  # check
            self._mock_subprocess(returncode=0, stdout="42"),  # run
        ]
        os.environ["OPENAI_API_KEY"] = "fake-key-for-test"
        try:
            _evaluate_ailang_code(
                "module M\n\nexport func absolute_value(x: int) -> int = x\n",
                self._sample_problem(test_cases=[{"args": [42], "expected": 42}]),
                tmp_path,
                1,
            )
        finally:
            del os.environ["OPENAI_API_KEY"]

        # Second call is the `ailang run` invocation
        argv = mock_run.call_args_list[1].args[0]
        assert argv[:2] == ["ailang", "run"]
        # --quiet is load-bearing: suppresses AILANG's standard tracing
        # output so stdout contains ONLY println() output (one line per
        # test case). Without it, the line-count match in
        # baseline_runner._aver_output_matches would misalign.
        assert "--quiet" in argv
        assert "--caps" in argv
        # IO capability is required for println()
        caps_idx = argv.index("--caps")
        assert argv[caps_idx + 1] == "IO"
        # Entry point is always 'main' (the harness-synthesised one)
        assert "--entry" in argv
        entry_idx = argv.index("--entry")
        assert argv[entry_idx + 1] == "main"

        env = mock_run.call_args_list[1].kwargs["env"]
        assert env.get("AILANG_TRACE") == "off"
        assert "OPENAI_API_KEY" not in env


# === AILANG prompts ===


class TestLoadAilangPrompt:
    def test_loads_from_file(self, tmp_path):
        from vera_bench.prompts import load_ailang_prompt

        prompt_file = tmp_path / "ailang_prompt.md"
        prompt_file.write_text("# AILANG Teaching Prompt\nUse `export func`.\n")
        result = load_ailang_prompt(prompt_file)
        assert "AILANG Teaching Prompt" in result
        assert "export func" in result

    @patch("subprocess.run")
    def test_loads_from_cli_when_source_none(self, mock_run):
        # `prompts.py` does `import subprocess` inside the function body,
        # so we patch the global `subprocess.run` directly.
        from vera_bench.prompts import load_ailang_prompt

        mock_run.return_value = MagicMock(
            returncode=0, stdout="# Embedded AILANG prompt content\n", stderr=""
        )
        result = load_ailang_prompt(None)
        assert "Embedded AILANG prompt content" in result
        # First positional arg of the subprocess.run call is the cmd list
        args = mock_run.call_args.args[0]
        assert args[:2] == ["ailang", "prompt"]

    @patch("subprocess.run")
    def test_ailang_not_found(self, mock_run):
        from vera_bench.prompts import load_ailang_prompt

        mock_run.side_effect = FileNotFoundError
        with pytest.raises(RuntimeError, match="ailang not found"):
            load_ailang_prompt(None)

    @patch("subprocess.run")
    def test_ailang_prompt_timeout(self, mock_run):
        from vera_bench.prompts import load_ailang_prompt

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ailang", timeout=10)
        with pytest.raises(RuntimeError, match="timed out"):
            load_ailang_prompt(None)

    @patch("subprocess.run")
    def test_ailang_prompt_non_zero_exit(self, mock_run):
        from vera_bench.prompts import load_ailang_prompt

        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="unknown subcommand"
        )
        with pytest.raises(RuntimeError, match="failed.*unknown subcommand"):
            load_ailang_prompt(None)

    @patch("subprocess.run")
    def test_ailang_prompt_non_zero_exit_stdout_only(self, mock_run):
        """Some CLI versions write the failure message to stdout instead of
        stderr. We must coalesce both streams rather than crash with
        TypeError on `None[:200]`."""
        from vera_bench.prompts import load_ailang_prompt

        mock_run.return_value = MagicMock(
            returncode=1, stdout="error on stdout instead", stderr=None
        )
        with pytest.raises(RuntimeError, match="failed.*error on stdout"):
            load_ailang_prompt(None)

    @patch("subprocess.run")
    def test_ailang_prompt_non_zero_exit_no_output(self, mock_run):
        """Neither stdout nor stderr populated — still raises RuntimeError
        (not TypeError) with a placeholder message."""
        from vera_bench.prompts import load_ailang_prompt

        mock_run.return_value = MagicMock(returncode=1, stdout=None, stderr=None)
        with pytest.raises(RuntimeError, match="non-zero exit"):
            load_ailang_prompt(None)


class TestAilangPrompt:
    def test_build_ailang_prompt(self):
        from vera_bench.prompts import build_ailang_prompt

        problem = {
            "description": "Compute absolute value",
            "description_neutral": "Return the absolute value of an integer.",
            "entry_point": "absolute_value",
        }
        result = build_ailang_prompt(problem, "# AILANG spec\n")
        assert "absolute_value" in result["user"]
        assert "AILANG" in result["system"]
        assert "# AILANG spec" in result["system"]
        assert "Return the absolute value" in result["user"]
        # Critical instructions — these are what the harness depends on
        assert "module benchmark/solution" in result["user"]
        assert "export func" in result["user"]
        assert "main" in result["user"].lower()  # explicit "no main" instruction

    def test_ailang_prompt_uses_neutral(self):
        from vera_bench.prompts import build_ailang_prompt

        problem = {
            "description": "Vera-flavoured description with @Int",
            "description_neutral": "Neutral description",
            "entry_point": "test",
        }
        result = build_ailang_prompt(problem, "spec")
        assert "Neutral description" in result["user"]
        assert "Vera-flavoured" not in result["user"]

    def test_build_ailang_fix_prompt(self):
        from vera_bench.prompts import build_ailang_fix_prompt

        result = build_ailang_fix_prompt(
            "module M\n\nexport func bad() -> int = true\n",
            "Error TC_001: type mismatch (int vs bool)",
            "# AILANG spec\n",
        )
        assert "bad()" in result["user"]
        assert "type mismatch" in result["user"]
        assert "Fix" in result["user"]
        assert "# AILANG spec" in result["system"]


# === AILANG CLI dispatch ===


class TestAilangCLI:
    def test_run_command_accepts_ailang(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--language",
                "ailang",
            ],
        )
        # The Click option accepted "ailang" — anything else is a downstream
        # error (missing API key, missing ailang binary), not a Click error.
        assert "invalid" not in (result.output or "").lower()

    def test_run_ailang_not_on_path(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        # Mock client creation + prompt load to isolate the ailang version
        # check; that's the call we want to test the failure mode of.
        with (
            patch("vera_bench.models.create_client"),
            patch(
                "vera_bench.prompts.load_ailang_prompt",
                return_value="# mock ailang prompt",
            ),
            patch("subprocess.run", side_effect=FileNotFoundError),
        ):
            result = CliRunner().invoke(
                main,
                [
                    "run",
                    "--model",
                    "claude-haiku-4-5-20251001",
                    "--language",
                    "ailang",
                ],
            )
        assert result.exit_code != 0
        assert "ailang not found" in (result.output or "")

    def test_run_ailang_version_timeout(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        with (
            patch("vera_bench.models.create_client"),
            patch(
                "vera_bench.prompts.load_ailang_prompt",
                return_value="# mock ailang prompt",
            ),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="ailang", timeout=5),
            ),
        ):
            result = CliRunner().invoke(
                main,
                [
                    "run",
                    "--model",
                    "claude-haiku-4-5-20251001",
                    "--language",
                    "ailang",
                ],
            )
        assert result.exit_code != 0
        assert "timed out" in (result.output or "").lower()

    def test_run_ailang_does_not_warn_on_skill_md(self, tmp_path):
        from click.testing import CliRunner

        from vera_bench.cli import main

        skill = tmp_path / "ailang_skill.md"
        skill.write_text("# AILANG override\n", encoding="utf-8")
        result = CliRunner().invoke(
            main,
            [
                "run",
                "--model",
                "claude-haiku-4-5-20251001",
                "--language",
                "ailang",
                "--skill-md",
                str(skill),
                "--problem",
                "VB-T1-001",
            ],
        )
        # AILANG legitimately consumes --skill-md as its language-reference
        # doc — so the "Warning: --skill-md is ignored" line MUST NOT fire.
        assert "--skill-md is ignored" not in (result.output or "")

    def test_baselines_command_accepts_ailang(self):
        from click.testing import CliRunner

        from vera_bench.cli import main

        result = CliRunner().invoke(main, ["baselines", "--language", "ailang"])
        assert "invalid" not in (result.output or "").lower()

    def test_run_ailang_version_nonzero_exit(self):
        """If `ailang --version` exits non-zero, we abort with a clear error."""
        from click.testing import CliRunner

        from vera_bench.cli import main

        # Return a subprocess result with returncode != 0
        bad_proc = MagicMock(returncode=2, stdout="", stderr="oops")
        with (
            patch("vera_bench.models.create_client"),
            patch(
                "vera_bench.prompts.load_ailang_prompt",
                return_value="# mock ailang prompt",
            ),
            patch("subprocess.run", return_value=bad_proc),
        ):
            result = CliRunner().invoke(
                main,
                [
                    "run",
                    "--model",
                    "claude-haiku-4-5-20251001",
                    "--language",
                    "ailang",
                ],
            )
        assert result.exit_code != 0
        assert "ailang --version failed" in (result.output or "")

    def test_run_ailang_full_path_success(self, tmp_path):
        """End-to-end mocked dispatch: version detected -> run_benchmark called.

        Covers the cli.py 240-296 slug-building, console echo, and summary-print
        paths that fire when `ailang --version` returns cleanly.
        """
        from click.testing import CliRunner

        from vera_bench.cli import main

        ver_proc = MagicMock(returncode=0, stdout="ailang 0.21.0\n", stderr="")

        with (
            patch("vera_bench.models.create_client"),
            patch(
                "vera_bench.prompts.load_ailang_prompt",
                return_value="# mock ailang prompt",
            ),
            patch("subprocess.run", return_value=ver_proc),
            patch(
                "vera_bench.runner.run_benchmark",
                return_value=[],  # no problems run -> skips _print_metrics
            ),
        ):
            result = CliRunner().invoke(
                main,
                [
                    "run",
                    "--model",
                    "claude-haiku-4-5-20251001",
                    "--language",
                    "ailang",
                    "--output-dir",
                    str(tmp_path),
                    "--problem",
                    "VB-T1-001",  # single problem to keep it fast
                ],
            )
        assert result.exit_code == 0, result.output
        # The AILANG version was echoed to the console (cli.py:272-273)
        assert "AILANG:" in (result.output or "")
        # The filename slug includes the AILANG version (cli.py:256-257) —
        # appears in the "Output: ..." line printed by cli.py:274.
        assert "ailang-0-21-0" in (result.output or "")
