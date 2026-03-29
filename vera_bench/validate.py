"""Validate problem definitions and canonical Vera solutions."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from vera_bench.vera_runner import VeraRunner

REQUIRED_FIELDS = [
    "id",
    "tier",
    "title",
    "description",
    "signature",
    "contracts",
    "entry_point",
    "tags",
    "test_cases",
    "vera_check_must_pass",
    "vera_verify_tier1",
]

console = Console()


def find_vera_file(problem_id: str, solutions_dir: Path) -> Path | None:
    """Find the .vera file for a problem by ID prefix match."""
    vera_dir = solutions_dir / "vera"
    prefix = problem_id + "_"
    matches = list(vera_dir.glob(f"{prefix}*.vera"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = [str(m) for m in matches]
        console.print(
            f"[yellow]Warning: multiple .vera files for {problem_id}: {names}[/yellow]"
        )
    return None


def normalize_output(raw: str, expected) -> tuple[str, str]:
    """Normalize vera run output and expected value for comparison.

    vera run outputs integers for bools (1/0), so we normalize accordingly.
    """
    raw_stripped = raw.strip()

    if isinstance(expected, bool):
        expected_str = "1" if expected else "0"
    elif isinstance(expected, str) and expected.lower() in ("true", "false"):
        expected_str = "1" if expected.lower() == "true" else "0"
    else:
        expected_str = str(expected)

    return raw_stripped, expected_str


def validate_problem(
    problem_path: Path,
    solutions_dir: Path,
    runner: VeraRunner,
) -> dict:
    """Validate a single problem. Returns a result dict."""
    result = {
        "file": problem_path.name,
        "id": "?",
        "fields_ok": False,
        "vera_found": False,
        "check_pass": None,
        "verify_pass": None,
        "verify_t1": None,
        "verify_t3": None,
        "tests_run": 0,
        "tests_pass": 0,
        "errors": [],
    }

    # Load JSON
    try:
        with open(problem_path, encoding="utf-8") as f:
            problem = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        result["errors"].append(f"JSON load error: {e}")
        return result

    result["id"] = problem.get("id", "?")

    # Check required fields
    missing = [f for f in REQUIRED_FIELDS if f not in problem]
    if missing:
        result["errors"].append(f"Missing fields: {', '.join(missing)}")
    else:
        result["fields_ok"] = True

    # Find .vera file
    vera_file = find_vera_file(result["id"], solutions_dir)
    if vera_file is None:
        result["errors"].append(f"No .vera file found for {result['id']}")
        return result
    result["vera_found"] = True

    # vera check
    try:
        check = runner.check(vera_file)
        result["check_pass"] = check.passed
        if not check.passed:
            for diag in check.diagnostics:
                result["errors"].append(
                    f"check: {diag.get('description', 'unknown error')}"
                )
    except Exception as e:
        result["errors"].append(f"check error: {e}")
        return result

    if not result["check_pass"]:
        return result

    # vera verify
    try:
        verify = runner.verify(vera_file)
        result["verify_pass"] = verify.passed
        result["verify_t1"] = verify.tier1_verified
        result["verify_t3"] = verify.tier3_runtime

        expects_tier1 = problem.get("vera_verify_tier1", False)
        if expects_tier1 and verify.tier3_runtime > 0:
            result["errors"].append(
                f"Expected all Tier 1 but got "
                f"{verify.tier3_runtime} Tier 3 runtime contracts"
            )
        if not verify.passed:
            for diag in verify.diagnostics:
                result["errors"].append(
                    f"verify: {diag.get('description', 'unknown error')[:120]}"
                )
    except Exception as e:
        result["errors"].append(f"verify error: {e}")

    # Test cases
    test_cases = problem.get("test_cases", [])
    entry_point = problem.get("entry_point", "")
    for tc in test_cases:
        args = tc.get("args", [])
        expected = tc.get("expected")
        result["tests_run"] += 1
        try:
            run = runner.run_fn(vera_file, entry_point, args if args else None)
            if run.exit_code != 0:
                result["errors"].append(
                    f"run({args}): non-zero exit code {run.exit_code}"
                )
                continue
            actual, expected_str = normalize_output(run.stdout, expected)
            if actual == expected_str:
                result["tests_pass"] += 1
            else:
                result["errors"].append(
                    f"run({args}): expected {expected_str!r}, got {actual!r}"
                )
        except Exception as e:
            result["errors"].append(f"run error({args}): {e}")

    return result


def run_validation(
    problems_dir: Path | None = None,
    solutions_dir: Path | None = None,
) -> int:
    """Run full validation. Returns exit code (0 = all pass)."""
    repo_root = Path(__file__).parent.parent
    if problems_dir is None:
        problems_dir = repo_root / "problems"
    if solutions_dir is None:
        solutions_dir = repo_root / "solutions"

    runner = VeraRunner()

    # Collect all problem JSONs
    problem_files = sorted(problems_dir.rglob("VB_*.json"))
    if not problem_files:
        console.print("[red]No problem files found![/red]")
        return 1

    console.print(f"\nValidating {len(problem_files)} problems...\n")

    results = []
    for pf in problem_files:
        r = validate_problem(pf, solutions_dir, runner)
        results.append(r)

    # Print summary table
    table = Table(title="Validation Results")
    table.add_column("Problem", style="cyan")
    table.add_column("Fields", justify="center")
    table.add_column(".vera", justify="center")
    table.add_column("Check", justify="center")
    table.add_column("Verify", justify="center")
    table.add_column("Tiers", justify="center")
    table.add_column("Tests", justify="center")
    table.add_column("Status", justify="center")

    all_ok = True
    for r in results:
        ok = r["fields_ok"] and r["vera_found"] and r["check_pass"] and not r["errors"]
        if not ok:
            all_ok = False

        tier_str = ""
        if r["verify_t1"] is not None:
            tier_str = f"T1:{r['verify_t1']} T3:{r['verify_t3']}"

        test_str = ""
        if r["tests_run"] > 0:
            test_str = f"{r['tests_pass']}/{r['tests_run']}"

        status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"

        table.add_row(
            r["id"],
            "[green]OK[/green]" if r["fields_ok"] else "[red]FAIL[/red]",
            "[green]OK[/green]" if r["vera_found"] else "[red]MISS[/red]",
            "[green]PASS[/green]"
            if r["check_pass"]
            else ("[red]FAIL[/red]" if r["check_pass"] is False else "-"),
            "[green]PASS[/green]"
            if r["verify_pass"]
            else ("[red]FAIL[/red]" if r["verify_pass"] is False else "-"),
            tier_str,
            test_str,
            status,
        )

    console.print(table)

    # Print errors
    for r in results:
        if r["errors"]:
            console.print(f"\n[red]{r['id']}:[/red]")
            for err in r["errors"]:
                console.print(f"  {err}")

    passed = sum(
        1
        for r in results
        if not r["errors"] and r["fields_ok"] and r["vera_found"] and r["check_pass"]
    )
    total = len(results)
    console.print(f"\n{passed}/{total} problems passed validation.")

    return 0 if all_ok else 1
