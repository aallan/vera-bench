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
        from scripts.plot_results import MODELS as PR_MODELS

        assert len(PR_MODELS) == len(MODELS)
        for spec, m in zip(PR_MODELS, MODELS):
            assert spec.display == m.display
            assert spec.file_prefix == m.file_prefix
            assert spec.tier == m.tier
