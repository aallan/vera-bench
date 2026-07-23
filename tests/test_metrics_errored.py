"""Error accounting: the shrinking run_correct denominator (#95)."""

from __future__ import annotations

from vera_bench.metrics import compute_metrics


def _row(pid: str, *, check: bool, run, err: str | None):
    return {
        "problem_id": pid,
        "tier": 1,
        "attempt": 1,
        "check_pass": check,
        "run_correct": run,
        "error_message": err,
    }


class TestErroredAccounting:
    """`run_correct_rate` is measured over problems that compiled, so
    API-error rows leave the denominator entirely. The rate itself is
    unchanged (historical comparability), but the shrinkage must be
    visible in the metrics object."""

    def test_partial_api_failure_is_counted(self):
        rows = [
            _row(f"VB-T1-{i:03d}", check=False, run=None, err="API error: 401")
            for i in range(40)
        ]
        rows += [
            _row(f"VB-T1-{i:03d}", check=True, run=True, err=None)
            for i in range(40, 60)
        ]
        m = compute_metrics(rows)

        # The headline number is still 100% — that is the hazard.
        assert m.run_correct_rate == 1.0
        assert m.total_problems == 60
        # ...but the denominator and the failures are now reportable.
        assert m.run_eligible == 20
        assert m.errored == 40

    def test_total_api_failure(self):
        rows = [
            _row(f"VB-T1-{i:03d}", check=False, run=None, err="API error: 401")
            for i in range(60)
        ]
        m = compute_metrics(rows)
        assert m.run_correct_rate is None  # no measurement exists
        assert m.run_eligible == 0
        assert m.errored == 60

    def test_clean_run_reports_no_errors(self):
        rows = [
            _row(f"VB-T1-{i:03d}", check=True, run=True, err=None) for i in range(60)
        ]
        m = compute_metrics(rows)
        assert m.errored == 0
        assert m.run_eligible == m.total_problems == 60

    def test_compiled_but_wrong_is_not_an_error(self):
        """A model that compiles and gets the answer wrong is a real
        result, not a harness failure — it must stay in the denominator."""
        rows = [
            _row(f"VB-T1-{i:03d}", check=True, run=False, err=None) for i in range(60)
        ]
        m = compute_metrics(rows)
        assert m.errored == 0
        assert m.run_eligible == 60
        assert m.run_correct_rate == 0.0
