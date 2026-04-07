"""Tests for models.py — LLM API abstraction."""

from __future__ import annotations

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
            import anthropic
        except ImportError:
            pytest.skip("anthropic not installed")

        from unittest.mock import MagicMock, patch

        from vera_bench.models import AnthropicClient

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with patch("vera_bench.models.anthropic") as mock_mod:
            # Mock the client
            mock_client = MagicMock()
            mock_mod.Anthropic.return_value = mock_client
            mock_mod.APITimeoutError = anthropic.APITimeoutError

            # Mock response
            mock_resp = MagicMock()
            mock_resp.content = [MagicMock(text="hello")]
            mock_resp.usage.input_tokens = 100
            mock_resp.usage.output_tokens = 50
            mock_resp.model = "claude-test"
            mock_client.messages.create.return_value = mock_resp

            client = AnthropicClient("claude-test")
            result = client.complete("system", "user")
            assert result.text == "hello"
            assert result.input_tokens == 100
            assert result.output_tokens == 50


class TestOpenAIComplete:
    def test_complete_mock(self, monkeypatch):
        """Test OpenAI complete with a mocked SDK."""
        try:
            import openai
        except ImportError:
            pytest.skip("openai not installed")

        from unittest.mock import MagicMock, patch

        from vera_bench.models import OpenAIClient

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        with patch("vera_bench.models.openai") as mock_mod:
            mock_client = MagicMock()
            mock_mod.OpenAI.return_value = mock_client
            mock_mod.APITimeoutError = openai.APITimeoutError

            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = "world"
            mock_resp.choices = [mock_choice]
            mock_resp.usage.prompt_tokens = 200
            mock_resp.usage.completion_tokens = 75
            mock_resp.model = "gpt-test"
            chat = mock_client.with_options.return_value.chat
            chat.completions.create.return_value = mock_resp

            client = OpenAIClient("gpt-test")
            result = client.complete("system", "user")
            assert result.text == "world"
            assert result.input_tokens == 200
            assert result.output_tokens == 75


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
