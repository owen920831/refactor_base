"""Tests for LLM client."""

import pytest

from mvp_agent.llm_client import LLMClient, LLMConfig, LLMResponse


class TestLLMConfig:
    """Tests for LLMConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = LLMConfig()
        assert config.model == "gpt-oss:120b"
        assert config.base_url == "http://localhost:11434"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = LLMConfig(
            model="gpt-oss:120b",
            temperature=0.5,
        )
        assert config.model == "gpt-oss:120b"
        assert config.temperature == 0.5


class TestLLMResponse:
    """Tests for LLMResponse."""

    def test_response_creation(self) -> None:
        """Test response creation."""
        response = LLMResponse(
            content="Hello",
            model="test",
            total_tokens=10,
        )
        assert response.content == "Hello"
        assert response.model == "test"
        assert response.error is None


# Integration tests require Ollama running
@pytest.mark.skip(reason="Requires Ollama server running")
class TestLLMClientIntegration:
    """Integration tests for LLMClient."""

    def test_generate(self) -> None:
        """Test basic generation."""
        client = LLMClient()
        response = client.generate("Say hello")
        assert response.content
        assert response.error is None
