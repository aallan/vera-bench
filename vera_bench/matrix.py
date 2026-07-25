"""The canonical benchmark model matrix — one source of truth.

Which models the benchmark sweeps, their provider, tier, display name, and
whether they also run the zero-training-data targets (Aver + AILANG). This
was previously duplicated across three files that could drift apart:
`scripts/run_full_benchmark.py` (provider-grouped, for the gate),
`scripts/plot_results.py` (tier-tagged, for the charts), and the sweep
runner. They now all read this.

Consumers:
- `scripts/plot_results.py` derives its `ModelSpec` list from `MODELS`.
- `scripts/preflight.sh` reads `MODELS` (ids + providers) to gate the sweep.
- `scripts/run_sweep.sh` reads `MODELS` (ids + providers + ztd) to run it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Model:
    id: str  # the --model CLI string, e.g. "openai-pro/gpt-5.6-sol"
    provider: str  # anthropic | openai | moonshot
    tier: str  # fable | opus | sonnet — controls chart layout
    display: str  # "Claude Fable 5"
    ztd: bool = False  # also runs Aver + AILANG generation targets

    @property
    def file_prefix(self) -> str:
        """The model-id portion of a result filename ('/' -> '-')."""
        return self.id.replace("/", "-")


# Ordered by tier (fable, opus, sonnet) so the derived chart lineup keeps
# its left-to-right panel order. The fable row is intentionally 2-wide:
# Moonshot ships no ceiling-above-flagship model. openai-pro/gpt-5.6-sol is
# Sol at reasoning.mode=pro — same underlying model as the opus-tier entry,
# the controlled reasoning-budget comparison.
#
# WITHIN a tier, most capable first. The charts read left-to-right as
# descending capability (that is what the tier order itself encodes), so a
# newer, stronger model sitting to the right of the one it supersedes
# reads as the reverse of the truth — hence Opus 5 before Opus 4.8. This
# is presentation order only; the `generation` slide keeps its own
# explicit CHRONOLOGICAL chain, because a trajectory over time must run
# oldest-to-newest regardless of how the tiers are laid out.
MODELS: list[Model] = [
    Model("claude-fable-5", "anthropic", "fable", "Claude Fable 5", ztd=True),
    Model("openai-pro/gpt-5.6-sol", "openai", "fable", "GPT-5.6 Sol (pro)"),
    Model("claude-opus-5", "anthropic", "opus", "Claude Opus 5", ztd=True),
    Model("claude-opus-4-8", "anthropic", "opus", "Claude Opus 4.8", ztd=True),
    Model("gpt-5.6-sol", "openai", "opus", "GPT-5.6 Sol", ztd=True),
    Model("moonshot/kimi-k3", "moonshot", "opus", "Kimi K3", ztd=True),
    Model("claude-sonnet-5", "anthropic", "sonnet", "Claude Sonnet 5"),
    Model("gpt-5.6-terra", "openai", "sonnet", "GPT-5.6 Terra"),
    Model("moonshot/kimi-k2.6", "moonshot", "sonnet", "Kimi K2.6"),
]

PROVIDER_ENV_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
}


def detect_provider(model: str) -> str:
    """Provider for any model id, including ones not in MODELS.

    Prefix-based so an arbitrary `--model` still routes: the gate and the
    sweep both accept ad-hoc ids, not only the matrix.
    """
    if model.startswith(("claude-", "anthropic/")):
        return "anthropic"
    if model.startswith(("gpt-", "o1-", "o3-", "openai/", "openai-pro/")):
        return "openai"
    if model.startswith("moonshot/"):
        return "moonshot"
    if model.startswith("or/"):
        return "openrouter"
    return "unknown"
