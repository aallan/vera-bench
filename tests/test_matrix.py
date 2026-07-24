"""The canonical model matrix and its consumers."""

from __future__ import annotations

from vera_bench.matrix import MODELS, PROVIDER_ENV_KEYS, detect_provider


class TestMatrix:
    def test_eight_models_three_providers(self):
        assert len(MODELS) == 8
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
