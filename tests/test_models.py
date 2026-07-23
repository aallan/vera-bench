"""Tests for models.py — LLM API abstraction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vera_bench.models import create_client


class TestCreateClient:
    def test_anthropic(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("claude-sonnet-4-6")

    def test_anthropic_prefix(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("anthropic/claude-3-opus")

    def test_openai(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("gpt-4o")

    def test_o1(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("o1-preview")

    def test_o3(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("o3-mini")

    def test_openai_prefix(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("openai/gpt-4")

    def test_moonshot(self, monkeypatch):
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("moonshot/kimi-k2")

    def test_unknown(self):
        with pytest.raises(ValueError, match="Unknown model"):
            create_client("llama-3-70b")


class TestMoonshotClient:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        try:
            from vera_bench.models import MoonshotClient

            with pytest.raises(EnvironmentError, match="MOONSHOT_API_KEY"):
                MoonshotClient("moonshot/kimi-k2")
        except ImportError:
            pytest.skip("openai package not installed")


class TestAnthropicClient:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        try:
            from vera_bench.models import AnthropicClient

            with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
                AnthropicClient("claude-sonnet-4-6")
        except ImportError:
            pytest.skip("anthropic package not installed")


class TestOpenAIClient:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        try:
            from vera_bench.models import OpenAIClient

            with pytest.raises(EnvironmentError, match="OPENAI_API_KEY"):
                OpenAIClient("gpt-4o")
        except ImportError:
            pytest.skip("openai package not installed")


def _text_block(text: str):
    """A TextBlock stand-in. `.type` matters — the real SDK discriminates
    content blocks on it, and MagicMock's auto-attributes would hide a
    bug that only shows up against the live API."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


class _ThinkingBlock:
    """A ThinkingBlock stand-in with **no** `.text` attribute, which is
    what makes this faithful: the live failure was
    "'ThinkingBlock' object has no attribute 'text'". A MagicMock would
    have silently supplied one and reproduced nothing."""

    type = "thinking"
    thinking = "let me work through this"


class TestAnthropicTextExtraction:
    """Claude Fable 5 returns extended-thinking blocks ahead of the text,
    so content[0] is not the answer (smoke S1, 2026-07-23)."""

    def test_skips_leading_thinking_block(self):
        from vera_bench.models import _anthropic_text

        assert _anthropic_text([_ThinkingBlock(), _text_block("answer")]) == "answer"

    def test_plain_text_response(self):
        from vera_bench.models import _anthropic_text

        assert _anthropic_text([_text_block("answer")]) == "answer"

    def test_joins_multiple_text_blocks(self):
        from vera_bench.models import _anthropic_text

        blocks = [_ThinkingBlock(), _text_block("part one "), _text_block("part two")]
        assert _anthropic_text(blocks) == "part one part two"

    def test_unknown_block_types_ignored(self):
        from vera_bench.models import _anthropic_text

        redacted = MagicMock()
        redacted.type = "redacted_thinking"
        assert _anthropic_text([redacted, _text_block("answer")]) == "answer"

    @pytest.mark.parametrize("content", [[], None, [_ThinkingBlock()]])
    def test_no_text_block_yields_empty_string(self, content):
        from vera_bench.models import _anthropic_text

        assert _anthropic_text(content) == ""


