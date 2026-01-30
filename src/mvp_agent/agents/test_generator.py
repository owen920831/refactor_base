"""Unit test generator for C++ code.

Generates Google Test unit tests for converted C++ code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from mvp_agent.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "test_gen.txt"


@dataclass
class TestGenerationResult:
    """Result of test generation."""

    success: bool
    test_code: str
    error: str | None = None
    tokens_used: int = 0


class TestGenerator:
    """Generates unit tests for C++ code.

    Uses LLM to create Google Test unit tests.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize the test generator.

        Args:
            llm_client: LLM client for generation.
        """
        self.llm_client = llm_client
        self._system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """Load the test generator system prompt."""
        if PROMPT_PATH.exists():
            return PROMPT_PATH.read_text(encoding="utf-8")
        logger.warning("Test generator prompt not found at %s", PROMPT_PATH)
        return "Generate Google Test unit tests for the C++ code."

    def generate(
        self,
        cpp_code: str,
        class_name: str | None = None,
        original_python: str | None = None,
    ) -> TestGenerationResult:
        """Generate unit tests for C++ code.

        Args:
            cpp_code: The C++ code to test.
            class_name: Optional class name for test naming.
            original_python: Optional original Python for reference.

        Returns:
            TestGenerationResult with test code.
        """
        user_prompt = f"""Generate Google Test unit tests for this C++ code.

## C++ Code to Test
```cpp
{cpp_code}
```
"""

        if original_python:
            user_prompt += f"""
## Original Python (for reference)
```python
{original_python}
```
"""

        if class_name:
            user_prompt += f"\nFocus on testing the {class_name} class."

        response = self.llm_client.generate_with_retry(
            prompt=user_prompt,
            system_prompt=self._system_prompt,
        )

        if response.error:
            return TestGenerationResult(
                success=False,
                test_code="",
                error=response.error,
                tokens_used=response.total_tokens,
            )

        test_code = self._clean_code(response.content)

        return TestGenerationResult(
            success=True,
            test_code=test_code,
            tokens_used=response.total_tokens,
        )

    def _clean_code(self, content: str) -> str:
        """Remove markdown fences from generated code.

        Args:
            content: Raw LLM response.

        Returns:
            Cleaned test code.
        """
        content = content.strip()

        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)

        return content.strip()
