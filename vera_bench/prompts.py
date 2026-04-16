"""Prompt construction for VeraBench evaluations."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

SYSTEM_PROMPT = (
    "You are an expert Vera programmer. "
    "Write valid Vera code that compiles and verifies."
)

_WRITE_INSTRUCTION = (
    "Write a complete Vera function (including requires, ensures, effects, and body). "
)

SKILL_MD_URL = "https://veralang.dev/SKILL.md"
AVER_LLMS_TXT_URL = "https://averlang.dev/llms.txt"

_USER_AGENT = "vera-bench/0.0.9"


def _fetch_url(url: str, *, timeout: int = 10) -> str:
    """Fetch a URL with a proper User-Agent (avoids Cloudflare 403s)."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def load_skill_md(source: str | Path | None = None) -> str:
    """Load SKILL.md from a URL or local file.

    If source is None, fetches from veralang.dev.
    If source starts with http, fetches from that URL.
    Otherwise reads from the local file path.
    """
    if source is None:
        source = SKILL_MD_URL

    source_str = str(source)
    if source_str.startswith("http"):
        try:
            return _fetch_url(source_str)
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(
                f"Failed to fetch SKILL.md from {source_str}: {e}\n"
                "Use --skill-md to provide a local copy."
            ) from e

    return Path(source).read_text(encoding="utf-8")


def load_aver_llms_txt(source: str | Path | None = None) -> str:
    """Load Aver llms.txt from a URL or local file.

    If source is None, fetches from averlang.dev.
    If source starts with http, fetches from that URL.
    Otherwise reads from the local file path.
    """
    if source is None:
        source = AVER_LLMS_TXT_URL

    source_str = str(source)
    if source_str.startswith("http"):
        try:
            return _fetch_url(source_str)
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(
                f"Failed to fetch llms.txt from {source_str}: {e}\n"
                "Use --skill-md to provide a local copy."
            ) from e

    return Path(source).read_text(encoding="utf-8")


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


def _neutral_description(problem: dict) -> str:
    """Return language-neutral description, falling back to original."""
    return problem.get("description_neutral") or problem["description"]


def build_python_prompt(problem: dict) -> dict:
    """Build a prompt asking the model to write Python.

    Returns dict with 'system' and 'user' keys.
    """
    entry_point = problem["entry_point"]
    user_msg = (
        f"{_neutral_description(problem)}\n\n"
        f"Write a Python function named `{entry_point}`. "
        "Output only the Python code, no explanation."
    )
    return {
        "system": PYTHON_SYSTEM_PROMPT,
        "user": user_msg,
    }


TYPESCRIPT_SYSTEM_PROMPT = (
    "You are an expert TypeScript programmer. Write correct, concise TypeScript code."
)


def build_typescript_prompt(problem: dict) -> dict:
    """Build a prompt asking the model to write TypeScript.

    Returns dict with 'system' and 'user' keys.
    """
    from vera_bench.baseline_runner import _snake_to_camel

    entry_point = _snake_to_camel(problem["entry_point"])
    user_msg = (
        f"{_neutral_description(problem)}\n\n"
        f"Write a TypeScript function named `{entry_point}`. "
        "Output only the TypeScript code, no explanation."
    )
    return {
        "system": TYPESCRIPT_SYSTEM_PROMPT,
        "user": user_msg,
    }


AVER_SYSTEM_PROMPT = (
    "You are an expert Aver programmer. "
    "Write correct, concise Aver code. "
    "Aver is not in your training data — use the llms.txt reference below."
)


def build_aver_prompt(problem: dict, llms_txt: str) -> dict:
    """Build a prompt asking the model to write Aver.

    Same approach as Python/TypeScript: raw description + function name.
    The llms.txt in the system prompt replaces training data.
    """
    entry_point = problem["entry_point"]
    user_msg = (
        f"{_neutral_description(problem)}\n\n"
        f"Write an Aver function named `{entry_point}`. "
        "Output only the Aver code, no explanation."
    )
    return {
        "system": f"{AVER_SYSTEM_PROMPT}\n\n{llms_txt}",
        "user": user_msg,
    }


def build_aver_fix_prompt(original_code: str, error_output: str, llms_txt: str) -> dict:
    """Build a retry prompt after a failed Aver check.

    Returns dict with 'system' and 'user' keys.
    """
    user_msg = (
        "The Aver code you wrote:\n\n"
        f"```aver\n{original_code}\n```\n\n"
        f"produced this error:\n\n{error_output}\n\n"
        "Fix the code. Output only the corrected Aver code, "
        "no explanation."
    )
    return {
        "system": f"{AVER_SYSTEM_PROMPT}\n\n{llms_txt}",
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