class TestAnthropicComplete:
    def test_thinking_response_does_not_crash(self, monkeypatch):
        """End-to-end regression for the Fable 5 failure."""
        try:
            import anthropic  # noqa: F401

            from vera_bench.models import AnthropicClient
        except ImportError:
            pytest.skip("anthropic not installed")

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        client = AnthropicClient("claude-fable-5")

        mock_resp = MagicMock()
        mock_resp.content = [_ThinkingBlock(), _text_block("def f(): pass")]
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 50
        mock_resp.usage.cache_creation_input_tokens = 0
        mock_resp.usage.cache_read_input_tokens = 0
        mock_resp.model = "claude-fable-5"
        client._client.messages.create = MagicMock(return_value=mock_resp)

        assert client.complete("system", "user").text == "def f(): pass"

    def test_complete_mock(self, monkeypatch):
        """Test Anthropic complete with a mocked SDK."""
        try:
            import anthropic  # noqa: F401

            from vera_bench.models import AnthropicClient
        except ImportError:
            pytest.skip("anthropic not installed")

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        client = AnthropicClient("claude-test")

        mock_resp = MagicMock()
        mock_resp.content = [_text_block("hello")]
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 50
        mock_resp.usage.cache_creation_input_tokens = 0
        mock_resp.usage.cache_read_input_tokens = 0
        mock_resp.model = "claude-test"
        client._client.messages.create = MagicMock(return_value=mock_resp)

        result = client.complete("system", "user")
        assert result.text == "hello"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.model == "claude-test"


class TestOpenAIComplete:
    def test_complete_mock(self, monkeypatch):
        """Test OpenAI complete with a mocked SDK."""
        try:
            import openai  # noqa: F401

            from vera_bench.models import OpenAIClient
        except ImportError:
            pytest.skip("openai not installed")

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        client = OpenAIClient("gpt-test")

        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "world"
        mock_resp.choices = [mock_choice]
        mock_resp.usage.prompt_tokens = 200
        mock_resp.usage.completion_tokens = 75
        mock_resp.model = "gpt-test"

        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = mock_resp
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

        result = client.complete("system", "user")
        assert result.text == "world"
        assert result.input_tokens == 200
        assert result.output_tokens == 75
        assert result.model == "gpt-test"


class TestMoonshotComplete:
    def test_complete_mock(self, monkeypatch):
        """Test Moonshot complete with a mocked SDK."""
        try:
            import openai  # noqa: F401

            from vera_bench.models import MoonshotClient
        except ImportError:
            pytest.skip("openai not installed")

        monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")

        client = MoonshotClient("moonshot/kimi-k2")

        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "kimi response"
        mock_resp.choices = [mock_choice]
        mock_resp.usage.prompt_tokens = 150
        mock_resp.usage.completion_tokens = 60
        mock_resp.model = "kimi-k2"

        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = mock_resp
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

        result = client.complete("system", "user")
        assert result.text == "kimi response"
        assert result.input_tokens == 150
        assert result.output_tokens == 60
        assert result.model == "kimi-k2"


class TestLLMResponse:
    def test_fields(self):
        from vera_bench.models import LLMResponse

        r = LLMResponse(
            text="hello",
            input_tokens=100,
            output_tokens=50,
            wall_time_s=1.5,
            model="test",
        )
        assert r.text == "hello"
        assert r.input_tokens == 100
        assert r.output_tokens == 50
        assert r.wall_time_s == 1.5
        assert r.model == "test"


