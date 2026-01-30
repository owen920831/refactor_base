"""Strategic planner for refactoring tasks.

Analyzes source code and generates a task queue for conversion.
Reference: refact-agent tool_strategic_planning.rs
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from mvp_agent.cognition.analyzer import Analyzer
from mvp_agent.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "planner.txt"


@dataclass
class Task:
    """A single refactoring task."""

    id: str
    type: str  # "class", "function", "include", "setup"
    name: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    priority: int = 3
    source_lines: tuple[int, int] | None = None
    status: str = "pending"  # "pending", "running", "success", "failed", "skipped"
    retries: int = 0
    error: str | None = None


@dataclass
class Plan:
    """Refactoring plan containing ordered tasks."""

    source_path: str
    target_language: str
    tasks: list[Task] = field(default_factory=list)
    total_tokens: int = 0


class Planner:
    """Generates refactoring plans from source analysis.

    Uses LLM to create a strategic plan for code conversion.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize the planner.

        Args:
            llm_client: LLM client for generation.
        """
        self.llm_client = llm_client
        self.analyzer = Analyzer()
        self._system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """Load the planner system prompt."""
        if PROMPT_PATH.exists():
            return PROMPT_PATH.read_text(encoding="utf-8")
        logger.warning("Planner prompt not found at %s, using default", PROMPT_PATH)
        return "You are a code refactoring planner. Output a JSON array of tasks."

    def create_plan(
        self,
        source_path: str | Path,
        target_language: str = "C++",
    ) -> Plan:
        """Create a refactoring plan for the source file.

        Args:
            source_path: Path to Python source file.
            target_language: Target language for conversion.

        Returns:
            Plan with ordered tasks.
        """
        source_path = Path(source_path)
        source_code = source_path.read_text(encoding="utf-8")

        # Analyze source
        module_info = self.analyzer.analyze_file(source_path)
        summary = self.analyzer.to_summary(module_info)

        # Build prompt
        target = target_language
        user_prompt = f"""Analyze this Python source and create a conversion plan to {target}.

## Source File: {source_path.name}

```python
{source_code}
```

## Analysis Summary
{summary}

Create a detailed task plan for converting this to {target}.
"""

        # Call LLM
        response = self.llm_client.generate_with_retry(
            prompt=user_prompt,
            system_prompt=self._system_prompt,
        )

        if response.error:
            logger.error("Failed to generate plan: %s", response.error)
            return Plan(
                source_path=str(source_path),
                target_language=target_language,
                tasks=[],
            )

        # Parse tasks
        tasks = self._parse_tasks(response.content)

        return Plan(
            source_path=str(source_path),
            target_language=target_language,
            tasks=tasks,
            total_tokens=response.total_tokens,
        )

    def _parse_tasks(self, content: str) -> list[Task]:
        """Parse task list from LLM response.

        Args:
            content: LLM response content.

        Returns:
            List of Task objects.
        """
        # Try to extract JSON from response
        content = content.strip()

        # Remove markdown fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            data = json.loads(content)
            if not isinstance(data, list):
                logger.error("Expected JSON array, got %s", type(data))
                return []

            tasks = []
            for item in data:
                source_lines = None
                if "source_lines" in item and isinstance(item["source_lines"], list):
                    source_lines = tuple(item["source_lines"][:2])

                task = Task(
                    id=item.get("id", f"task_{len(tasks)}"),
                    type=item.get("type", "unknown"),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    dependencies=item.get("dependencies", []),
                    priority=item.get("priority", 3),
                    source_lines=source_lines,
                )
                tasks.append(task)

            # Sort by priority and dependencies
            tasks.sort(key=lambda t: (t.priority, len(t.dependencies)))
            return tasks

        except json.JSONDecodeError as e:
            logger.error("Failed to parse tasks JSON: %s", e)
            logger.debug("Content was: %s", content[:500])
            return []

    def get_next_task(self, plan: Plan) -> Task | None:
        """Get the next runnable task from the plan.

        Args:
            plan: The refactoring plan.

        Returns:
            Next pending task with satisfied dependencies, or None.
        """
        completed_ids = {t.id for t in plan.tasks if t.status in ("success", "skipped")}

        for task in plan.tasks:
            if task.status != "pending":
                continue
            if all(dep in completed_ids for dep in task.dependencies):
                return task

        return None
