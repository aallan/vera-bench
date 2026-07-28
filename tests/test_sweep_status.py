"""sweep_status classification and completeness.

The load-bearing property: a target is only "complete" when it covers every
problem AND carries no transient fault. Counting rows instead of unique
problems would let a partial run (60 rows spread over fewer problems via fix
attempts) masquerade as done — the exact false-clean this tool exists to catch.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import sweep_status as ss  # noqa: E402

NO_ERR = {"refusal": 0, "length": 0, "transient": 0, "other": 0}


def _b(**kw: int) -> dict[str, int]:
    return {**NO_ERR, **kw}


class TestVerdictCoverage:
    def test_full_coverage_no_error_is_complete(self):
        assert ss.verdict(60, 60, _b()) == ("complete", "complete")

    def test_partial_coverage_is_in_flight_even_with_enough_rows(self):
        # 30 unique problems of 60 — the row count is irrelevant; this must
        # NOT read as complete.
        cat, detail = ss.verdict(30, 60, _b())
        assert cat == "in-flight"
        assert "30/60" in detail

    def test_transient_forces_rerun(self):
        assert ss.verdict(60, 60, _b(transient=2))[0] == "re-run"

    def test_length_forces_raise_tokens(self):
        assert ss.verdict(60, 60, _b(length=3))[0] == "raise-tokens"

    def test_both_transient_and_length_are_shown(self):
        _, detail = ss.verdict(60, 60, _b(transient=1, length=4))
        assert "transient" in detail and "length" in detail

    def test_refusal_only_is_complete_kept(self):
        cat, detail = ss.verdict(60, 60, _b(refusal=2))
        assert cat == "complete" and "refusal" in detail

    def test_other_only_is_complete(self):
        # "other" = compile/runtime diagnostics (real results). It does not
        # force a re-run; the oth column carries the visibility instead.
        assert ss.verdict(60, 60, _b(other=3)) == ("complete", "complete")


class TestClassify:
    def test_refusal(self):
        assert (
            ss.classify("Anthropic returned no text block (stop_reason=refusal)")
            == "refusal"
        )

    def test_length_beats_empty_content(self):
        # A length truncation also says "empty content"; length must win so it
        # is treated as a budget wall, not a transient blip.
        assert (
            ss.classify("Moonshot returned empty content (finish_reason=length)")
            == "length"
        )

    def test_transient_api_error(self):
        # Every harness-wrapped infra failure is prefixed "API error", so it
        # can never fall through to "other".
        assert ss.classify("API error: Moonshot API timed out") == "transient"

    def test_compile_error_is_other(self):
        assert ss.classify("check failed: unexpected token") == "other"

    def test_anthropic_token_wall_is_length_not_refusal(self):
        # Anthropic spells a truncation `stop_reason=max_tokens`, and its
        # message ALSO says "no text block" — which the refusal pattern
        # matches. Knowing only OpenAI's `finish_reason=length` therefore
        # relabelled a recoverable truncation as the model declining, so
        # the sweep kept it as a real verdict instead of offering a bigger
        # budget, and it was published in the refusal count.
        msg = (
            "Fix API error: Anthropic returned no text block for "
            "model='claude-opus-5' (stop_reason=max_tokens, blocks=['thinking'])"
        )
        assert ss.classify(msg) == "length"
        assert not ss.is_refusal(msg)

    def test_a_genuine_refusal_survives_the_exclusion(self):
        msg = "Anthropic returned no text block (stop_reason=refusal)"
        assert ss.is_refusal(msg)
        assert ss.classify(msg) == "refusal"

    def test_both_provider_spellings_of_a_token_wall(self):
        for msg in (
            "Moonshot returned empty content (finish_reason=length)",
            "Anthropic returned no text block (stop_reason=max_tokens)",
        ):
            assert ss.classify(msg) == "length", msg

    def test_execution_timeout_is_a_real_result_not_a_transient(self):
        # The harness's own 30s budget on the model's COMPILED code. The
        # program did not terminate, which is a wrong answer — deterministic,
        # so re-running it only reproduces it. Bucketing this transient made
        # the sweep retry it to its limit and left the target permanently
        # "RE-RUN", so a finished sweep could not be told from a broken one.
        assert ss.classify("test 0: vera run timed out after 30s") == "other"

    def test_execution_prefix_beats_every_transient_word(self):
        # `test N:` marks the local per-test path — no network is involved,
        # so no message carrying it can be an infrastructure fault, whatever
        # words appear later.
        for msg in (
            "test 3: vera run timed out after 30s",
            "test 12: connection reset while running",
            "test 0: killed by signal 9",
        ):
            assert ss.classify(msg) == "other", msg

    def test_api_timeout_is_still_transient(self):
        # The regression guard for the fix above: infrastructure timeouts
        # carry no `test N:` prefix and must keep re-running.
        assert ss.classify("API error: request timed out") == "transient"
        assert ss.classify("Connection error contacting provider") == "transient"


def test_expected_problems_matches_repo():
    # The repo's real problem set — the denominator run_sweep and this tool
    # both use for coverage. Must be a plausible, non-zero count.
    assert ss._expected_problems() >= 60


class TestExpectedTargets:
    """The sweep-file denominator is derived from the matrix, not hardcoded: it
    tracks 4 core targets per model plus 2 (aver, ailang) per ztd model, with
    the pro tier honoured via SWEEP_INCLUDE_PRO. As the matrix grows this count
    moves with it — the point is that it is derived, so a complete sweep reads
    as N/N rather than N/<stale-constant>."""

    def test_pro_off_default(self, monkeypatch):
        # 8 models pro-off (5 of them ztd): 8*4 core + 5*2 ztd = 42.
        monkeypatch.delenv("SWEEP_INCLUDE_PRO", raising=False)
        assert ss._expected_targets() == 42

    def test_pro_on_adds_the_pro_tier(self, monkeypatch):
        # 9 models pro-on: 9*4 + 5*2 = 46.
        monkeypatch.setenv("SWEEP_INCLUDE_PRO", "1")
        assert ss._expected_targets() == 46