class TestOpenRouterClient:
    def test_create_client_routes_or_prefix(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("or/moonshotai/kimi-k2-0905")

    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        try:
            from vera_bench.models import OpenRouterClient

            with pytest.raises(EnvironmentError, match="OPENROUTER_API_KEY"):
                OpenRouterClient("or/moonshotai/kimi-k2-0905")
        except ImportError:
            pytest.skip("openai package not installed")


class TestOpenRouterComplete:
    def test_complete_mock(self, monkeypatch):
        """OpenRouter.complete with mocked OpenAI SDK call."""
        try:
            import openai  # noqa: F401

            from vera_bench.models import OpenRouterClient
        except ImportError:
            pytest.skip("openai not installed")

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        client = OpenRouterClient("or/moonshotai/kimi-k2-0905")
        # The `or/` prefix should be stripped from the model name passed
        # to the API call (the API doesn't know about our routing prefix).
        assert client._model == "moonshotai/kimi-k2-0905"

        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "openrouter response"
        mock_resp.choices = [mock_choice]
        mock_resp.usage.prompt_tokens = 175
        mock_resp.usage.completion_tokens = 80
        mock_resp.model = "moonshotai/kimi-k2-0905"

        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = mock_resp
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

        result = client.complete("sys", "user")
        assert result.text == "openrouter response"
        assert result.input_tokens == 175
        assert result.output_tokens == 80
        assert result.model == "moonshotai/kimi-k2-0905"

        # Verify the API was called with the stripped model name
        called_kwargs = mock_inner.chat.completions.create.call_args.kwargs
        assert called_kwargs["model"] == "moonshotai/kimi-k2-0905"
        assert called_kwargs["messages"][0]["role"] == "system"
        assert called_kwargs["messages"][0]["content"] == "sys"
        assert called_kwargs["messages"][1]["role"] == "user"
        assert called_kwargs["messages"][1]["content"] == "user"

    def test_complete_empty_choices_raises(self, monkeypatch):
        """I3 (PR #70): empty `choices` is API-side failure, not the
        model's fault. Must raise rather than return text="" — silent
        empty-string return was getting blamed on the model as "did not
        define entry point" in JSONL output."""
        try:
            import openai  # noqa: F401

            from vera_bench.models import OpenRouterClient
        except ImportError:
            pytest.skip("openai not installed")

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        client = OpenRouterClient("or/test/model")

        mock_resp = MagicMock()
        mock_resp.choices = []
        mock_resp.usage = None
        mock_resp.model = "test/model"

        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = mock_resp
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

        with pytest.raises(RuntimeError, match="returned no choices"):
            client.complete("sys", "user")

    def test_complete_empty_content_raises(self, monkeypatch):
        """I3: choice exists but content is None (content-filter,
        tool-call-only, etc.) — surface as RuntimeError with finish_reason
        rather than silently text=""."""
        try:
            import openai  # noqa: F401

            from vera_bench.models import OpenRouterClient
        except ImportError:
            pytest.skip("openai not installed")

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        client = OpenRouterClient("or/test/model")

        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_choice.finish_reason = "content_filter"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.model = "test/model"

        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = mock_resp
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

        with pytest.raises(RuntimeError, match="empty content.*content_filter"):
            client.complete("sys", "user")

    def test_complete_api_timeout(self, monkeypatch):
        """OpenRouter timeout propagates as TimeoutError."""
        try:
            import openai

            from vera_bench.models import OpenRouterClient
        except ImportError:
            pytest.skip("openai not installed")

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        client = OpenRouterClient("or/test/model")

        mock_inner = MagicMock()
        mock_inner.chat.completions.create.side_effect = openai.APITimeoutError(
            request=MagicMock()
        )
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

        with pytest.raises(TimeoutError, match="OpenRouter API timed out"):
            client.complete("sys", "user")

    def test_complete_authentication_error_aborts(self, monkeypatch):
        """I3: AuthenticationError must raise EnvironmentError so the
        caller aborts the run — retrying 60 problems with a bad key is
        pure token waste."""
        try:
            import openai

            from vera_bench.models import OpenRouterClient
        except ImportError:
            pytest.skip("openai not installed")

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        client = OpenRouterClient("or/test/model")

        mock_inner = MagicMock()
        mock_inner.chat.completions.create.side_effect = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(),
            body=None,
        )
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

        with pytest.raises(EnvironmentError, match="OpenRouter authentication"):
            client.complete("sys", "user")

    def test_complete_rate_limit_error(self, monkeypatch):
        """I3: RateLimitError surfaces with a clear "slow the sweep"
        message rather than the raw openai repr."""
        try:
            import openai

            from vera_bench.models import OpenRouterClient
        except ImportError:
            pytest.skip("openai not installed")

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        client = OpenRouterClient("or/test/model")

        mock_inner = MagicMock()
        mock_inner.chat.completions.create.side_effect = openai.RateLimitError(
            message="Rate limit hit",
            response=MagicMock(),
            body=None,
        )
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

        with pytest.raises(RuntimeError, match="rate-limited"):
            client.complete("sys", "user")


