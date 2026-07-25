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
    """Extract the cached-token count across OpenAI-compatible providers.

    The field's *location* differs by provider, despite all three using
    the OpenAI SDK:

    - OpenAI and OpenRouter nest it:
      ``usage.prompt_tokens_details.cached_tokens``.
    - Moonshot reports it at the top level: ``usage.cached_tokens``
      (verified against their API reference, 2026-07-24). The SDK's
      ``CompletionUsage`` model is ``extra="allow"``, so this non-standard
      field survives parsing and is readable as an attribute — but only if
      we look there. Reading only the nested path recorded 0 for every
      Moonshot row despite Moonshot caching at ~99% on the shared prefix.

    Nested wins when present (that is the standard shape); the top-level
    read is the Moonshot fallback. type() not isinstance throughout: bool
    is an int subclass, and a provider quirk returning True must not count
    as one cached token.
    """
    details = getattr(usage, "prompt_tokens_details", None)
    nested = getattr(details, "cached_tokens", None) if details is not None else None
    if type(nested) is int:
        return nested
    top = getattr(usage, "cached_tokens", 0)
    return top if type(top) is int else 0


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


# Reasoning execution modes, per the OpenAI Responses API `reasoning.mode`
# field (Literal["standard", "pro"] in openai-python 2.47). This is a
# different axis from `reasoning.effort` — see OpenAIClient.__init__.
REASONING_MODES: frozenset[str] = frozenset({"standard", "pro"})

# Models routed to the Responses API even without an explicit mode.
#
# This exists to keep the reasoning-budget comparison controlled.
# `openai-pro/gpt-5.6-sol` can ONLY run on Responses (pro mode is
# Responses-only), so if its default-mode counterpart ran on Chat
# Completions the two arms would differ by endpoint as well as by mode —
# and the slide claims the difference is deliberation. Pinning both Sol
# entries here makes mode the only variable.
#
# Deliberately not every OpenAI model: gpt-5.6-terra is a separate tier
# row, not half of a controlled pair, and leaving it on Chat Completions
# avoids re-verifying a path that already works.
RESPONSES_API_MODELS: frozenset[str] = frozenset({"gpt-5.6-sol"})


