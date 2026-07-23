"""LLM API abstraction (Anthropic, OpenAI)."""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Protocol


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
    return cached if isinstance(cached, int) else 0


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
    - moonshot/* -> MoonshotClient (OpenAI-compatible)
    - or/* -> OpenRouterClient (OpenAI-compatible; routes to any
      OpenRouter-hosted model, e.g. or/moonshotai/kimi-k2-0905)
    """
    if model.startswith("claude-") or model.startswith("anthropic/"):
        return AnthropicClient(model)
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
        "moonshot/*, or or/* prefix."
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
            input_tokens=usage.input_tokens + cache_creation + cache_read,
            output_tokens=usage.output_tokens,
            wall_time_s=round(elapsed, 2),
            model=response.model,
            cached_tokens=cache_read if isinstance(cache_read, int) else 0,
        )


class OpenAIClient:
    def __init__(self, model: str) -> None:
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

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> LLMResponse:
        import openai

        start = time.monotonic()
        try:
            response = self._client.with_options(
                timeout=timeout
            ).chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # Cache-shard routing for the shared system prefix.
                # Passed via extra_body so it works on any 1.x SDK
                # regardless of typed-kwarg support (#61).
                extra_body={"prompt_cache_key": _prompt_cache_key(system)},
            )
        except openai.APITimeoutError as e:
            raise TimeoutError(f"OpenAI API timed out: {e}") from e
        except openai.AuthenticationError as e:
            # Bad API key — abort the run. Retrying 60 problems with the
            # same bad key is pure waste.
            raise EnvironmentError(
                f"OpenAI authentication failed (check OPENAI_API_KEY): {e}"
            ) from e
        except openai.RateLimitError as e:
            raise RuntimeError(
                f"OpenAI rate-limited the model={self._model!r} "
                f"request: {e}. Slow the sweep or use a higher tier."
            ) from e
        except openai.BadRequestError as e:
            raise RuntimeError(
                f"OpenAI rejected the request to model={self._model!r}: {e}. "
                "Often model id wrong or prompt exceeds context."
            ) from e
        except openai.APIStatusError as e:
            raise RuntimeError(
                f"OpenAI API error (status={getattr(e, 'status_code', '?')}) "
                f"on model={self._model!r}: {e}"
            ) from e

        elapsed = time.monotonic() - start

        if not response.choices:
            finish_reason = getattr(response, "finish_reason", "no choices")
            raise RuntimeError(
                f"OpenAI returned no choices for model={self._model!r} "
                f"(finish_reason={finish_reason})"
            )

        choice = response.choices[0]
        text = choice.message.content if choice.message else None
        if not text:
            finish_reason = getattr(choice, "finish_reason", "unknown")
            raise RuntimeError(
                f"OpenAI returned empty content for model={self._model!r} "
                f"(finish_reason={finish_reason})"
            )

        usage = response.usage
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=response.model or self._model,
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
        import openai

        start = time.monotonic()
        try:
            response = self._client.with_options(
                timeout=timeout
            ).chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # No cache parameter: Moonshot's Context Caching is fully
                # automatic (prefix matching on all requests, no headers
                # or cache-lifecycle calls — see #61 research notes).
            )
        except openai.APITimeoutError as e:
            raise TimeoutError(f"Moonshot API timed out: {e}") from e
        except openai.AuthenticationError as e:
            raise EnvironmentError(
                f"Moonshot authentication failed (check MOONSHOT_API_KEY): {e}"
            ) from e
        except openai.RateLimitError as e:
            raise RuntimeError(
                f"Moonshot rate-limited the model={self._model!r} "
                f"request: {e}. Slow the sweep or use a higher tier."
            ) from e
        except openai.BadRequestError as e:
            raise RuntimeError(
                f"Moonshot rejected the request to model={self._model!r}: {e}. "
                "Often model id wrong or prompt exceeds context."
            ) from e
        except openai.APIStatusError as e:
            raise RuntimeError(
                f"Moonshot API error (status={getattr(e, 'status_code', '?')}) "
                f"on model={self._model!r}: {e}"
            ) from e

        elapsed = time.monotonic() - start

        if not response.choices:
            finish_reason = getattr(response, "finish_reason", "no choices")
            raise RuntimeError(
                f"Moonshot returned no choices for model={self._model!r} "
                f"(finish_reason={finish_reason})"
            )

        choice = response.choices[0]
        text = choice.message.content if choice.message else None
        if not text:
            finish_reason = getattr(choice, "finish_reason", "unknown")
            raise RuntimeError(
                f"Moonshot returned empty content for model={self._model!r} "
                f"(finish_reason={finish_reason})"
            )

        usage = response.usage
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
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
        import openai

        start = time.monotonic()
        try:
            response = self._client.with_options(
                timeout=timeout
            ).chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except openai.APITimeoutError as e:
            raise TimeoutError(f"OpenRouter API timed out: {e}") from e
        except openai.AuthenticationError as e:
            # Bad API key — abort the run. Retrying 60 problems with the
            # same bad key is pure waste.
            raise EnvironmentError(
                f"OpenRouter authentication failed (check OPENROUTER_API_KEY): {e}"
            ) from e
        except openai.RateLimitError as e:
            raise RuntimeError(
                f"OpenRouter rate-limited the model={self._model!r} "
                f"request: {e}. Slow the sweep or use a higher tier."
            ) from e
        except openai.BadRequestError as e:
            raise RuntimeError(
                f"OpenRouter rejected the request to model={self._model!r}: {e}. "
                "Often model id wrong or prompt exceeds context."
            ) from e
        except openai.APIStatusError as e:
            # Catch-all for any other API-side failure (5xx, etc.) — these
            # used to propagate raw and land as multi-line openai-repr
            # `error_message` rows in JSONL. Wrap with a clean message.
            raise RuntimeError(
                f"OpenRouter API error (status={getattr(e, 'status_code', '?')}) "
                f"on model={self._model!r}: {e}"
            ) from e

        elapsed = time.monotonic() - start

        # Explicit error if the API returns no choices — without this,
        # we'd return text="" and the harness would blame the model for
        # "did not define entry point" when the real fault is API-side.
        if not response.choices:
            finish_reason = getattr(response, "finish_reason", "no choices")
            raise RuntimeError(
                f"OpenRouter returned no choices for model={self._model!r} "
                f"(finish_reason={finish_reason})"
            )

        choice = response.choices[0]
        # If the choice exists but content is None (e.g. content-filter or
        # tool-call without text), that's also worth surfacing rather than
        # silently becoming text="".
        text = choice.message.content if choice.message else None
        if not text:
            finish_reason = getattr(choice, "finish_reason", "unknown")
            raise RuntimeError(
                f"OpenRouter returned empty content for model={self._model!r} "
                f"(finish_reason={finish_reason})"
            )

        usage = response.usage
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=response.model or self._model,
            cached_tokens=_openai_cached_tokens(usage) if usage else 0,
        )
