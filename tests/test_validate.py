"""Tests for the validation module."""

import json
from pathlib import Path

import pytest

from vera_bench.validate import REQUIRED_FIELDS

REPO_ROOT = Path(__file__).parent.parent
PROBLEMS_DIR = REPO_ROOT / "problems"
SOLUTIONS_DIR = REPO_ROOT / "solutions"


def _collect_problem_files():
    return sorted(PROBLEMS_DIR.rglob("VB_*.json"))


@pytest.fixture(scope="session")
def problem_files():
    return _collect_problem_files()


class TestProblemSchema:
    """Verify all problem JSON files have the required schema."""

    @pytest.mark.parametrize(
        "problem_file",
        _collect_problem_files(),
        ids=lambda p: p.stem,
    )
    def test_required_fields(self, problem_file: Path):
        with open(problem_file, encoding="utf-8") as f:
            problem = json.load(f)
        missing = [field for field in REQUIRED_FIELDS if field not in problem]
        assert not missing, f"Missing fields: {missing}"

    @pytest.mark.parametrize(
        "problem_file",
        _collect_problem_files(),
        ids=lambda p: p.stem,
    )
    def test_id_format(self, problem_file: Path):
        with open(problem_file, encoding="utf-8") as f:
            problem = json.load(f)
        pid = problem["id"]
        assert pid.startswith("VB-T"), f"ID must start with VB-T, got {pid}"

    @pytest.mark.parametrize(
        "problem_file",
        _collect_problem_files(),
        ids=lambda p: p.stem,
    )
    def test_tier_matches_directory(self, problem_file: Path):
        with open(problem_file, encoding="utf-8") as f:
            problem = json.load(f)
        dir_tier = int(problem_file.parent.name.replace("tier", ""))
        assert problem["tier"] == dir_tier, (
            f"Tier {problem['tier']} in JSON but file is in tier{dir_tier}/"
        )

    @pytest.mark.parametrize(
        "problem_file",
        _collect_problem_files(),
        ids=lambda p: p.stem,
    )
    def test_vera_solution_exists(self, problem_file: Path):
        with open(problem_file, encoding="utf-8") as f:
            problem = json.load(f)
        prefix = problem["id"] + "_"
        matches = list((SOLUTIONS_DIR / "vera").glob(f"{prefix}*.vera"))
        assert len(matches) == 1, (
            f"Expected 1 .vera file for {problem['id']}, found {len(matches)}"
        )

    @pytest.mark.parametrize(
        "problem_file",
        _collect_problem_files(),
        ids=lambda p: p.stem,
    )
    def test_contracts_structure(self, problem_file: Path):
        with open(problem_file, encoding="utf-8") as f:
            problem = json.load(f)
        contracts = problem["contracts"]
        assert "requires" in contracts, "Missing contracts.requires"
        assert "ensures" in contracts, "Missing contracts.ensures"
        assert "effects" in contracts, "Missing contracts.effects"
        assert isinstance(contracts["requires"], list), "requires must be a list"
        assert isinstance(contracts["ensures"], list), "ensures must be a list"


class TestVeraRunner:
    """Test the vera_runner module."""

    def test_import(self):
        from vera_bench.vera_runner import VeraRunner

        runner = VeraRunner()
        assert runner.vera is not None

    def test_check_result_fields(self):
        from vera_bench.vera_runner import CheckResult

        r = CheckResult(passed=True, exit_code=0, stdout="", stderr="")
        assert r.passed is True
        assert r.diagnostics == []

    def test_version(self):
        from vera_bench.vera_runner import VeraRunner

        runner = VeraRunner()
        ver = runner.version()
        assert ver != "unknown"
        assert "." in ver  # e.g. "0.0.105"

    def test_verify_result_fields(self):
        from vera_bench.vera_runner import VerifyResult

        r = VerifyResult(
            passed=True,
            exit_code=0,
            stdout="",
            stderr="",
            tier1_verified=3,
            tier3_runtime=0,
            total=3,
        )
        assert r.tier1_verified == 3
        assert r.tier3_runtime == 0


class TestPrompts:
    """Test prompt construction."""

    def test_full_spec_prompt(self):
        from vera_bench.prompts import build_full_spec_prompt

        problem = {
            "description": "Test problem",
            "signature": "public fn test(@Int -> @Int)",
            "contracts": {
                "requires": ["true"],
                "ensures": ["@Int.result >= 0"],
                "effects": "pure",
            },
        }
        result = build_full_spec_prompt(problem, "SKILL.md content here")
        assert "Test problem" in result["user"]
        assert "requires(true)" in result["user"]
        assert "SKILL.md content here" in result["system"]

    def test_spec_from_nl_prompt(self):
        from vera_bench.prompts import build_spec_from_nl_prompt

        problem = {
            "description": "Test problem",
            "signature": "public fn test(@Int -> @Int)",
            "contracts": {
                "requires": ["true"],
                "ensures": ["true"],
                "effects": "pure",
            },
        }
        result = build_spec_from_nl_prompt(problem, "SKILL")
        assert "Test problem" in result["user"]
        assert "requires(true)" not in result["user"]

    def test_fix_prompt(self):
        from vera_bench.prompts import build_fix_prompt

        result = build_fix_prompt("original code", "Error: type mismatch")
        assert "Error: type mismatch" in result["user"]
        assert "original code" in result["user"]


class TestLoadSkillMd:
    def test_load_from_url(self):
        from unittest.mock import MagicMock, patch

        from vera_bench.prompts import SKILL_MD_URL, load_skill_md

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"# Vera SKILL.md\nTest content"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            content = load_skill_md(SKILL_MD_URL)
        assert "Vera" in content

    def test_load_from_file(self, tmp_path):
        from vera_bench.prompts import load_skill_md

        f = tmp_path / "test.md"
        f.write_text("test content", encoding="utf-8")
        assert load_skill_md(f) == "test content"

    def test_load_default(self):
        from unittest.mock import MagicMock, patch

        from vera_bench.prompts import load_skill_md

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"# Vera"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            content = load_skill_md()
        assert "Vera" in content

    def test_bad_url(self):
        import urllib.error
        from unittest.mock import patch

        from vera_bench.prompts import load_skill_md

        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("not found"),
            ),
            pytest.raises(RuntimeError, match="Failed to fetch"),
        ):
            load_skill_md("https://veralang.dev/nonexistent")


class TestCLI:
    """Test CLI setup."""

    def test_cli_group(self):
        from vera_bench.cli import main

        assert main.name == "main"

    def test_validate_command_exists(self):
        from vera_bench.cli import main

        assert "validate" in [cmd for cmd in main.commands]

    def test_run_command_exists(self):
        from vera_bench.cli import main

        assert "run" in [cmd for cmd in main.commands]
