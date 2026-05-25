"""LLM API abstraction (Anthropic, OpenAI)."""

from __future__ import annotations

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
            )
        except openai.APITimeoutError as e:
            raise TimeoutError(f"OpenAI API timed out: {e}") from e

        elapsed = time.monotonic() - start
        choice = response.choices[0] if response.choices else None
        text = (
            choice.message.content
            if choice and choice.message and choice.message.content
            else ""
        )
        usage = response.usage
        return LLMResponse(
            text=text or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=response.model or self._model,
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
            )
        except openai.APITimeoutError as e:
            raise TimeoutError(f"Moonshot API timed out: {e}") from e

        elapsed = time.monotonic() - start
        choice = response.choices[0] if response.choices else None
        text = (
            choice.message.content
            if choice and choice.message and choice.message.content
            else ""
        )
        usage = response.usage
        return LLMResponse(
            text=text or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=response.model or self._model,
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
        )
