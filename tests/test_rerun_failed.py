"""rerun_one must never hand splice() bad data.

The whole point of the surgical repair is to replace one problem's rows in a
canonical file without disturbing the other 59. If a re-run stalls, produces
nothing, produces an empty file, or (worst) produces rows for a *different*
problem, letting that reach splice() would corrupt good results. These tests
pin the guards that abort first.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import rerun_failed as rf  # noqa: E402


def _write(scratch: pathlib.Path, rows: list[dict]) -> None:
    (scratch / "out.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def _call(monkeypatch, scratch, *, produce, run=None):
    """Run rerun_one with subprocess.run stubbed to `produce` the given rows."""

    def fake_run(cmd, **kwargs):
        if run is not None:
            run(cmd, **kwargs)  # let a test raise TimeoutExpired / CalledProcessError
        if produce is not None:
            _write(scratch, produce)

    monkeypatch.setattr(rf.subprocess, "run", fake_run)
    return rf.rerun_one("m", "vera", "full-spec", "VB-T1-001", [], str(scratch), 900)


def test_good_rows_are_returned(monkeypatch, tmp_path):
    rows = [{"problem_id": "VB-T1-001", "attempt": 1, "run_correct": True}]
    assert _call(monkeypatch, tmp_path, produce=rows) == rows


def test_empty_file_aborts_before_splice(monkeypatch, tmp_path):
    with pytest.raises(SystemExit, match="empty file"):
        _call(monkeypatch, tmp_path, produce=[])


def test_rows_for_another_problem_abort(monkeypatch, tmp_path):
    # The dangerous case: a fresh run that somehow emitted a different id would
    # otherwise overwrite that id's good group.
    rows = [{"problem_id": "VB-T9-999", "attempt": 1, "run_correct": True}]
    with pytest.raises(SystemExit, match="rows for"):
        _call(monkeypatch, tmp_path, produce=rows)


def test_no_output_file_aborts(monkeypatch, tmp_path):
    with pytest.raises(SystemExit, match="no output file"):
        _call(monkeypatch, tmp_path, produce=None)


def test_timeout_aborts(monkeypatch, tmp_path):
    def boom(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 900)

    with pytest.raises(SystemExit, match="exceeded 900s"):
        _call(monkeypatch, tmp_path, produce=None, run=boom)


def test_nonzero_exit_aborts(monkeypatch, tmp_path):
    def boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(2, cmd)

    with pytest.raises(SystemExit, match="exited 2"):
        _call(monkeypatch, tmp_path, produce=None, run=boom)
