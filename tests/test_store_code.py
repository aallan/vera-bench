"""Stored generated code (#109) — the artefact that makes a run re-gradeable.

A sweep's verdicts survive in the JSONL; before this the code that earned
them did not. That asymmetry cost a full re-sweep when the graded set
expanded, because answers we had already paid for could not be graded
against the new test cases. These tests pin the properties that make the
stored code trustworthy: it is written for every attempt, it is addressed
relative to the results tree, and a storage failure degrades the row
rather than the run.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vera_bench.models import LLMResponse
from vera_bench.runner import ProblemResult, run_benchmark, store_code

REPO_ROOT = Path(__file__).parent.parent


class TestStoreCode:
    def test_returns_path_relative_to_the_results_dir(self, tmp_path):
        code_dir = tmp_path / "results" / "code" / "target-bench-0-0-18"
        rel = store_code(code_dir, "VB-T1-001", 1, "vera", "fn f() {}")
        # Relative to results/, not to cwd — so a row stays valid when the
        # tree is moved or shipped as a release asset.
        assert rel == "code/target-bench-0-0-18/VB-T1-001_attempt1.vera"
        assert (tmp_path / "results" / rel).read_text() == "fn f() {}"

    @pytest.mark.parametrize(
        ("language", "ext"),
        [
            ("vera", "vera"),
            ("python", "py"),
            ("typescript", "ts"),
            ("aver", "av"),
            ("ailang", "ail"),
        ],
    )
    def test_extension_matches_the_language(self, tmp_path, language, ext):
        rel = store_code(tmp_path / "r" / "code" / "t", "P", 1, language, "x")
        assert rel.endswith(f"P_attempt1.{ext}")

    def test_attempt_number_separates_the_fix_from_the_original(self, tmp_path):
        d = tmp_path / "r" / "code" / "t"
        first = store_code(d, "P", 1, "vera", "original")
        second = store_code(d, "P", 2, "vera", "fixed")
        assert first != second
        assert (tmp_path / "r" / first).read_text() == "original"
        assert (tmp_path / "r" / second).read_text() == "fixed"

    def test_disabled_when_no_directory(self):
        assert store_code(None, "P", 1, "vera", "x") is None

    def test_write_failure_degrades_the_row_not_the_run(self, tmp_path, monkeypatch):
        # A run costs real money; instrumentation must not be able to lose
        # it. The failure is reported, not raised, and never silent — the
        # row simply carries no code_path.
        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", boom)
        assert store_code(tmp_path / "code" / "t", "P", 1, "vera", "x") is None


class TestRowCarriesCode:
    """The row and the file must agree, in both dispatch paths."""

    def _client(self):
        sol = (
            REPO_ROOT / "solutions" / "python" / "VB_T1_001_absolute_value.py"
        ).read_text()
        client = MagicMock()
        client.complete.return_value = LLMResponse(
            text=f"```python\n{sol}\n```",
            model="mock-model",
            input_tokens=1,
            output_tokens=1,
            wall_time_s=0.1,
        )
        return client, sol

    def _problem(self):
        path = REPO_ROOT / "problems" / "tier1" / "VB_T1_001_absolute_value.json"
        return json.loads(path.read_text())

    @pytest.mark.parametrize("parallel", [1, 2])
    def test_code_is_stored_in_sequential_and_parallel_paths(self, tmp_path, parallel):
        # run_benchmark has two dispatch paths and they are wired
        # separately; the parallel one was missed on the first pass, which
        # would have stored nothing for every real sweep (they all run
        # --parallel). Both are pinned here.
        client, sol = self._client()
        out = tmp_path / "mock-python-bench-0-0-18.jsonl"
        run_benchmark(
            problems=[self._problem()],
            client=client,
            skill_md="",
            vera=None,
            language="python",
            output_path=out,
            bench_version="0.0.18",
            parallel=parallel,
        )
        row = json.loads(out.read_text().splitlines()[0])
        assert row["code_path"], f"no code stored at parallel={parallel}"
        assert (out.parent / row["code_path"]).read_text().strip() == sol.strip()

    def test_opting_out_stores_nothing(self, tmp_path):
        client, _ = self._client()
        out = tmp_path / "mock-python-bench-0-0-18.jsonl"
        run_benchmark(
            problems=[self._problem()],
            client=client,
            skill_md="",
            vera=None,
            language="python",
            output_path=out,
            bench_version="0.0.18",
            store_generated_code=False,
        )
        row = json.loads(out.read_text().splitlines()[0])
        assert "code_path" not in row  # None values are dropped from JSONL
        assert not (out.parent / "code").exists()

    def test_absent_path_is_omitted_rather_than_null(self):
        # to_jsonl drops None, so a row from a --no-store-code run is not
        # distinguishable-by-null from one where the write failed. Both
        # simply lack the key; the console carries the failure.
        r = ProblemResult(
            problem_id="P", model="m", language="vera", attempt=1, check_pass=True
        )
        assert "code_path" not in json.loads(r.to_jsonl())
