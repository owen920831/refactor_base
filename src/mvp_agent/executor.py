"""Code executor for Python to C++ conversion.

Executes individual tasks from the planner, generating C++ code.
Reference: refact-agent generate_code_edit.rs, tool_subagent.rs
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from mvp_agent.llm_client import LLMClient
from mvp_agent.planner import Task

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "executor.txt"


@dataclass
class ExecutionResult:
    """Result of executing a conversion task."""

    task_id: str
    success: bool
    generated_code: str
    error: str | None = None
    tokens_used: int = 0


class Executor:
    """Executes code conversion tasks.

    Acts as a sub-agent focused on generating C++ code from Python.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize the executor.

        Args:
            llm_client: LLM client for code generation.
        """
        self.llm_client = llm_client
        self._system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """Load the executor system prompt."""
        if PROMPT_PATH.exists():
            return PROMPT_PATH.read_text(encoding="utf-8")
        logger.warning("Executor prompt not found at %s", PROMPT_PATH)
        return "Convert Python code to C++. Return only the C++ code."

    def execute(
        self,
        task: Task,
        source_code: str,
        context: str | None = None,
    ) -> ExecutionResult:
        """Execute a conversion task.

        Args:
            task: The task to execute.
            source_code: Full Python source code.
            context: Optional additional context (previously generated code).

        Returns:
            ExecutionResult with generated code or error.
        """
        # Extract relevant portion if line range specified
        if task.source_lines:
            start, end = task.source_lines
            lines = source_code.split("\n")
            relevant_code = "\n".join(lines[start - 1 : end])
        else:
            relevant_code = source_code

        # Build prompt
        user_prompt = f"""Convert the following Python code to C++.

## Task: {task.name}
{task.description}

## Python Code
```python
{relevant_code}
```
"""

        if context:
            user_prompt += f"""
## Previously Generated Code (for reference)
```cpp
{context}
```
"""

        # Call LLM
        response = self.llm_client.generate_with_retry(
            prompt=user_prompt,
            system_prompt=self._system_prompt,
        )

        if response.error:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                generated_code="",
                error=response.error,
                tokens_used=response.total_tokens,
            )

        # Clean up response
        code = self._clean_code(response.content)

        return ExecutionResult(
            task_id=task.id,
            success=True,
            generated_code=code,
            tokens_used=response.total_tokens,
        )

    def _clean_code(self, content: str) -> str:
        """Remove markdown fences and clean up generated code.

        Args:
            content: Raw LLM response.

        Returns:
            Cleaned C++ code.
        """
        content = content.strip()

        # Remove markdown code fences
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```cpp or ```)
            lines = lines[1:]
            # Remove last line if it's a fence
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)

        return content.strip()

    def fix_error(
        self,
        task: Task,
        generated_code: str,
        error_message: str,
    ) -> ExecutionResult:
        """Attempt to fix compilation/test errors.

        Args:
            task: The task that failed.
            generated_code: The code that failed.
            error_message: The error message from compiler/tests.

        Returns:
            ExecutionResult with fixed code or error.
        """
        user_prompt = f"""The following C++ code has an error. Fix it.

        ## Task: {task.name}

        ## Current Code
        ```cpp
        {generated_code}
        ```

        ## Error
        ```
        {error_message}
        ```

        Return only the fixed C++ code, no explanations.
        """

        response = self.llm_client.generate_with_retry(
            prompt=user_prompt,
            system_prompt=self._system_prompt,
        )

        if response.error:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                generated_code=generated_code,
                error=response.error,
                tokens_used=response.total_tokens,
            )

        code = self._clean_code(response.content)

        return ExecutionResult(
            task_id=task.id,
            success=True,
            generated_code=code,
            tokens_used=response.total_tokens,
        )

    def assemble_code(self, code_chunks: list[str]) -> ExecutionResult:
        """Assemble multiple code chunks into a single valid file.

        Args:
            code_chunks: List of C++ code strings.

        Returns:
            ExecutionResult with merged code.
        """
        combined = "\n\n".join(code_chunks)
        user_prompt = f"""Merge the following C++ code chunks into a single valid source file.

        # Instructions
        1. Consolidate all headers at the top.
        2. Remove duplicate includes.
        3. Merge class definitions if split across chunks (e.g. methods defined outside class).
        4. Ensure correct namespaces.
        5. Remove duplicate helper functions.
        6. Return ONLY the final C++ code.

        # Code Chunks
        ```cpp
        {combined}
        ```
        """

        response = self.llm_client.generate_with_retry(
            prompt=user_prompt,
            system_prompt=self._system_prompt,
        )

        if response.error:
            return ExecutionResult(
                task_id="assembly",
                success=False,
                generated_code="",
                error=response.error,
                tokens_used=response.total_tokens,
            )

        code = self._clean_code(response.content)
        return ExecutionResult(
            task_id="assembly",
            success=True,
            generated_code=code,
            tokens_used=response.total_tokens,
        )
