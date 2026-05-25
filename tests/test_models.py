"""Tests for models.py — LLM API abstraction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vera_bench.models import create_client


class TestCreateClient:
    def test_anthropic(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises((ImportError, EnvironmentError)):
            create_client("claude-sonnet-4-20250514")

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
                AnthropicClient("claude-sonnet-4-20250514")
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


class TestAnthropicComplete:
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
        mock_resp.content = [MagicMock(text="hello")]
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
