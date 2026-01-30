"""Ollama LLM client wrapper.

This module provides a client for interacting with the Ollama API.
Supports both streaming and non-streaming generation.

Reference: refact-agent/engine/src architecture.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
import json
import time
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for the LLM client."""

    model: str = "gpt-oss:20b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.7
    max_tokens: int = 16384
    timeout: float = 300.0


@dataclass
class LLMResponse:
    """Response from the LLM."""

    content: str
    model: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    done: bool = True
    error: str | None = None


class LLMClient:
    """Client for Ollama API.

    Attributes:
        config: LLM configuration.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        """Initialize the LLM client.

        Args:
            config: Optional LLM configuration. Uses defaults if not provided.
        """
        self.config = config or LLMConfig()
        self._client = httpx.Client(timeout=self.config.timeout)
        
        # Setup logging directory
        self.log_dir = Path("output/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trace_file = self.log_dir / "llm_trace.jsonl"

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.
            model: Optional model override.
            temperature: Optional temperature override.

        Returns:
            LLMResponse containing the generated content.
        """
        model = model or self.config.model
        temperature = temperature if temperature is not None else self.config.temperature

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        try:
            response = self._client.post(
                f"{self.config.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            response_obj = LLMResponse(
                content=data.get("message", {}).get("content", ""),
                model=data.get("model", model),
                total_tokens=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                done=data.get("done", True),
            )
            
            self._log_trace(prompt, system_prompt, model, payload, response_obj)
            return response_obj
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error from Ollama: %s", e)
            return LLMResponse(content="", model=model, error=str(e))
        except httpx.RequestError as e:
            logger.error("Request error to Ollama: %s", e)
            return LLMResponse(content="", model=model, error=str(e))

    def generate_with_retry(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Generate with automatic retry on failure.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.
            max_retries: Maximum number of retries.

        Returns:
            LLMResponse containing the generated content.
        """
        last_error = None
        for attempt in range(max_retries):
            response = self.generate(prompt, system_prompt)
            if response.error is None and response.content:
                return response
            last_error = response.error
            logger.warning("Attempt %d/%d failed: %s", attempt + 1, max_retries, last_error)

        return LLMResponse(
            content="",
            model=self.config.model,
            error=f"Failed after {max_retries} attempts: {last_error}",
        )

    def _log_trace(
        self, 
        prompt: str, 
        system_prompt: str | None, 
        model: str, 
        payload: dict[str, Any], 
        response: LLMResponse
    ) -> None:
        """Log the LLM call trace to a JSONL file."""
        log_entry = {
            "timestamp": time.time(),
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": prompt,
            "full_messages": payload.get("messages", []),
            "response_content": response.content,
            "tokens": {
                "prompt": response.prompt_tokens,
                "completion": response.completion_tokens,
                "total": response.total_tokens
            },
            "error": response.error
        }
        
        try:
            with open(self.trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("Failed to write LLM trace: %s", e)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> LLMClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
