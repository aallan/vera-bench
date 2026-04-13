#!/usr/bin/env python3
"""Run the full VeraBench benchmark suite (all 8 targets).

Usage:
  # Interactive mode — prompts for model and API key
  python scripts/run_full_benchmark.py

  # Autonomous mode
  python scripts/run_full_benchmark.py \
    --model claude-sonnet-4-20250514 --api-key sk-ant-...

  # Autonomous with env var
  ANTHROPIC_API_KEY=sk-ant-... \
    python scripts/run_full_benchmark.py --model claude-sonnet-4-20250514

Runs all 8 targets:
  1. Vera full-spec
  2. Vera spec-from-NL
  3. Python LLM generation
  4. TypeScript LLM generation
  5. Aver LLM generation
  6. Python baselines
  7. TypeScript baselines
  8. Aver baselines
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MODELS = {
    "anthropic": [
        ("Claude Sonnet 4", "claude-sonnet-4-20250514"),
        ("Claude Opus 4", "claude-opus-4-20250514"),
    ],
    "openai": [
        ("GPT-4o", "gpt-4o"),
        ("GPT-4.1", "gpt-4.1-2025-04-14"),
    ],
    "moonshot": [
        ("Kimi K2.5", "moonshot/kimi-k2.5"),
        ("Kimi K2 Turbo", "moonshot/kimi-k2-turbo-preview"),
    ],
}

PROVIDER_ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
}


def _detect_provider(model: str) -> str:
    if model.startswith("claude-") or model.startswith("anthropic/"):
        return "anthropic"
    if (
        model.startswith("gpt-")
        or model.startswith("o1-")
        or model.startswith("o3-")
        or model.startswith("openai/")
    ):
        return "openai"
    if model.startswith("moonshot/"):
        return "moonshot"
    return "unknown"


def _interactive_select_model() -> str:
    print("\n=== VeraBench Full Benchmark ===\n")
    print("Select a provider:\n")
    providers = list(MODELS.keys())
    for i, provider in enumerate(providers, 1):
        print(f"  {i}. {provider.title()}")

    while True:
        choice = input("\nProvider [1]: ").strip() or "1"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                break
        except ValueError:
            pass
        print("Invalid choice.")

    provider = providers[idx]
    models = MODELS[provider]

    print("\nSelect a model:\n")
    for i, (name, model_id) in enumerate(models, 1):
        print(f"  {i}. {name} ({model_id})")

    while True:
        choice = input("\nModel [1]: ").strip() or "1"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                break
        except ValueError:
            pass
        print("Invalid choice.")

    return models[idx][1]


def _ensure_api_key(model: str, api_key: str | None) -> dict:
    """Return env dict with the right API key set."""
    provider = _detect_provider(model)
    env_key = PROVIDER_ENV_KEYS.get(provider)

    if not env_key:
        print(f"Error: unknown provider for model {model!r}")
        sys.exit(1)

    # Check sources in order: --api-key flag, environment, interactive
    key = api_key or os.environ.get(env_key)

    if not key:
        key = getpass.getpass(f"\nEnter {env_key}: ").strip()
        if not key:
            print(f"Error: {env_key} is required.")
            sys.exit(1)

    env = dict(os.environ)
    env[env_key] = key
    return env


def _format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _run(cmd: list[str], env: dict, timeout: int = 3600) -> tuple[int, float]:
    """Run a vera-bench command, streaming output.

    Args:
        timeout: Maximum seconds per target (default 60 minutes).

    Returns:
        Tuple of (return_code, elapsed_seconds).
    """
    start_ts = datetime.now(timezone.utc)
    print(f"\n{'=' * 60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"Started: {start_ts.strftime('%H:%M:%S UTC')}")
    print(f"{'=' * 60}\n")
    t0 = time.monotonic()
    try:
        result = subprocess.run(cmd, env=env, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        finish_ts = datetime.now(timezone.utc)
        print(f"\nTIMEOUT after {_format_duration(elapsed)}")
        print(f"Timed out at: {finish_ts.strftime('%H:%M:%S UTC')}")
        return 1, elapsed
    elapsed = time.monotonic() - t0
    finish_ts = datetime.now(timezone.utc)
    print(f"\nCompleted in {_format_duration(elapsed)}")
    print(f"Finished: {finish_ts.strftime('%H:%M:%S UTC')}")
    return result.returncode, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the full VeraBench benchmark suite"
    )
    parser.add_argument(
        "--model",
        help="Model identifier (e.g. claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--api-key",
        help="API key (or set via environment variable)",
    )
    parser.add_argument(
        "--skip-baselines",
        action="store_true",
        help="Skip baseline runs (only run LLM targets)",
    )
    args = parser.parse_args()

    # Select model
    model = args.model or _interactive_select_model()
    print(f"\nModel: {model}")

    # Ensure API key
    env = _ensure_api_key(model, args.api_key)

    # Define targets
    targets = [
        ("Vera full-spec", ["vera-bench", "run", "--model", model]),
        (
            "Vera spec-from-NL",
            [
                "vera-bench",
                "run",
                "--model",
                model,
                "--mode",
                "spec-from-nl",
            ],
        ),
        (
            "Python LLM",
            [
                "vera-bench",
                "run",
                "--model",
                model,
                "--language",
                "python",
            ],
        ),
        (
            "TypeScript LLM",
            [
                "vera-bench",
                "run",
                "--model",
                model,
                "--language",
                "typescript",
            ],
        ),
        (
            "Aver LLM",
            [
                "vera-bench",
                "run",
                "--model",
                model,
                "--language",
                "aver",
            ],
        ),
    ]

    if not args.skip_baselines:
        targets.extend(
            [
                ("Python baselines", ["vera-bench", "baselines"]),
                (
                    "TypeScript baselines",
                    [
                        "vera-bench",
                        "baselines",
                        "--language",
                        "typescript",
                    ],
                ),
                (
                    "Aver baselines",
                    [
                        "vera-bench",
                        "baselines",
                        "--language",
                        "aver",
                    ],
                ),
            ]
        )

    # Run all targets
    results: dict[str, dict] = {}
    run_start_ts = datetime.now(timezone.utc)
    run_start = time.monotonic()
    for name, cmd in targets:
        rc, elapsed = _run(cmd, env)
        results[name] = {
            "status": "PASS" if rc == 0 else f"FAIL (exit {rc})",
            "elapsed": elapsed,
        }
    total_elapsed = time.monotonic() - run_start

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}\n")
    name_width = max(len(n) for n in results)
    for name, info in results.items():
        duration = _format_duration(info["elapsed"])
        print(f"  {name:<{name_width}}  {info['status']:<16} {duration:>12}")
    total_dur = _format_duration(total_elapsed)
    print(f"\n  {'Total':<{name_width}}  {'':<16} {total_dur:>12}")

    # Write timing.json
    timing_path = Path("results") / "timing.json"
    timing_path.parent.mkdir(parents=True, exist_ok=True)
    run_end_ts = datetime.now(timezone.utc)
    timing_data = {
        "model": model,
        "started_at": run_start_ts.isoformat(),
        "finished_at": run_end_ts.isoformat(),
        "total_seconds": round(total_elapsed, 1),
        "targets": {
            name: {
                "status": info["status"],
                "seconds": round(info["elapsed"], 1),
            }
            for name, info in results.items()
        },
    }
    timing_path.write_text(json.dumps(timing_data, indent=2) + "\n", encoding="utf-8")
    print(f"\nTiming written to {timing_path}")

    # Generate report
    print(f"\n{'=' * 60}")
    print("Generating report...")
    print(f"{'=' * 60}\n")
    report_rc, _ = _run(["vera-bench", "report", "results/"], env)
    if report_rc != 0:
        print(f"\nWarning: report generation failed (exit {report_rc})")

    failed = sum(1 for info in results.values() if "FAIL" in info["status"])
    if failed:
        print(f"\n{failed} target(s) failed.")
        return 1
    print("\nAll targets completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
