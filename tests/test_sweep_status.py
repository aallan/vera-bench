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


def test_expected_problems_matches_repo():
    # The repo's real problem set — the denominator run_sweep and this tool
    # both use for coverage. Must be a plausible, non-zero count.
    assert ss._expected_problems() >= 60


class TestExpectedTargets:
    """The sweep-file denominator must match the default sweep, not a hardcoded
    40: with pro opt-out (the default) run_sweep produces 36 targets, so a
    complete pro-off sweep should read as 36/36, not 36/40."""

    def test_pro_off_default_is_36(self, monkeypatch):
        monkeypatch.delenv("SWEEP_INCLUDE_PRO", raising=False)
        assert ss._expected_targets() == 36

    def test_pro_on_is_40(self, monkeypatch):
        monkeypatch.setenv("SWEEP_INCLUDE_PRO", "1")
        assert ss._expected_targets() == 40