def _anthropic_text(content: object) -> str:
    """Join the text blocks of an Anthropic response, skipping the rest.

    Models with extended thinking return ThinkingBlock (and possibly
    RedactedThinkingBlock) entries *ahead of* the TextBlock, so
    `content[0]` is not the answer — Claude Fable 5 fails outright on a
    blind `content[0].text` with "'ThinkingBlock' object has no
    attribute 'text'". Blocks are matched on `.type` rather than
    isinstance so a future SDK can add block kinds without breaking
    this, and every text block is joined rather than just the first,
    since nothing guarantees there is exactly one.
    """
    parts = [
        getattr(block, "text", "") or ""
        for block in (content or [])
        if getattr(block, "type", None) == "text"
    ]
    return "".join(parts)


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
        text = _anthropic_text(response.content)
        if not text:
            # Mirrors _validate_openai_response_text. Without this, an
            # empty string reaches extract_code and the row is recorded as
            # "did not define entry point" — the model blamed for an
            # API-side non-answer. Realistic for the thinking models this
            # release adds: a response truncated mid-deliberation contains
            # ThinkingBlocks and no TextBlock at all.
            kinds = [getattr(b, "type", "?") for b in (response.content or [])]
            raise RuntimeError(
                f"Anthropic returned no text block for model={self._model!r} "
                f"(stop_reason={getattr(response, 'stop_reason', 'unknown')}, "
                f"blocks={kinds}). Extended thinking may have consumed the "
                f"entire {max_tokens}-token budget — try raising --max-tokens."
            )
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
        # Reasoning execution mode for the ceiling ("pro") benchmark
        # entry. Set by the openai-pro/ routing prefix in create_client;
        # never via the runner (the complete() Protocol carries no
        # per-call config — see the v0.0.16 plan).
        #
        # `mode` and `effort` are INDEPENDENT axes: mode selects standard
        # vs pro execution, effort controls how much reasoning happens
        # within it. Pro mode exists only on the Responses API, so a
        # client with a mode set routes there instead of Chat
        # Completions. Chat Completions rejects the parameter outright
        # (400 "Unknown parameter: 'reasoning'"), and mapping pro onto
        # reasoning_effort="max" does not work either — gpt-5.6-sol
        # rejects "max" on Chat Completions, and effort is the wrong axis
        # regardless. Both verified live, 2026-07-23.
        if reasoning_mode is not None and reasoning_mode not in REASONING_MODES:
            raise ValueError(
                f"Unknown reasoning mode {reasoning_mode!r}. "
                f"Known modes: {sorted(REASONING_MODES)}"
            )
        if reasoning_mode is None and self._model in RESPONSES_API_MODELS:
            reasoning_mode = "standard"
        self._reasoning_mode = reasoning_mode

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> LLMResponse:
        # Reasoning consumes output budget on reasoning models — a 4096
        # default can be all deliberation and no answer at the pro tier.
        # The floor applies to standard mode too, not just pro: both arms
        # of the reasoning-budget comparison must get the same ceiling,
        # or the delta measures the budget as well as the mode. Smoke S2
        # validates against truncation.
        effective_max = max_tokens
        if self._reasoning_mode:
            effective_max = max(max_tokens, 16000)
            return self._complete_responses(system, user, effective_max, timeout)

        # Cache-shard routing for the shared system prefix (#61).
        # Sent via extra_body rather than as a typed kwarg to keep
        # this call shape identical to the Moonshot and OpenRouter
        # clients, which share this request path. (The original
        # reason — compatibility with 1.x SDKs lacking the typed
        # kwarg — no longer applies: pyproject floors openai at
        # >=2.45. _complete_responses passes it as a typed kwarg.)
        extra_body: dict = {"prompt_cache_key": _prompt_cache_key(system)}

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
        return LLMResponse(
            text=text,
            input_tokens=_as_count(usage.prompt_tokens) if usage else 0,
            output_tokens=_as_count(usage.completion_tokens) if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=response.model or self._model,
            cached_tokens=_openai_cached_tokens(usage) if usage else 0,
        )

    def _complete_responses(
        self, system: str, user: str, max_output: int, timeout: float
    ) -> LLMResponse:
        """Run through the Responses API, the only endpoint carrying
        `reasoning.mode`. Chat Completions rejects the parameter."""
        start = time.monotonic()
        response = _call_openai_compatible(
            lambda: self._client.with_options(timeout=timeout).responses.create(
                model=self._model,
                instructions=system,
                input=user,
                reasoning={"mode": self._reasoning_mode},
                max_output_tokens=max_output,
                prompt_cache_key=_prompt_cache_key(system),
                # Responses defaults store=True; Chat Completions does not
                # persist at all. Opting out keeps repeat sweeps mutually
                # independent — retained prompts and completions could feed
                # cross-run caching or personalisation, and a benchmark whose
                # second run is informed by its first is not measuring what
                # it claims to. (It also keeps 60 problems' worth of prompts
                # and generated code off the provider's servers.)
                store=False,
            ),
            label="OpenAI",
            key_hint="OPENAI_API_KEY",
            model=self._model,
        )
        elapsed = time.monotonic() - start

        # The response echoes the *effective* execution mode, so a silent
        # downgrade to standard is detectable here rather than inferred
        # later from suspiciously-similar wall times. A pro entry that
        # actually ran standard would make the headline comparison a
        # model against itself, so it must not pass quietly.
        # Absence must be as loud as mismatch. Both `reasoning` and `mode`
        # are Optional with None defaults, so a server that did NOT apply
        # the parameter most likely does not echo it either — and an
        # `if effective and ...` guard short-circuits past precisely the
        # case this exists to catch. The row is stamped "#pro" on the
        # strength of this check, and the reasoning slide's entire claim
        # rests on that suffix meaning something.
        effective = getattr(getattr(response, "reasoning", None), "mode", None)
        if effective != self._reasoning_mode:
            raise RuntimeError(
                f"OpenAI did not confirm the reasoning mode for "
                f"model={self._model!r}: requested {self._reasoning_mode!r}, "
                f"response reported {effective!r}. An unconfirmed mode must "
                f"not be recorded as '#{self._reasoning_mode}'."
            )

        text = (response.output_text or "").strip()
        if not text:
            detail = getattr(response, "incomplete_details", None)
            reason = getattr(detail, "reason", None) or getattr(
                response, "status", "unknown"
            )
            raise ValueError(
                f"OpenAI returned no output text for model={self._model!r} "
                f"(status/reason: {reason}). Reasoning may have consumed the "
                f"entire {max_output}-token budget."
            )

        usage = response.usage
        details = getattr(usage, "input_tokens_details", None) if usage else None
        # Both Sol variants report the same API model id — suffix the
        # reasoning mode so JSONL rows are self-describing (filenames
        # are already distinct via the CLI model string).
        reported = f"{response.model or self._model}#{self._reasoning_mode}"
        return LLMResponse(
            text=text,
            input_tokens=_as_count(getattr(usage, "input_tokens", 0)) if usage else 0,
            output_tokens=_as_count(getattr(usage, "output_tokens", 0)) if usage else 0,
            wall_time_s=round(elapsed, 2),
            model=reported,
            cached_tokens=_as_count(getattr(details, "cached_tokens", 0)),
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
        # Higher than the other providers' 120s, deliberately. Kimi on a
        # hard Tier-5 spec-from-NL problem exceeds 120s *every* time, not
        # occasionally: VB-T5-009 failed identically across a dozen
        # retries at four different --max-tokens values, because the
        # budget is the wrong lever — a smaller one does not make the
        # model deliberate faster. The harness asks whether a model CAN
        # solve a problem, not whether it can do so quickly, so a client
        # timeout that low was silently converting "slow" into "failed".
        # Recorded as a transient API error, it was also unfixable from
        # the CLI, which has no timeout flag (#105).
        timeout: float = 300.0,
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
