"""Every language's LLM evaluator must grade its own canonical as correct.

The multi-agent review of PR #112 found that `vera-bench baselines`
cannot protect the LLM grading path: baselines run the canonical mains
(their own `main` prints the answers), while graded code goes through
per-language argument synthesis the baselines never touch. That blind
spot hid two criticals — the aver/AILANG evaluators rendering ADT
arguments as Python dict reprs, and the AILANG check step failing every
IO solution — both of which scored known-correct code as wrong.

A canonical solution is by definition a correct answer, so any
`run_correct is not True` from an evaluator here is a harness bug, full
stop. Aver and AILANG cover all fourteen newly-graded problems (CI has
no binaries for them, so these run only where it matters — on the
machine that runs sweeps); Vera, Python and TypeScript cover one problem
per newly-graded shape, their paths being otherwise pinned by hermetic
decline and baseline tests.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vera_bench.runner import (
    _evaluate_ailang_code,
    _evaluate_aver_code,
    _evaluate_code,
    _evaluate_python_code,
    _evaluate_typescript_code,
)
from vera_bench.vera_runner import VeraRunner

REPO_ROOT = Path(__file__).parent.parent

#: The problems graded for the first time in 0.0.17/0.0.18 — the ones
#: whose evaluator paths had never run before this branch.
NEWLY_GRADED = [
    "T2_001",
    "T2_002",
    "T2_003",
    "T2_006",
    "T2_007",
    "T2_008",
    "T2_009",
    "T2_010",
    "T3_001",
    "T3_002",
    "T3_003",
    "T3_004",
    "T3_005",
    "T3_006",
    "T3_007",
    "T3_008",
    "T3_009",
    "T3_010",
    "T4_006",
    "T4_009",
    "T5_002",
    "T5_005",
    "T5_008",
    "T5_010",
]
#: One representative per shape for the languages whose paths carry
#: hermetic coverage elsewhere: ADT argument, ADT return, IO.
SHAPE_SAMPLE = ["T3_002", "T3_009", "T5_008"]


def load_problem(pid: str) -> dict:
    matches = list(REPO_ROOT.glob(f"problems/tier*/*{pid}*.json"))
    assert matches, pid
    return json.loads(matches[0].read_text())


def load_solution(lang: str, pid: str, ext: str) -> str:
    matches = list(REPO_ROOT.glob(f"solutions/{lang}/VB?{pid}_*.{ext}"))
    assert matches, (lang, pid)
    return matches[0].read_text()


@pytest.mark.parametrize("pid", NEWLY_GRADED)
@pytest.mark.skipif(shutil.which("aver") is None, reason="aver not on PATH")
def test_aver_evaluator_grades_its_canonical(pid, tmp_path):
    problem = load_problem(pid)
    result = _evaluate_aver_code(
        load_solution("aver", pid, "av"), problem, tmp_path, attempt=1
    )
    assert result["run_correct"] is True, result


@pytest.mark.parametrize("pid", NEWLY_GRADED)
@pytest.mark.skipif(shutil.which("ailang") is None, reason="ailang not on PATH")
def test_ailang_evaluator_grades_its_canonical(pid, tmp_path):
    problem = load_problem(pid)
    result = _evaluate_ailang_code(
        load_solution("ailang", pid, "ail"), problem, tmp_path, attempt=1
    )
    assert result["run_correct"] is True, result


@pytest.mark.parametrize("pid", SHAPE_SAMPLE)
@pytest.mark.skipif(shutil.which("vera") is None, reason="vera not on PATH")
def test_vera_evaluator_grades_its_canonical(pid, tmp_path):
    problem = load_problem(pid)
    result = _evaluate_code(
        load_solution("vera", pid.replace("_", "-"), "vera"),
        problem,
        VeraRunner(),
        tmp_path,
        attempt=1,
    )
    assert result["run_correct"] is True, result


@pytest.mark.parametrize("pid", SHAPE_SAMPLE)
def test_python_evaluator_grades_its_canonical(pid, tmp_path):
    problem = load_problem(pid)
    result = _evaluate_python_code(
        load_solution("python", pid, "py"), problem, tmp_path, attempt=1
    )
    assert result["run_correct"] is True, result


@pytest.mark.parametrize("pid", SHAPE_SAMPLE)
@pytest.mark.skipif(
    shutil.which("tsx") is None and shutil.which("npx") is None,
    reason="tsx/npx not on PATH",
)
def test_typescript_evaluator_grades_its_canonical(pid, tmp_path):
    problem = load_problem(pid)
    result = _evaluate_typescript_code(
        load_solution("typescript", pid, "ts"), problem, tmp_path, attempt=1
    )
    assert result["run_correct"] is True, result


@pytest.mark.skipif(shutil.which("vera") is None, reason="vera not on PATH")
class TestRenamedAdtType:
    """A model may rename the TYPE, not just the constructors.

    match_constructors deliberately tolerates it, but the generated
    probe_eq used to hard-code the problem's type name — so the wrapper
    could not compile against the model's own code and a correct
    solution was recorded as a wrong answer (multi-agent review of #112,
    verified against real vera). Worst in spec-from-NL, the mode where
    inventing the name is the point.
    """

    def _run(self, pid: str, transform) -> dict:
        problem = load_problem(pid)
        src = transform(load_solution("vera", pid.replace("_", "-"), "vera"))
        return _evaluate_code(src, problem, VeraRunner(), Path(self.tmp), attempt=1)

    @pytest.fixture(autouse=True)
    def _tmp(self, tmp_path):
        self.tmp = tmp_path

    def test_renamed_list_type_still_grades(self):
        r = self._run("T3_009", lambda s: s.replace("List", "IntList"))
        assert r["run_correct"] is True, r

    def test_both_types_renamed_still_grade(self):
        r = self._run(
            "T3_010",
            lambda s: s.replace("List", "Xs").replace("Option", "Maybe"),
        )
        assert r["run_correct"] is True, r
