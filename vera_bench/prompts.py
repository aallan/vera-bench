"""Prompt construction for VeraBench evaluations."""

from __future__ import annotations

from pathlib import Path

SYSTEM_PROMPT = (
    "You are an expert Vera programmer. "
    "Write valid Vera code that compiles and verifies."
)

_WRITE_INSTRUCTION = (
    "Write a complete Vera function (including requires, ensures, effects, and body). "
)


def load_skill_md(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _format_contracts(contracts: dict) -> str:
    lines = []
    for req in contracts.get("requires", []):
        lines.append(f"  requires({req})")
    for ens in contracts.get("ensures", []):
        lines.append(f"  ensures({ens})")
    effects = contracts.get("effects", "pure")
    lines.append(f"  effects({effects})")
    return "\n".join(lines)


def build_full_spec_prompt(problem: dict, skill_md: str) -> dict:
    """Build a prompt with full contracts provided (Tier 1-2 mode).

    Returns dict with 'system' and 'user' keys.
    """
    contracts_str = _format_contracts(problem["contracts"])
    user_msg = (
        f"{problem['description']}\n\n"
        f"The function signature is:\n{problem['signature']}\n\n"
        f"The contracts are:\n{contracts_str}\n\n"
        f"{_WRITE_INSTRUCTION}"
        "Output only the Vera code, no explanation."
    )
    return {
        "system": f"{SYSTEM_PROMPT}\n\n{skill_md}",
        "user": user_msg,
    }


def build_spec_from_nl_prompt(problem: dict, skill_md: str) -> dict:
    """Build a prompt with only NL description and signature.

    Returns dict with 'system' and 'user' keys.
    """
    user_msg = (
        f"{problem['description']}\n\n"
        f"The function signature is:\n{problem['signature']}\n\n"
        f"{_WRITE_INSTRUCTION}"
        "You must write appropriate contracts. "
        "Output only the Vera code, no explanation."
    )
    return {
        "system": f"{SYSTEM_PROMPT}\n\n{skill_md}",
        "user": user_msg,
    }


PYTHON_SYSTEM_PROMPT = (
    "You are an expert Python programmer. Write correct, concise Python 3.11+ code."
)


def build_python_prompt(problem: dict) -> dict:
    """Build a prompt asking the model to write Python.

    Returns dict with 'system' and 'user' keys.
    """
    entry_point = problem["entry_point"]
    user_msg = (
        f"{problem['description']}\n\n"
        f"Write a Python function named `{entry_point}`. "
        "Output only the Python code, no explanation."
    )
    return {
        "system": PYTHON_SYSTEM_PROMPT,
        "user": user_msg,
    }


def build_fix_prompt(original_code: str, error_output: str) -> dict:
    """Build a retry prompt after a failed check.

    Returns dict with 'system' and 'user' keys.
    """
    user_msg = (
        "The Vera code you wrote:\n\n"
        f"```vera\n{original_code}\n```\n\n"
        f"produced this error:\n\n{error_output}\n\n"
        "Fix the code. Output only the corrected Vera code, "
        "no explanation."
    )
    return {
        "system": SYSTEM_PROMPT,
        "user": user_msg,
    }
