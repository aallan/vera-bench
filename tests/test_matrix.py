"""The canonical model matrix and its consumers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

from vera_bench.matrix import MODELS, PROVIDER_ENV_KEYS, detect_provider


class TestMatrix:
    def test_nine_models_three_providers(self):
        assert len(MODELS) == 9
        assert {m.provider for m in MODELS} == {"anthropic", "openai", "moonshot"}

    def test_display_names_unique(self):
        # Duplicate display names silently coalesce models in the charts.
        names = [m.display for m in MODELS]
        assert len(names) == len(set(names))

    def test_file_prefix_slashes_become_dashes(self):
        pro = next(m for m in MODELS if m.id == "openai-pro/gpt-5.6-sol")
        assert pro.file_prefix == "openai-pro-gpt-5.6-sol"
        k3 = next(m for m in MODELS if m.id == "moonshot/kimi-k3")
        assert k3.file_prefix == "moonshot-kimi-k3"

    def test_the_two_sol_prefixes_are_distinct(self):
        # One is a proper substring of the other; the glob that finds result
        # files must not confuse them.
        prefixes = {m.file_prefix for m in MODELS}
        assert "gpt-5.6-sol" in prefixes
        assert "openai-pro-gpt-5.6-sol" in prefixes

    def test_ztd_subset(self):
        ztd = {m.id for m in MODELS if m.ztd}
        assert ztd == {
            "claude-fable-5",
            "claude-opus-4-8",
            "claude-opus-5",
            "gpt-5.6-sol",
            "moonshot/kimi-k3",
        }

    def test_every_provider_has_an_env_key(self):
        for m in MODELS:
            assert m.provider in PROVIDER_ENV_KEYS

    def test_detect_provider_routes_every_matrix_id(self):
        for m in MODELS:
            assert detect_provider(m.id) == m.provider

    def test_detect_provider_handles_ids_outside_the_matrix(self):
        assert detect_provider("gpt-4o") == "openai"
        assert detect_provider("anthropic/claude-3") == "anthropic"
        assert detect_provider("or/meta-llama/llama-3") == "openrouter"
        assert detect_provider("llama-3-70b") == "unknown"


class TestPlotResultsDerivesFromMatrix:
    """plot_results.MODELS is a projection of the canonical matrix, not a
    hand-kept copy — the drift this consolidation removed."""

    def test_derived_lineup_matches_matrix(self):
        # Put the repo root on the path so `scripts` imports under any
        # pytest invocation (CI's `pytest` console script doesn't add cwd
        # the way `python -m pytest` does). Mirrors plot_slide.py.
        import pathlib
        import sys

        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from scripts.plot_results import MODELS as PR_MODELS

        assert len(PR_MODELS) == len(MODELS)
        for spec, m in zip(PR_MODELS, MODELS):
            assert spec.display == m.display
            assert spec.file_prefix == m.file_prefix
            assert spec.tier == m.tier


class TestPassAtOne:
    """The honest headline metric: solved / gradeable, where a refusal,
    a compile failure, a runtime error and a wrong answer all count as
    not-solved. It must NOT shrink the denominator the way
    run_correct-over-eligible did (which let refusals inflate the bar)."""

    def _pass1(self, rows, gradeable):
        import pathlib
        import sys

        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        import scripts.plot_results as pr

        pr._GRADEABLE_IDS = set(gradeable)  # fixed, not read from disk
        return pr._pass_at_1_pct(rows)

    def _row(self, pid, *, check, run, err=None, attempt=1):
        return {
            "problem_id": pid,
            "attempt": attempt,
            "check_pass": check,
            "run_correct": run,
            "error_message": err,
        }

    def test_refusal_counts_as_not_solved(self):
        gradeable = {f"P{i}" for i in range(10)}
        rows = [self._row(f"P{i}", check=True, run=True) for i in range(9)]
        rows.append(
            self._row("P9", check=False, run=None, err="... stop_reason=refusal ...")
        )
        # 9 of 10 solved — the refusal is a miss, not dropped from the base.
        assert self._pass1(rows, gradeable) == 90

    def test_compile_failure_and_wrong_answer_are_misses(self):
        gradeable = {f"P{i}" for i in range(10)}
        rows = [self._row(f"P{i}", check=True, run=True) for i in range(8)]
        rows.append(self._row("P8", check=False, run=None, err="check: syntax"))
        rows.append(self._row("P9", check=True, run=False))  # compiled, wrong
        assert self._pass1(rows, gradeable) == 80

    def test_denominator_is_gradeable_not_eligible(self):
        # The old bug: a model that refuses 5 and aces 5 scored 100%.
        gradeable = {f"P{i}" for i in range(10)}
        rows = [self._row(f"P{i}", check=True, run=True) for i in range(5)]
        rows += [
            self._row(f"P{i}", check=False, run=None, err="refusal")
            for i in range(5, 10)
        ]
        assert self._pass1(rows, gradeable) == 50  # not 100

    def test_non_gradeable_problems_excluded(self):
        # Problems without test cases can't be output-graded — not in denom.
        gradeable = {"P0", "P1"}
        rows = [
            self._row("P0", check=True, run=True),
            self._row("P1", check=True, run=True),
            self._row("P2", check=True, run=None),  # no test cases
        ]
        assert self._pass1(rows, gradeable) == 100

    def test_fix_attempt_counts(self):
        # attempt-2 that compiles and runs correctly supersedes a failed a1.
        gradeable = {"P0"}
        rows = [
            self._row("P0", check=False, run=None, err="check", attempt=1),
            self._row("P0", check=True, run=True, attempt=2),
        ]
        assert self._pass1(rows, gradeable) == 100

    def test_none_when_no_gradeable_present(self):
        assert self._pass1([self._row("X", check=True, run=None)], {"P0"}) is None


class TestGradeableVersioning:
    """The gradeable set is version-pinned, like the model lineup.

    problems/ on disk only knows today's problem set, but old result
    files carry rows for problems that were not gradeable when swept.
    Without the pin, regenerating a v0.0.16 chart after test cases
    landed for 10 more problems would divide 36 problems' worth of
    solves by 46 and silently deflate every published number.
    """

    def _pr(self) -> "ModuleType":
        import pathlib
        import sys

        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        import scripts.plot_results as pr

        return pr

    def test_old_version_excludes_later_graded_problems(self, monkeypatch):
        pr = self._pr()
        monkeypatch.setattr(pr, "_GRADEABLE_IDS", {"P0", "P1"})
        monkeypatch.setattr(pr, "GRADEABLE_ADDED", {"P1": "0.0.17"})
        assert pr._gradeable_ids("0.0.16") == {"P0"}
        assert pr._gradeable_ids("0.0.17") == {"P0", "P1"}
        assert pr._gradeable_ids(None) == {"P0", "P1"}

    def test_unparseable_version_is_treated_as_current(self, monkeypatch):
        pr = self._pr()
        monkeypatch.setattr(pr, "_GRADEABLE_IDS", {"P0", "P1"})
        monkeypatch.setattr(pr, "GRADEABLE_ADDED", {"P1": "0.0.17"})
        assert pr._gradeable_ids("not-a-version") == {"P0", "P1"}

    def test_pass_at_1_uses_the_versioned_denominator(self, monkeypatch):
        # Ten problems, all solved; two of them only became gradeable in
        # 0.0.17. A 0.0.16 file scoring 8/8 must not become 8/10.
        pr = self._pr()
        monkeypatch.setattr(pr, "_GRADEABLE_IDS", {f"P{i}" for i in range(10)})
        monkeypatch.setattr(pr, "GRADEABLE_ADDED", {"P8": "0.0.17", "P9": "0.0.17"})
        rows = [
            {
                "problem_id": f"P{i}",
                "attempt": 1,
                "check_pass": True,
                # The two later-graded problems look exactly as they do in
                # a real old file: present, ungraded, no error.
                "run_correct": True if i < 8 else None,
                "error_message": None,
            }
            for i in range(10)
        ]
        assert pr._pass_at_1_pct(rows, "0.0.16") == 100
        assert pr._pass_at_1_pct(rows, "0.0.17") == 80

    def test_every_pinned_id_is_gradeable_today(self, monkeypatch):
        # A GRADEABLE_ADDED entry for a problem with no test cases would
        # mean the pin and the problem set disagree about reality.
        pr = self._pr()
        # drop any patched value and read from disk — via monkeypatch so
        # the disk cache cannot leak into later tests
        monkeypatch.setattr(pr, "_GRADEABLE_IDS", None)
        current = pr._gradeable_ids(None)
        missing = set(pr.GRADEABLE_ADDED) - current
        assert not missing, f"pinned but not gradeable on disk: {sorted(missing)}"
        for version in pr.GRADEABLE_ADDED.values():
            assert pr._version_tuple(version) is not None

    def test_version_boundaries_match_published_history(self, monkeypatch):
        # The mechanism is tested with synthetic pins above; this pins
        # the REAL data. A typo'd version on one of the 24 entries, or a
        # problem gaining cases without a pin, corrupts regenerated
        # published charts silently — the exact CLAUDE.md invariant.
        pr = self._pr()
        monkeypatch.setattr(pr, "_GRADEABLE_IDS", None)
        assert len(pr._gradeable_ids("0.0.16")) == 36
        assert len(pr._gradeable_ids("0.0.17")) == 46
        assert len(pr._gradeable_ids(None)) == 60
        added = pr._gradeable_ids(None) - pr._gradeable_ids("0.0.16")
        assert added == set(pr.GRADEABLE_ADDED)

    def test_declines_leave_the_denominator(self, monkeypatch):
        # "test wrapper unavailable" is the harness abstaining, not the
        # model failing; only harness-labelled rows are excluded, so a
        # model cannot shrink its own denominator.
        pr = self._pr()
        monkeypatch.setattr(pr, "_GRADEABLE_IDS", {"P0", "P1", "P2"})
        monkeypatch.setattr(pr, "GRADEABLE_ADDED", {})
        rows = [
            {"problem_id": "P0", "attempt": 1, "check_pass": True, "run_correct": True},
            {
                "problem_id": "P1",
                "attempt": 1,
                "check_pass": True,
                "error_message": "test wrapper unavailable: no data declaration",
            },
            {
                "problem_id": "P2",
                "attempt": 1,
                "check_pass": True,
                "run_correct": False,
            },
        ]
        # P1 declined: 1 solved of 2 eligible, not 1 of 3.
        assert pr._pass_at_1_pct(rows) == 50
        # A model-written message must not trigger the exclusion.
        rows[1] = {
            "problem_id": "P1",
            "attempt": 1,
            "check_pass": True,
            "run_correct": False,
            "error_message": "test wrapper unavailable (I refuse)",
        }
        assert pr._pass_at_1_pct(rows) == 33

    def test_a_forged_decline_message_does_not_shrink_the_denominator(
        self, monkeypatch
    ):
        # A compile-failure row carries the compiler's diagnostic, which
        # quotes the model's own source. Substring-matching alone let a
        # model remove its problem from the denominator by writing the
        # phrase; the marker must be anchored and paired with check_pass.
        pr = self._pr()
        monkeypatch.setattr(pr, "_GRADEABLE_IDS", {"P0", "P1"})
        monkeypatch.setattr(pr, "GRADEABLE_ADDED", {})
        rows = [
            {"problem_id": "P0", "attempt": 1, "check_pass": True, "run_correct": True},
            {
                "problem_id": "P1",
                "attempt": 1,
                "check_pass": False,
                "error_message": "[E001] parse error near "
                "'test wrapper unavailable: hi'",
            },
        ]
        assert pr._pass_at_1_pct(rows) == 50  # counted, not excluded

    def test_a_genuine_decline_still_leaves_the_denominator(self, monkeypatch):
        pr = self._pr()
        monkeypatch.setattr(pr, "_GRADEABLE_IDS", {"P0", "P1"})
        monkeypatch.setattr(pr, "GRADEABLE_ADDED", {})
        rows = [
            {"problem_id": "P0", "attempt": 1, "check_pass": True, "run_correct": True},
            {
                "problem_id": "P1",
                "attempt": 1,
                "check_pass": True,
                "error_message": "test wrapper unavailable: no data declaration",
            },
        ]
        assert pr._pass_at_1_pct(rows) == 100