class TestCachedTokensHelpers:
    """Unit tests for the #61 cache-accounting helpers."""

    def test_openai_cached_tokens_real_int(self):
        from vera_bench.models import _openai_cached_tokens

        usage = MagicMock()
        usage.prompt_tokens_details.cached_tokens = 27000
        assert _openai_cached_tokens(usage) == 27000

    def test_openai_cached_tokens_rejects_bool(self):
        """bool is an int subclass — a provider quirk returning True
        must not count as 1 cached token (type() check, not
        isinstance)."""
        from vera_bench.models import _openai_cached_tokens

        usage = MagicMock()
        usage.prompt_tokens_details.cached_tokens = True
        assert _openai_cached_tokens(usage) == 0

    def test_openai_cached_tokens_absent_details(self):
        from vera_bench.models import _openai_cached_tokens

        assert _openai_cached_tokens(object()) == 0

    def test_openai_cached_tokens_none_details(self):
        from vera_bench.models import _openai_cached_tokens

        usage = MagicMock()
        usage.prompt_tokens_details = None
        assert _openai_cached_tokens(usage) == 0

    def test_openai_cached_tokens_magicmock_leak_guard(self):
        from vera_bench.models import _openai_cached_tokens

        # A bare MagicMock auto-creates attributes — the isinstance
        # guard must refuse the non-int and report 0, never leak a
        # mock object into token accounting.
        assert _openai_cached_tokens(MagicMock()) == 0

    def test_prompt_cache_key_stable_and_distinct(self):
        from vera_bench.models import _prompt_cache_key

        k1 = _prompt_cache_key("prefix A")
        assert k1 == _prompt_cache_key("prefix A")
        assert k1 != _prompt_cache_key("prefix B")
        assert k1.startswith("vera-bench-")


class TestOpenAICachingAndHardening:
    """#61: cache instrumentation + OpenRouter-standard error handling."""

    def _client(self, monkeypatch: pytest.MonkeyPatch) -> object:
        try:
            from vera_bench.models import OpenAIClient
        except ImportError:
            pytest.skip("openai not installed")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        return OpenAIClient("gpt-test")

    def _wire(self, client: object, mock_inner: MagicMock) -> None:
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

    def _ok_response(self, cached: int = 0) -> MagicMock:
        resp = MagicMock()
        choice = MagicMock()
        choice.message.content = "hello"
        resp.choices = [choice]
        resp.model = "gpt-test"
        resp.usage.prompt_tokens = 30000
        resp.usage.completion_tokens = 50
        resp.usage.prompt_tokens_details.cached_tokens = cached
        return resp

    def test_cached_tokens_flow_into_response(self, monkeypatch):
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = self._ok_response(
            cached=28000
        )
        self._wire(client, mock_inner)
        result = client.complete("sys", "user")
        assert result.cached_tokens == 28000
        assert result.input_tokens == 30000

    def test_prompt_cache_key_sent_via_extra_body(self, monkeypatch):
        from vera_bench.models import _prompt_cache_key

        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = self._ok_response()
        self._wire(client, mock_inner)
        client.complete("the system prefix", "user")
        kwargs = mock_inner.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == {
            "prompt_cache_key": _prompt_cache_key("the system prefix")
        }

    def test_authentication_error_aborts(self, monkeypatch):
        try:
            import openai
        except ImportError:
            pytest.skip("openai not installed")
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.side_effect = openai.AuthenticationError(
            message="Invalid API key", response=MagicMock(), body=None
        )
        self._wire(client, mock_inner)
        with pytest.raises(EnvironmentError, match="OpenAI authentication"):
            client.complete("sys", "user")

    def test_empty_choices_raises(self, monkeypatch):
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        resp = MagicMock()
        resp.choices = []
        mock_inner.chat.completions.create.return_value = resp
        self._wire(client, mock_inner)
        with pytest.raises(RuntimeError, match="no choices"):
            client.complete("sys", "user")

    def test_empty_content_raises(self, monkeypatch):
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        resp = MagicMock()
        choice = MagicMock()
        choice.message.content = None
        choice.finish_reason = "content_filter"
        resp.choices = [choice]
        mock_inner.chat.completions.create.return_value = resp
        self._wire(client, mock_inner)
        with pytest.raises(RuntimeError, match="empty content"):
            client.complete("sys", "user")


