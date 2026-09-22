"""The result filename is a contract between two programs.

`vera-bench run` writes it; `scripts/run_sweep.sh` predicts it to decide
whether a target is already finished. When the two disagreed the failure
was silent and expensive: run_sweep.sh had the bench version spelled into
its own copy of the pattern, so on 0.0.18 it waited for a file the CLI
would never write, judged every successful target dirty, and retried the
whole matrix — pro tier included — before reporting total failure over
good data. `sweep_status.py` had the same literal as its default glob and
reported a *previous* release's finished sweep as though it were the
current one, which reads as success.

These tests pin the contract from both ends: that the CLI and the shared
constructor agree, and that no script re-derives a version it should be
asking for.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from vera_bench import __version__
from vera_bench.results_path import (
    compiler_segment,
    recorded_compiler_version,
    result_filename,
    version_slug,
)

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS = REPO_ROOT / "scripts"


class TestResultFilename:
    def test_vera_full_spec_carries_the_compiler_version(self):
        assert (
            result_filename("claude-fable-5", "0.0.18", vera_version="0.1.8")
            == "claude-fable-5-bench-0-0-18-vera-0-1-8.jsonl"
        )

    def test_spec_from_nl_is_marked(self):
        assert (
            result_filename(
                "gpt-5.6-sol", "0.0.18", mode="spec-from-nl", vera_version="0.1.8"
            )
            == "gpt-5.6-sol-spec-from-nl-bench-0-0-18-vera-0-1-8.jsonl"
        )

    def test_a_slash_in_the_model_becomes_a_dash(self):
        # `moonshot/kimi-k3` cannot appear in a path segment.
        assert result_filename("moonshot/kimi-k3", "0.0.18", language="python") == (
            "moonshot-kimi-k3-python-bench-0-0-18.jsonl"
        )

    def test_python_and_typescript_carry_no_compiler_version(self):
        for lang in ("python", "typescript"):
            name = result_filename("m", "0.0.18", language=lang, vera_version="0.1.8")
            assert "vera-" not in name

    def test_unknown_versions_are_omitted_not_spelled(self):
        # `unknown` is what the CLI reports when a compiler is absent;
        # putting it in the name would make the file unmatchable.
        name = result_filename("m", "0.0.18", vera_version="unknown")
        assert name == "m-bench-0-0-18.jsonl"

    def test_version_slug(self):
        assert version_slug("0.0.18") == "0-0-18"


class TestCompilerSegment:
    """regrade.py decides whether a target was graded by the installed
    compiler by building that compiler's segment and checking the name ends
    with it, so the segment must be exactly what result_filename appends."""

    def test_each_graded_language_names_its_own_compiler(self):
        assert compiler_segment("vera", "0.1.13") == "vera-0-1-13"
        assert compiler_segment("aver", "0.27.1") == "aver-0-27-1"
        assert compiler_segment("ailang", "0.30.0") == "ailang-0-30-0"

    def test_no_segment_without_a_compiler_or_a_version(self):
        assert compiler_segment("python", "0.1.13") is None
        assert compiler_segment("typescript", "0.1.13") is None
        for missing in ("unknown", "", None):
            assert compiler_segment("vera", missing) is None

    def test_a_result_name_ends_with_its_segment(self):
        name = result_filename("m", "0.0.18", language="aver", aver_version="0.27.1")
        assert name.endswith(f"-{compiler_segment('aver', '0.27.1')}.jsonl")


class TestRecordedCompilerVersion:
    def test_reads_back_what_result_filename_wrote(self):
        for lang, version in (
            ("vera", "0.1.8"),
            ("aver", "0.27.1"),
            ("ailang", "0.30.0"),
        ):
            name = result_filename(
                "moonshot/kimi-k3",
                "0.0.18",
                language=lang,
                **{f"{lang}_version": version},
            )
            assert recorded_compiler_version(name, lang) == version, name

    def test_spec_from_nl_records_its_compiler_too(self):
        name = result_filename("m", "0.0.18", mode="spec-from-nl", vera_version="0.1.8")
        assert recorded_compiler_version(name, "vera") == "0.1.8"

    def test_a_language_segment_is_not_read_as_a_compiler_version(self):
        # An Aver name with no version still contains `-aver-`, as its
        # language segment; that must not come back as version `bench.0.0.18`.
        assert recorded_compiler_version("m-aver-bench-0-0-18.jsonl", "aver") is None
        assert recorded_compiler_version("m-bench-0-0-18.jsonl", "vera") is None

    def test_python_records_none(self):
        name = "m-python-bench-0-0-18.jsonl"
        assert recorded_compiler_version(name, "python") is None


class TestShellContract:
    """What the shell computes must be what Python computes."""

    def test_the_module_cli_prints_the_same_name(self):
        expected = result_filename("claude-opus-5", "0.0.18", vera_version="0.1.8")
        out = subprocess.run(
            [
                sys.executable,
                "-m",
                "vera_bench.results_path",
                "--model",
                "claude-opus-5",
                "--bench-version",
                "0.0.18",
                "--vera-version",
                "0.1.8",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
        assert out.stdout.strip() == expected


class TestNoHardcodedVersions:
    """A version written down is a version that goes stale silently."""

    #: Deliberate historical pins, not drift: GRADEABLE_ADDED records the
    #: release each problem became gradeable in, and the chart scripts
    #: keep frozen lineups for versions whose models have since retired.
    ALLOWED = re.compile(
        r"GRADEABLE_ADDED|HISTORICAL_LINEUPS|_LINEUP_V_|"
        r"^\s*#|^\s*\"|^\s*'|python scripts/|0\.0\.7|0\.0\.9|0\.0\.112"
    )

    @pytest.mark.parametrize("script", ["run_sweep.sh", "sweep_status.py"])
    def test_the_sweep_scripts_do_not_spell_a_bench_version(self, script):
        # These two decide what has already run. A literal here made a
        # finished target look unfinished (and a finished older sweep
        # look like the current one).
        text = (SCRIPTS / script).read_text()
        offenders = [
            ln
            for ln in text.splitlines()
            if re.search(r"bench[-\s]0-0-\d+", ln) and not self.ALLOWED.search(ln)
        ]
        assert not offenders, offenders

    def test_run_sweep_does_not_re_derive_a_version_with_a_regex(self):
        # A `[0-9]+\.[0-9]+\.[0-9]+` match keeps only the numeric head, so
        # a prerelease (`0.0.19rc1`) becomes `0.0.19` — a name the CLI
        # never writes, which is this bug wearing a different hat. Both
        # versions must be read from the code that writes them.
        text = (SCRIPTS / "run_sweep.sh").read_text()
        offenders = [
            ln
            for ln in text.splitlines()
            if r"[0-9]+\.[0-9]+" in ln and not ln.lstrip().startswith("#")
        ]
        assert not offenders, offenders

    def test_run_sweep_builds_every_result_name_through_results_path(self):
        # A hand-assembled name is a second construction, free to drift
        # from the one `vera-bench run` uses. The aver/ailang globs were
        # the last two; their compiler segment is a wildcard, but the name
        # around it still comes from results_path.
        text = (SCRIPTS / "run_sweep.sh").read_text()
        offenders = [
            ln
            for ln in text.splitlines()
            if ".jsonl" in ln
            and "result_file" not in ln
            and not ln.lstrip().startswith("#")
        ]
        assert not offenders, offenders

    def test_the_chart_scripts_default_to_the_repo_version(self):
        # Running a chart script with no arguments must plot THIS
        # release, not whichever one was current when it was written.
        for script in ("plot_results.py", "plot_slide.py", "plot_narrative.py"):
            text = (SCRIPTS / script).read_text()
            block = text[text.index('"--version"') :][:400]
            assert "_default_version()" in block, script

    def test_default_version_agrees_with_the_package(self):
        # The charts read the repo's pyproject.toml; the sweep scripts read
        # the installed `vera_bench.__version__`. Two sources, so they are
        # pinned to agree — a release that bumped one and not the other
        # would have charts and sweeps naming different eras.
        sys.path.insert(0, str(REPO_ROOT))
        from scripts.plot_results import _default_version

        assert _default_version() == __version__
