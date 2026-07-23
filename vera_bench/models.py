"""LLM API abstraction (Anthropic, OpenAI)."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

_T = TypeVar("_T")


class AuthError(EnvironmentError):
    """API credential failure — aborts the whole sweep.

    Subclasses EnvironmentError so existing callers and tests that
    catch/expect EnvironmentError keep working, but gives the runner a
    precise type to re-raise on. That precision matters: EnvironmentError
    IS OSError, so catching it broadly would also abort the sweep on a
    transient ConnectionError from the HTTP client — a network blip
    should cost one problem, not the whole run.
    """


def _as_count(value: object) -> int:
    """Normalise a provider-reported token counter to a safe int.

    Providers occasionally report None (field absent), and mocks report
    MagicMock. Either reaches ProblemResult and then json.dumps, which
    raises "Object of type X is not JSON serializable" mid-sweep — after
    the API spend. Negative values are equally nonsensical. type() not
    isinstance(): bool is an int subclass.
    """
    return value if type(value) is int and value >= 0 else 0


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    wall_time_s: float
    model: str
    # Cache-hit portion of input_tokens (0 when the provider reports
    # nothing). Anthropic: cache_read_input_tokens. OpenAI-compatible:
    # usage.prompt_tokens_details.cached_tokens. Issue #61.
    cached_tokens: int = 0


def _openai_cached_tokens(usage: object) -> int:
    """Extract usage.prompt_tokens_details.cached_tokens defensively.

    OpenAI-compatible providers (OpenAI, Moonshot, OpenRouter) report
    cache hits under prompt_tokens_details, but the field is absent on
    older SDKs / non-caching providers and may be None. The isinstance
    guard also keeps MagicMock-based tests honest — an auto-created
    mock attribute is not an int and must not leak into accounting.
    """
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) if details is not None else 0
    # type() check, not isinstance: bool is an int subclass, and a
    # provider quirk returning True must not count as 1 cached token.
    return cached if type(cached) is int else 0


def _prompt_cache_key(system: str) -> str:
    """Stable cache-routing key for requests sharing a system prefix.

    OpenAI's prompt caching is automatic (>=1024 tokens) but
    `prompt_cache_key` improves hit rates by routing same-prefix
    requests to the same cache shard — recommended for the GPT-5.6
    family. Keyed on the system prompt (the ~28k-token SKILL.md /
    llms.txt prefix during sweeps) so each language-mode gets its own
    stable shard.
    """
    digest = hashlib.sha256(system.encode("utf-8")).hexdigest()[:16]
    return f"vera-bench-{digest}"


def _call_openai_compatible(
    create_fn: Callable[[], _T], label: str, key_hint: str, model: str
) -> _T:
    """Invoke an OpenAI-compatible create() with the standard error map.

    Shared by OpenAIClient / MoonshotClient / OpenRouterClient — same
    exception taxonomy, provider-specific label and credential hint:
    - APITimeoutError -> TimeoutError
    - AuthenticationError -> EnvironmentError (abort the run —
      retrying 60 problems with the same bad key is pure waste; the
      benchmark loop re-raises EnvironmentError rather than recording
      per-problem crash rows)
    - RateLimitError / BadRequestError / APIStatusError -> clean
      RuntimeError messages instead of raw multi-line openai reprs
      landing in JSONL
    """
    import openai

    try:
        return create_fn()
    except openai.APITimeoutError as e:
        raise TimeoutError(f"{label} API timed out: {e}") from e
    except openai.AuthenticationError as e:
        raise AuthError(f"{label} authentication failed (check {key_hint}): {e}") from e
    except openai.RateLimitError as e:
        raise RuntimeError(
            f"{label} rate-limited the model={model!r} "
            f"request: {e}. Slow the sweep or use a higher tier."
        ) from e
    except openai.BadRequestError as e:
        raise RuntimeError(
            f"{label} rejected the request to model={model!r}: {e}. "
            "Often model id wrong or prompt exceeds context."
        ) from e
    except openai.APIStatusError as e:
        raise RuntimeError(
            f"{label} API error (status={getattr(e, 'status_code', '?')}) "
            f"on model={model!r}: {e}"
        ) from e


def _validate_openai_response_text(response: Any, label: str, model: str) -> str:
    """Extract text from an OpenAI-compatible response, or raise.

    Explicit errors on empty choices / empty content — without these
    the harness would receive text="" and blame the model for "did
    not define entry point" when the real fault is API-side (content
    filter, tool-call-only response, truncation).
    """
    if not response.choices:
        finish_reason = getattr(response, "finish_reason", "no choices")
        raise RuntimeError(
            f"{label} returned no choices for model={model!r} "
            f"(finish_reason={finish_reason})"
        )
    choice = response.choices[0]
    message = getattr(choice, "message", None)
    text = getattr(message, "content", None) if message is not None else None
    # isinstance check, not just truthiness: newer APIs can return
    # structured content (a list of blocks) where a bare truthiness test
    # would pass a non-str through to LLMResponse.text, and extract_code's
    # regex would then fail far from the cause.
    if not isinstance(text, str) or not text:
        finish_reason = getattr(choice, "finish_reason", "unknown")
        raise RuntimeError(
            f"{label} returned empty content for model={model!r} "
            f"(finish_reason={finish_reason})"
        )
    return text


class LLMClient(Protocol):
    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> LLMResponse: ...


def create_client(model: str) -> LLMClient:
    """Create an LLM client based on the model identifier.

    - claude-* -> AnthropicClient
    - gpt-*, o1-*, o3-* -> OpenAIClient
    - openai-pro/* -> OpenAIClient at reasoning mode "pro" (e.g.
      openai-pro/gpt-5.6-sol runs Sol with reasoning.mode=pro — a
      distinct benchmark entry from default-mode gpt-5.6-sol; the
      CLI model string drives distinct results filenames)
    - moonshot/* -> MoonshotClient (OpenAI-compatible)
    - or/* -> OpenRouterClient (OpenAI-compatible; routes to any
      OpenRouter-hosted model, e.g. or/moonshotai/kimi-k2-0905)
    """
    if model.startswith("claude-") or model.startswith("anthropic/"):
        return AnthropicClient(model)
    if model.startswith("openai-pro/"):
        bare = model.removeprefix("openai-pro/")
        if not bare:
            raise ValueError(
                "openai-pro/ requires a model id, e.g. openai-pro/gpt-5.6-sol"
            )
        return OpenAIClient(bare, reasoning_mode="pro")
    if (
        model.startswith("gpt-")
        or model.startswith("o1-")
        or model.startswith("o3-")
        or model.startswith("openai/")
    ):
        return OpenAIClient(model)
    if model.startswith("moonshot/"):
        return MoonshotClient(model)
    if model.startswith("or/"):
        return OpenRouterClient(model)
    raise ValueError(
        f"Unknown model: {model!r}. "
        "Expected claude-*, anthropic/*, gpt-*, o1-*, o3-*, openai/*, "
        "openai-pro/*, moonshot/*, or or/* prefix."
    )


class AnthropicClient:
    def __init__(self, model: str) -> None:
        try:
            import anthropic  # noqa: F811
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install vera-bench[llm]"
            ) from None

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY environment variable not set")

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model.removeprefix("anthropic/")

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> LLMResponse:
        import anthropic

        start = time.monotonic()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user}],
                timeout=timeout,
            )
        except anthropic.APITimeoutError as e:
            raise TimeoutError(f"Anthropic API timed out: {e}") from e

        elapsed = time.monotonic() - start
        text = response.content[0].text if response.content else ""
        usage = response.usage
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        return LLMResponse(
            text=text,
            input_tokens=(
                _as_count(usage.input_tokens)
                + _as_count(cache_creation)
                + _as_count(cache_read)
            ),
            output_tokens=_as_count(usage.output_tokens),
            wall_time_s=round(elapsed, 2),
            model=response.model,
            cached_tokens=_as_count(cache_read),
        )


class OpenAIClient:
    def __init__(self, model: str, reasoning_mode: str | None = None) -> None:
        try:
            import openai  # noqa: F811
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install vera-bench[llm]"
            ) from None

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY environment variable not set")

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model.removeprefix("openai/")
        # Reasoning mode (e.g. "pro" for gpt-5.6-sol's ceiling tier).
        # Set by the openai-pro/ routing prefix in create_client; never
        # via the runner (the complete() Protocol carries no per-call
        # config — see the openai-pro design notes in the v0.0.16 plan).
        self._reasoning_mode = reasoning_mode

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> LLMResponse:
        # Reasoning consumes completion budget on reasoning models —
        # a 4096 default can be all deliberation and no output at the
        # pro tier. Floor the budget when a reasoning mode is active;
        # smoke test S2 validates against truncation.
        effective_max = max_tokens
        if self._reasoning_mode:
            effective_max = max(max_tokens, 16000)

        # Cache-shard routing for the shared system prefix, passed via
        # extra_body so it works on any 1.x SDK regardless of
        # typed-kwarg support (#61). The reasoning mode rides the same
        # channel ("reasoning.mode" per OpenAI's gpt-5.5-pro
        # deprecation notice); smoke S2 verifies the exact accepted
        # shape before the sweep.
        extra_body: dict = {"prompt_cache_key": _prompt_cache_key(system)}
        if self._reasoning_mode:
            extra_body["reasoning"] = {"mode": self._reasoning_mode}

        start = time.monotonic()
        response = _call_openai_compatible(
            lambda: self._client.with_options(timeout=timeout).chat.completions.create(
                model=self._model,
                # max_completion_tokens supersedes max_tokens on the
                # GPT-5.x reasoning families (which reject the legacy
                # kwarg); all matrix OpenAI models are 5.6-family.
                # Smoke S1 validates acceptance per model.
                max_completion_tokens=effective_max,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                extra_body=extra_body,
            ),
            label="OpenAI",
            key_hint="OPENAI_API_KEY",
            model=self._model,
        )
        elapsed = time.monotonic() - start
        text = _validate_openai_response_text(response, "OpenAI", self._model)
        usage = response.usage
        # Both Sol variants report the same API model id — suffix the
        # reasoning mode so JSONL rows are self-describing (filenames
        # are already distinct via the CLI model string).
        reported_model = response.model or self._model
        if self._reasoning_mode:
            reported_model = f"{reported_model}#{self._reasoning_mode}"
        return LLMResponse(
            text=text,
            input_tokens=_as_count(usage.prompt_tokens) if usage else 0,
            output_tokens=_as_count(usage.completion_tokens) if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=reported_model,
            cached_tokens=_openai_cached_tokens(usage) if usage else 0,
        )


MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"


class MoonshotClient:
    """Moonshot (Kimi) client — OpenAI-compatible API."""

    def __init__(self, model: str) -> None:
        try:
            import openai  # noqa: F811
        except ImportError:
            raise ImportError(
                "openai package required for Moonshot. "
                "Install with: pip install vera-bench[llm]"
            ) from None

        api_key = os.environ.get("MOONSHOT_API_KEY")
        if not api_key:
            raise EnvironmentError("MOONSHOT_API_KEY environment variable not set")

        self._client = openai.OpenAI(api_key=api_key, base_url=MOONSHOT_BASE_URL)
        self._model = model.removeprefix("moonshot/")

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> LLMResponse:
        start = time.monotonic()
        response = _call_openai_compatible(
            lambda: self._client.with_options(timeout=timeout).chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # No cache parameter: Moonshot's Context Caching is fully
                # automatic (prefix matching on all requests, no headers
                # or cache-lifecycle calls — see #61 research notes).
            ),
            label="Moonshot",
            key_hint="MOONSHOT_API_KEY",
            model=self._model,
        )
        elapsed = time.monotonic() - start
        text = _validate_openai_response_text(response, "Moonshot", self._model)
        usage = response.usage
        return LLMResponse(
            text=text,
            input_tokens=_as_count(usage.prompt_tokens) if usage else 0,
            output_tokens=_as_count(usage.completion_tokens) if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=response.model or self._model,
            cached_tokens=_openai_cached_tokens(usage) if usage else 0,
        )


# OpenRouter — OpenAI-compatible API that proxies many model providers.
# https://openrouter.ai
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """OpenRouter client — OpenAI-compatible API.

    Routes to any model hosted on OpenRouter. Use the `or/` prefix and the
    upstream model id, e.g. `or/moonshotai/kimi-k2-0905` to access the same
    Kimi K2.5 model that VeraBench's published Vera 100% result used.
    """

    def __init__(self, model: str) -> None:
        try:
            import openai  # noqa: F811
        except ImportError:
            raise ImportError(
                "openai package required for OpenRouter. "
                "Install with: pip install vera-bench[llm]"
            ) from None

        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENROUTER_API_KEY environment variable not set")

        self._client = openai.OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
        self._model = model.removeprefix("or/")

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> LLMResponse:
        start = time.monotonic()
        response = _call_openai_compatible(
            lambda: self._client.with_options(timeout=timeout).chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            ),
            label="OpenRouter",
            key_hint="OPENROUTER_API_KEY",
            model=self._model,
        )
        elapsed = time.monotonic() - start
        text = _validate_openai_response_text(response, "OpenRouter", self._model)
        usage = response.usage
        return LLMResponse(
            text=text,
            input_tokens=_as_count(usage.prompt_tokens) if usage else 0,
            output_tokens=_as_count(usage.completion_tokens) if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=response.model or self._model,
            cached_tokens=_openai_cached_tokens(usage) if usage else 0,
        )