class TestMoonshotCachingAndHardening:
    """#61: Moonshot caching is automatic — accounting + hardening only."""

    def _client(self, monkeypatch: pytest.MonkeyPatch) -> object:
        try:
            from vera_bench.models import MoonshotClient
        except ImportError:
            pytest.skip("openai not installed")
        monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
        return MoonshotClient("moonshot/kimi-test")

    def _wire(self, client: object, mock_inner: MagicMock) -> None:
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

    def test_no_cache_param_sent(self, monkeypatch):
        """Moonshot's Context Caching is fully automatic — the request
        must NOT carry an extra_body cache key (their API, their
        routing)."""
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        resp = MagicMock()
        choice = MagicMock()
        choice.message.content = "hi"
        resp.choices = [choice]
        resp.model = "kimi-test"
        resp.usage.prompt_tokens = 100
        resp.usage.completion_tokens = 10
        resp.usage.prompt_tokens_details.cached_tokens = 64
        mock_inner.chat.completions.create.return_value = resp
        self._wire(client, mock_inner)
        result = client.complete("sys", "user")
        kwargs = mock_inner.chat.completions.create.call_args.kwargs
        assert "extra_body" not in kwargs
        assert result.cached_tokens == 64

    def test_authentication_error_aborts(self, monkeypatch):
        try:
            import openai
        except ImportError:
            pytest.skip("openai not installed")
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.side_effect = openai.AuthenticationError(
            message="Invalid API key", response=MagicMock(), body=None
        )
        self._wire(client, mock_inner)
        with pytest.raises(EnvironmentError, match="Moonshot authentication"):
            client.complete("sys", "user")

    def test_empty_content_raises(self, monkeypatch):
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        resp = MagicMock()
        choice = MagicMock()
        choice.message.content = None
        choice.finish_reason = "length"
        resp.choices = [choice]
        mock_inner.chat.completions.create.return_value = resp
        self._wire(client, mock_inner)
        with pytest.raises(RuntimeError, match="empty content"):
            client.complete("sys", "user")


