"""regrade.py may only re-grade a target with the compiler that graded it.

A re-grade recomputes verdicts from stored code, on the assumption that
only the harness changed. Vera 0.1.9 broke that assumption for the 0.0.18
results: redeclaring a built-in effect became an error, where 0.1.8 needed
the declaration before a bare `throw` would resolve. Re-grading those
files with 0.1.9 installed fails programs that were correct when graded,
and `--apply` writes that over published numbers. These tests pin the
guard that refuses, and the opt-out that lets a deliberate experiment
through.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from collections import Counter

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import regrade as rg  # noqa: E402

INSTALLED = {"vera": "0.1.13", "aver": "0.27.1", "ailang": "0.30.0"}


class _FakeVera:
    def version(self) -> str:
        return "0.1.13"


class TestCompilerDrift:
    def test_the_grading_version_may_regrade(self):
        name = "m-bench-0-0-18-vera-0-1-13.jsonl"
        assert rg.compiler_drift(name, "vera", INSTALLED) is None

    def test_another_vera_version_is_refused_and_both_are_named(self):
        name = "m-bench-0-0-18-vera-0-1-8.jsonl"
        assert (
            rg.compiler_drift(name, "vera", INSTALLED)
            == "graded by vera 0.1.8, installed vera 0.1.13"
        )

    def test_spec_from_nl_is_held_like_full_spec(self):
        name = "m-spec-from-nl-bench-0-0-18-vera-0-1-8.jsonl"
        assert rg.compiler_drift(name, "vera", INSTALLED) is not None

    def test_a_version_is_not_mistaken_for_a_longer_one(self):
        # 0.1.8 must not pass for a file 0.1.18 graded, nor the reverse. The
        # comparison anchors on the dash that opens the segment.
        assert rg.compiler_drift(
            "m-bench-0-0-18-vera-0-1-18.jsonl", "vera", {"vera": "0.1.8"}
        )
        assert rg.compiler_drift(
            "m-bench-0-0-18-vera-0-1-8.jsonl", "vera", {"vera": "0.1.18"}
        )

    def test_aver_and_ailang_are_held_to_their_own_compilers(self):
        for name, lang in (
            ("m-aver-bench-0-0-18-aver-0-27-1.jsonl", "aver"),
            ("m-ailang-bench-0-0-18-ailang-0-30-0.jsonl", "ailang"),
        ):
            assert rg.compiler_drift(name, lang, INSTALLED) is None
        assert (
            rg.compiler_drift("m-aver-bench-0-0-16-aver-0-9-5.jsonl", "aver", INSTALLED)
            == "graded by aver 0.9.5, installed aver 0.27.1"
        )

    def test_python_and_typescript_are_never_held(self):
        # No compiler of ours grades them. Before results_path, a Python
        # name could pick up whatever Vera was installed; that stray
        # segment must not make one look drifted either.
        for lang in ("python", "typescript"):
            for name in (
                f"m-{lang}-bench-0-0-18.jsonl",
                f"m-{lang}-bench-0-0-9-vera-0-0-108.jsonl",
            ):
                assert rg.compiler_drift(name, lang, INSTALLED) is None, name

    def test_an_unknown_installed_compiler_never_matches(self):
        # A re-grade that cannot name its compiler cannot claim it is the
        # one that graded the file.
        assert (
            rg.compiler_drift(
                "m-bench-0-0-18-vera-0-1-8.jsonl", "vera", {"vera": "unknown"}
            )
            == "graded by vera 0.1.8, installed vera unknown"
        )

    def test_a_name_that_records_no_version_is_refused(self):
        assert (
            rg.compiler_drift("m-bench-0-0-18.jsonl", "vera", INSTALLED)
            == "graded by an unrecorded vera, installed vera 0.1.13"
        )


class TestInstalledVersions:
    def test_banners_are_read_the_way_the_cli_reads_them(self, monkeypatch):
        banners = {
            "aver": "aver 0.27.1\n",
            # ailang prints several lines; only the first carries the version.
            "ailang": "AILANG v0.30.0\ncommit 1a2b3c\nbuilt 2026-07-01\n",
        }

        def fake_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
            assert cmd[1:] == ["--version"]
            assert kwargs.get("timeout") == 5
            return subprocess.CompletedProcess(cmd, 0, banners[cmd[0]], "")

        monkeypatch.setattr(rg.subprocess, "run", fake_run)
        assert rg.installed_versions(_FakeVera()) == INSTALLED

    def test_a_missing_or_failing_compiler_is_unknown(self, monkeypatch):
        def fake_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
            if cmd[0] == "aver":
                raise FileNotFoundError(cmd[0])
            return subprocess.CompletedProcess(cmd, 1, "", "boom")

        monkeypatch.setattr(rg.subprocess, "run", fake_run)
        assert rg.installed_versions(_FakeVera()) == {
            "vera": "0.1.13",
            "aver": "unknown",
            "ailang": "unknown",
        }

    def test_a_wedged_compiler_is_unknown(self, monkeypatch):
        def fake_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

        monkeypatch.setattr(rg.subprocess, "run", fake_run)
        versions = rg.installed_versions(_FakeVera())
        assert versions["aver"] == versions["ailang"] == "unknown"


def _target(results: pathlib.Path, name: str, language: str) -> pathlib.Path:
    path = results / name
    row = {"problem_id": "VB-T1-001", "language": language}
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def run_main(monkeypatch, tmp_path, capsys):
    """main() over a scratch results dir, with the compilers and the grading
    itself stubbed out. Returns the names regrade_file was handed, and the
    printed output."""
    graded: list[str] = []

    def fake_regrade_file(path: pathlib.Path, *args, **kwargs):
        graded.append(path.name)
        return [], Counter(unchanged=1)

    monkeypatch.setattr(rg, "VeraRunner", _FakeVera)
    monkeypatch.setattr(rg, "installed_versions", lambda vera: dict(INSTALLED))
    monkeypatch.setattr(rg, "regrade_file", fake_regrade_file)

    def run(*argv: str) -> tuple[list[str], str]:
        common = ["--results-dir", str(tmp_path), "--bench-version", "0.0.18"]
        assert rg.main([*common, *argv]) == 0
        return graded, capsys.readouterr().out

    return run


class TestMain:
    def test_a_target_the_installed_compiler_graded_is_regraded(
        self, run_main, tmp_path
    ):
        _target(tmp_path, "m-bench-0-0-18-vera-0-1-13.jsonl", "vera")
        graded, out = run_main()
        assert graded == ["m-bench-0-0-18-vera-0-1-13.jsonl"]
        assert "compiler-drift 0" in out

    def test_a_drifted_target_is_skipped_in_a_dry_run_too(self, run_main, tmp_path):
        _target(tmp_path, "m-bench-0-0-18-vera-0-1-8.jsonl", "vera")
        graded, out = run_main()
        assert graded == []
        assert "skipped: graded by vera 0.1.8, installed vera 0.1.13" in out
        assert "compiler-drift 1" in out

    def test_apply_does_not_get_past_the_guard(self, run_main, tmp_path):
        # The case the guard exists for: --apply over published results.
        path = _target(tmp_path, "m-bench-0-0-18-vera-0-1-8.jsonl", "vera")
        before = path.read_text(encoding="utf-8")
        graded, _ = run_main("--apply")
        assert graded == []
        assert path.read_text(encoding="utf-8") == before

    def test_python_and_typescript_targets_are_always_regraded(
        self, run_main, tmp_path
    ):
        _target(tmp_path, "m-python-bench-0-0-18.jsonl", "python")
        _target(tmp_path, "m-typescript-bench-0-0-18.jsonl", "typescript")
        graded, out = run_main()
        assert sorted(graded) == [
            "m-python-bench-0-0-18.jsonl",
            "m-typescript-bench-0-0-18.jsonl",
        ]
        assert "compiler-drift 0" in out

    def test_the_opt_out_regrades_a_drifted_target_and_says_so(
        self, run_main, tmp_path
    ):
        _target(tmp_path, "m-bench-0-0-18-vera-0-1-8.jsonl", "vera")
        graded, out = run_main("--allow-compiler-drift")
        assert graded == ["m-bench-0-0-18-vera-0-1-8.jsonl"]
        assert "drift allowed: graded by vera 0.1.8" in out
        assert "compiler-drift 0" in out
