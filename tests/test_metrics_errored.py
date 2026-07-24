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

    def test_runtime_exception_is_a_model_failure_not_an_error(self):
        """The canary case (2026-07-24). The Vera evaluator records the
        runtime diagnostic for a contract violation / div-by-zero / stack
        overflow, so these rows carry an error_message — but the code
        compiled (check=True), ran, and was graded run_correct=False. That
        is a model failure counted in run_correct, not a grading gap.
        Counting it as `errored` conflated a legitimate failure with a
        harness problem and put an alarming non-zero on a healthy run."""
        rows = [
            _row(
                "VB-T5-009",
                check=True,
                run=False,
                err="test 0: Precondition violation in state_max$where$loop ...",
            ),
            _row(
                "VB-T3-011",
                check=True,
                run=False,
                err="test 2: Integer division by zero in safe_divide ...",
            ),
        ]
        # ...alongside genuine grading gaps, which MUST still count.
        rows += [
            _row("VB-T1-001", check=False, run=None, err="API error: 401"),
        ]
        m = compute_metrics(rows)
        assert m.errored == 1  # only the API failure, not the two runtime fails
        assert m.run_eligible == 2  # the two that compiled and ran
        assert m.run_correct_rate == 0.0  # both ran and failed


class TestVeraRunDiagnostics:
    """`vera run` failures must be attributable (#72 reached Aver and
    AILANG but never the Vera path, which is the headline number).

    A compiler crash previously arrived as `error_message=None,
    check_pass=True, run_correct=False` — byte-identical to a model
    writing a wrong program. vera SIGBUS'd repeatedly on 2026-07-23
    (aallan/vera#1145), so this is observed, not hypothetical.
    """

    def test_signal_death_is_named(self):
        from vera_bench.runner import _vera_run_error
        from vera_bench.vera_runner import RunResult

        # subprocess reports a signal death as a negative returncode;
        # SIGBUS is 10. Without naming it this reads as an ordinary
        # non-zero exit — which is to say, as the model's fault.
        msg = _vera_run_error(0, RunResult(exit_code=-10, stdout="", stderr=""))
        assert "killed by signal 10" in msg

    def test_signal_death_includes_stderr_when_present(self):
        from vera_bench.runner import _vera_run_error
        from vera_bench.vera_runner import RunResult

        msg = _vera_run_error(
            3, RunResult(exit_code=-11, stdout="", stderr="memory fault at 0x0")
        )
        assert "signal 11" in msg and "memory fault" in msg

    def test_ordinary_failure_surfaces_stderr(self):
        from vera_bench.runner import _vera_run_error
        from vera_bench.vera_runner import RunResult

        msg = _vera_run_error(
            1, RunResult(exit_code=1, stdout="", stderr="type error: expected Int")
        )
        assert "type error: expected Int" in msg

    def test_silent_nonzero_exit_still_reports_something(self):
        from vera_bench.runner import _vera_run_error
        from vera_bench.vera_runner import RunResult

        msg = _vera_run_error(2, RunResult(exit_code=1, stdout="", stderr=""))
        assert "exit 1" in msg