class TestOpenAIProRouting:
    """Sol@pro (openai-pro/ prefix) — the controlled reasoning-budget
    comparison entry. Same model id, distinct mode, distinct results."""

    def _client(
        self,
        monkeypatch: pytest.MonkeyPatch,
        model: str = "openai-pro/gpt-5.6-sol",
    ) -> object:
        try:
            from vera_bench.models import create_client
        except ImportError:
            pytest.skip("openai not installed")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        return create_client(model)

    def _ok_response(self) -> MagicMock:
        resp = MagicMock()
        choice = MagicMock()
        choice.message.content = "code"
        resp.choices = [choice]
        resp.model = "gpt-5.6-sol"
        resp.usage.prompt_tokens = 100
        resp.usage.completion_tokens = 5000
        resp.usage.prompt_tokens_details.cached_tokens = 0
        return resp

    def _wire(self, client: object, mock_inner: MagicMock) -> None:
        client._client = MagicMock()
        client._client.with_options.return_value = mock_inner

    def test_routing_strips_prefix_and_sets_mode(self, monkeypatch):
        from vera_bench.models import OpenAIClient

        client = self._client(monkeypatch)
        assert isinstance(client, OpenAIClient)
        assert client._model == "gpt-5.6-sol"
        assert client._reasoning_mode == "pro"

    def test_default_openai_has_no_reasoning_mode(self, monkeypatch):
        client = self._client(monkeypatch, model="gpt-5.6-sol")
        assert client._reasoning_mode is None

    def test_unknown_prefix_still_rejected(self, monkeypatch):
        from vera_bench.models import create_client

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with pytest.raises(ValueError, match="Unknown model"):
            create_client("mystery/some-model")

    def test_pro_sends_reasoning_effort_kwarg(self, monkeypatch):
        """Chat Completions takes `reasoning_effort`, not a nested
        `reasoning` object — the latter is the Responses-API shape and
        is rejected with 400 "Unknown parameter: 'reasoning'" (smoke
        S2, 2026-07-23). "pro" is our name; the API ceiling is "max"."""
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = self._ok_response()
        self._wire(client, mock_inner)
        client.complete("sys", "user")
        kwargs = mock_inner.chat.completions.create.call_args.kwargs
        assert kwargs["reasoning_effort"] == "max"
        assert "reasoning" not in kwargs
        assert "reasoning" not in kwargs["extra_body"]
        # Cache key still rides alongside (#61)
        assert "prompt_cache_key" in kwargs["extra_body"]

    def test_default_mode_sends_no_reasoning(self, monkeypatch):
        client = self._client(monkeypatch, model="gpt-5.6-sol")
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = self._ok_response()
        self._wire(client, mock_inner)
        client.complete("sys", "user")
        kwargs = mock_inner.chat.completions.create.call_args.kwargs
        assert "reasoning_effort" not in kwargs
        assert "reasoning" not in kwargs["extra_body"]

    def test_reasoning_effort_is_a_value_the_api_accepts(self, monkeypatch):
        """Guard against inventing a value the SDK's Literal rejects."""
        from typing import get_args

        from openai.types.shared.reasoning_effort import ReasoningEffort

        from vera_bench.models import REASONING_MODE_EFFORT

        valid = {v for v in get_args(get_args(ReasoningEffort)[0]) if v}
        assert set(REASONING_MODE_EFFORT.values()) <= valid

    def test_unmapped_reasoning_mode_raises(self, monkeypatch):
        """Silently dropping the parameter would make the 'pro' entry run
        at default effort — a comparison of a model against itself."""
        from vera_bench.models import OpenAIClient

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with pytest.raises(ValueError, match="Unknown reasoning mode"):
            OpenAIClient("gpt-5.6-sol", reasoning_mode="ultra")

    def test_max_completion_tokens_sent_not_max_tokens(self, monkeypatch):
        """GPT-5.x reasoning families reject the legacy max_tokens kwarg."""
        client = self._client(monkeypatch, model="gpt-5.6-sol")
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = self._ok_response()
        self._wire(client, mock_inner)
        client.complete("sys", "user", max_tokens=4096)
        kwargs = mock_inner.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 4096
        assert "max_tokens" not in kwargs

    def test_pro_mode_floors_completion_budget(self, monkeypatch):
        """Reasoning eats completion budget — pro floors to 16000 so
        deliberation can't starve the output (validated live in S2)."""
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = self._ok_response()
        self._wire(client, mock_inner)
        client.complete("sys", "user", max_tokens=4096)
        kwargs = mock_inner.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 16000

    def test_pro_response_model_gets_mode_suffix(self, monkeypatch):
        """Both Sol variants report the same API id — the suffix makes
        JSONL rows self-describing."""
        client = self._client(monkeypatch)
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = self._ok_response()
        self._wire(client, mock_inner)
        result = client.complete("sys", "user")
        assert result.model == "gpt-5.6-sol#pro"

    def test_default_response_model_unsuffixed(self, monkeypatch):
        client = self._client(monkeypatch, model="gpt-5.6-sol")
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = self._ok_response()
        self._wire(client, mock_inner)
        result = client.complete("sys", "user")
        assert result.model == "gpt-5.6-sol"

    def test_bare_openai_pro_prefix_rejected(self, monkeypatch):
        from vera_bench.models import create_client

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with pytest.raises(ValueError, match="requires a model id"):
            create_client("openai-pro/")
