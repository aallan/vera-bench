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


def _call(monkeypatch, scratch: pathlib.Path, *, produce, run=None) -> list[dict]:
    """Run rerun_one with subprocess.run stubbed to `produce` the given rows."""

    def fake_run(cmd: list[str], **kwargs) -> None:
        # Pin that rerun_one actually forwards the timeout to the subprocess —
        # without this the timeout tests pass even if timeout= is dropped.
        assert kwargs.get("timeout") == 900
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


class TestEraScoping:
    """`results/` accumulates every release side by side.

    The target file is found by globbing the name `cli.py` builds. That name
    carries the bench version, so a prefix stopping at `-bench-` matches one
    file per era — unambiguous while only one release existed, and broken the
    moment a second landed. It failed exactly when it was needed: after a
    sweep, repairing a target, with the previous release still on disk.
    """

    def _populate(self, d: pathlib.Path, *names: str) -> None:
        for n in names:
            (d / n).write_text("", encoding="utf-8")

    def test_prefix_pins_the_bench_version(self):
        assert (
            rf.canonical_basename_prefix(
                "claude-opus-4-8", "vera", "full-spec", "0.0.18"
            )
            == "claude-opus-4-8-bench-0-0-18"
        )

    def test_two_eras_on_disk_resolve_to_the_requested_one(self, tmp_path):
        self._populate(
            tmp_path,
            "claude-opus-4-8-bench-0-0-16-vera-0-1-7.jsonl",
            "claude-opus-4-8-bench-0-0-18-vera-0-1-8.jsonl",
        )
        found = rf.find_canonical(
            str(tmp_path), "claude-opus-4-8", "vera", "full-spec", "0.0.18"
        )
        assert found.endswith("claude-opus-4-8-bench-0-0-18-vera-0-1-8.jsonl")

    def test_an_older_era_is_still_reachable(self, tmp_path):
        # The escape hatch: repairing a superseded release must stay possible.
        self._populate(
            tmp_path,
            "claude-opus-4-8-bench-0-0-16-vera-0-1-7.jsonl",
            "claude-opus-4-8-bench-0-0-18-vera-0-1-8.jsonl",
        )
        found = rf.find_canonical(
            str(tmp_path), "claude-opus-4-8", "vera", "full-spec", "0.0.16"
        )
        assert found.endswith("claude-opus-4-8-bench-0-0-16-vera-0-1-7.jsonl")

    def test_the_compiler_segment_stays_a_wildcard(self, tmp_path):
        # A target's Vera version is whatever produced it, not whatever is
        # installed now — so only the bench segment may be pinned.
        self._populate(tmp_path, "m-bench-0-0-18-vera-9-9-9.jsonl")
        found = rf.find_canonical(str(tmp_path), "m", "vera", "full-spec", "0.0.18")
        assert found.endswith("m-bench-0-0-18-vera-9-9-9.jsonl")

    def test_a_missing_era_says_so(self, tmp_path):
        self._populate(tmp_path, "m-bench-0-0-16-vera-0-1-7.jsonl")
        with pytest.raises(SystemExit, match="0.0.18"):
            rf.find_canonical(str(tmp_path), "m", "vera", "full-spec", "0.0.18")


class TestVersionTokenBoundary:
    """`0.0.18` must not select `0.0.180`.

    The bench segment is followed either by a compiler segment or by the
    extension, so a trailing `*` was enough to let one release's repair
    reach into another's file — and a splice writes rows, so the damage
    would have been to real results rather than a failed lookup.
    """

    def _write(self, d: pathlib.Path, *names: str) -> None:
        for n in names:
            (d / n).write_text("", encoding="utf-8")

    def test_a_longer_version_is_not_a_prefix_match(self, tmp_path):
        self._write(tmp_path, "m-bench-0-0-180-vera-0-1-8.jsonl")
        with pytest.raises(SystemExit, match="no results file"):
            rf.find_canonical(str(tmp_path), "m", "vera", "full-spec", "0.0.18")

    def test_the_intended_release_is_still_found_beside_it(self, tmp_path):
        self._write(
            tmp_path,
            "m-bench-0-0-18-vera-0-1-8.jsonl",
            "m-bench-0-0-180-vera-0-1-8.jsonl",
        )
        found = rf.find_canonical(str(tmp_path), "m", "vera", "full-spec", "0.0.18")
        assert found.endswith("m-bench-0-0-18-vera-0-1-8.jsonl")

    def test_a_name_ending_at_the_bench_segment_still_matches(self, tmp_path):
        # Python and TypeScript targets carry no compiler segment.
        self._write(tmp_path, "m-python-bench-0-0-18.jsonl")
        found = rf.find_canonical(str(tmp_path), "m", "python", "full-spec", "0.0.18")
        assert found.endswith("m-python-bench-0-0-18.jsonl")
