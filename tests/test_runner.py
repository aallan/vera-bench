"""Tests for the LLM runner, models, metrics, and report modules."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vera_bench.metrics import compute_metrics
from vera_bench.models import LLMResponse, create_client
from vera_bench.runner import ProblemResult, extract_vera_code

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
        assert d["error_message"] == "type mismatch"


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
        assert m.check_rate == 0.0

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
