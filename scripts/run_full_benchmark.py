#!/usr/bin/env python3
"""Run the full VeraBench benchmark suite (all 6 targets).

Usage:
  # Interactive mode — prompts for model and API key
  python scripts/run_full_benchmark.py

  # Autonomous mode
  python scripts/run_full_benchmark.py \
    --model claude-sonnet-4-20250514 --api-key sk-ant-...

  # Autonomous with env var
  ANTHROPIC_API_KEY=sk-ant-... \
    python scripts/run_full_benchmark.py --model claude-sonnet-4-20250514

Runs all 6 targets:
  1. Vera full-spec
  2. Vera spec-from-NL
  3. Python LLM generation
  4. TypeScript LLM generation
  5. Python baselines
  6. TypeScript baselines
"""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys

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


def _run(cmd: list[str], env: dict, timeout: int = 3600) -> int:
    """Run a vera-bench command, streaming output.

    Args:
        timeout: Maximum seconds per target (default 60 minutes).
    """
    print(f"\n{'=' * 60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'=' * 60}\n")
    try:
        result = subprocess.run(cmd, env=env, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"\nTIMEOUT after {timeout}s: {' '.join(cmd)}")
        return 1
    return result.returncode


def main():
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
            ]
        )

    # Run all targets
    results = {}
    for name, cmd in targets:
        rc = _run(cmd, env)
        results[name] = "PASS" if rc == 0 else f"FAIL (exit {rc})"

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}\n")
    for name, status in results.items():
        print(f"  {name}: {status}")

    # Generate report
    print(f"\n{'=' * 60}")
    print("Generating report...")
    print(f"{'=' * 60}\n")
    report_rc = _run(["vera-bench", "report", "results/"], env)
    if report_rc != 0:
        print(f"\nWarning: report generation failed (exit {report_rc})")

    failed = sum(1 for s in results.values() if "FAIL" in s)
    if failed:
        print(f"\n{failed} target(s) failed.")
        return 1
    print("\nAll targets completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
