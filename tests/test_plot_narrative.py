"""Row-level chart data: refusals, best-attempt, and the ZTD lineup.

These cover the reasoning `plot_results.extract_data` cannot do, where the
failure modes are silent — a wrong answer still renders a perfectly
well-formed slide, so the only place the error surfaces is here.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import scripts.plot_narrative as pn  # noqa: E402
import scripts.plot_results as pr  # noqa: E402


def _row(pid, *, check=True, run=None, err=None, attempt=1):
    return {
        "problem_id": pid,
        "attempt": attempt,
        "check_pass": check,
        "run_correct": run,
        "error_message": err,
    }


REFUSED = "API error: Anthropic returned no text block (stop_reason=refusal)"


class TestSolved:
    """`solved` decides what the refusal slide claims a model *could* do.

    Getting it wrong does not crash anything — it prints "solved it in:
    nowhere" under a refusal, which reverses the slide's argument.
    """

    def setup_method(self):
        pr._GRADEABLE_IDS = {"G1", "G2"}  # U1 is deliberately absent

    def teardown_method(self):
        pr._GRADEABLE_IDS = None

    def test_gradeable_problem_needs_correct_output(self):
        assert pn.solved(_row("G1", check=True, run=True), "G1") is True
        assert pn.solved(_row("G1", check=True, run=False), "G1") is False

    def test_gradeable_problem_that_only_compiled_is_not_solved(self):
        # Compiling is not evidence of a correct answer when the answer
        # can actually be checked.
        assert pn.solved(_row("G1", check=True, run=None), "G1") is False

    def test_ungradeable_problem_falls_back_to_compilation(self):
        # The 24 no-test-case problems carry run_correct=None by
        # construction. Requiring run_correct here reported a problem
        # every language compiled as solved nowhere.
        assert pn.solved(_row("U1", check=True, run=None), "U1") is True
        assert pn.solved(_row("U1", check=False, run=None), "U1") is False

    def test_missing_row_is_not_solved(self):
        assert pn.solved(None, "G1") is False


class TestBestByProblem:
    def test_passing_fix_supersedes_failed_first_attempt(self):
        rows = [
            _row("G1", check=False, attempt=1),
            _row("G1", check=True, run=True, attempt=2),
        ]
        assert pn.best_by_problem(rows)["G1"]["attempt"] == 2

    def test_failed_fix_does_not_displace_a_passing_original(self):
        rows = [
            _row("G1", check=True, run=True, attempt=1),
            _row("G1", check=False, attempt=2),
        ]
        assert pn.best_by_problem(rows)["G1"]["attempt"] == 1


class TestFindRefusals:
    def setup_method(self):
        pr._GRADEABLE_IDS = {"G1"}

    def teardown_method(self):
        pr._GRADEABLE_IDS = None

    def test_reports_languages_the_same_model_solved_it_in(self):
        rows = {
            ("M", "Python"): [_row("G1", check=False, err=REFUSED)],
            ("M", "Vera"): [_row("G1", check=True, run=True)],
            ("M", "TypeScript"): [_row("G1", check=True, run=False)],
        }
        (found,) = pn.find_refusals(rows)
        assert found["mode"] == "Python"
        assert found["problem"] == "G1"
        # Vera solved it; TypeScript compiled but answered wrongly, which
        # is not evidence the model could do the problem.
        assert found["solved_in"] == ["Vera"]

    def test_does_not_credit_a_different_model(self):
        rows = {
            ("M", "Python"): [_row("G1", check=False, err=REFUSED)],
            ("OTHER", "Vera"): [_row("G1", check=True, run=True)],
        }
        (found,) = pn.find_refusals(rows)
        assert found["solved_in"] == []

    def test_a_plain_compile_error_is_not_a_refusal(self):
        rows = {("M", "Python"): [_row("G1", check=False, err="SyntaxError")]}
        assert pn.find_refusals(rows) == []


def test_ztd_lineup_is_derived_from_the_matrix():
    """A hand-kept copy of this list silently dropped Claude Opus 5 from
    the zero-training-data slide — the slide rendered fine, just without
    a model that had run every ZTD target."""
    from scripts.plot_slide import ZTD_MODELS
    from vera_bench.matrix import MODELS as MATRIX

    assert ZTD_MODELS == [m.display for m in MATRIX if m.ztd]
    assert "Claude Opus 5" in ZTD_MODELS


def test_every_language_has_a_hatch_and_a_marker():
    """Identity must never rest on hue alone: the palette sits at ΔE 4.4
    (Vera/Python, protan) and ΔE 2.1 (Vera/AILANG, deutan)."""
    for mode in pn.ALL_MODES:
        assert mode in pr.LANG_HATCH
        assert pr.LANG_MARKER.get(mode)
    # Distinct textures, so two series never share one.
    hatches = [pr.LANG_HATCH[m] for m in pn.ALL_MODES]
    assert len(hatches) == len(set(hatches))
    assert len({pr.LANG_MARKER[m] for m in pn.ALL_MODES}) == len(pn.ALL_MODES)
