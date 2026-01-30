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
from mvp_agent.core.schemas import TaskDAG, TaskNode

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "planner.txt"

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
        return "You are a code refactoring planner. Output a JSON DAG of tasks."

    def create_plan(
        self,
        source_path: str | Path,
        target_language: str = "C++",
    ) -> TaskDAG:
        """Create a refactoring plan for the source file.

        Args:
            source_path: Path to Python source file.
            target_language: Target language for conversion.

        Returns:
            TaskDAG with ordered tasks.
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

Create a detailed task DAG for converting this to {target}.
Output MUST be a valid JSON object matching the TaskDAG schema:
{{
  "tasks": [
    {{
      "id": "task_id",
      "description": "...",
      "dependencies": ["dep_id"],
      "files_involved": ["..."],
      "estimated_cost": 1
    }}
  ]
}}
"""

        # Call LLM
        response = self.llm_client.generate_with_retry(
            prompt=user_prompt,
            system_prompt=self._system_prompt,
        )

        if response.error:
            logger.error("Failed to generate plan: %s", response.error)
            return TaskDAG(tasks=[])

        # Parse tasks
        return self._parse_tasks(response.content)

    def _parse_tasks(self, content: str) -> TaskDAG:
        """Parse task list from LLM response.

        Args:
            content: LLM response content.

        Returns:
            TaskDAG object.
        """
        # Try to extract JSON from response
        content = content.strip()

        # Remove markdown fences if present
        if "```json" in content:
            import re
            match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match:
                content = match.group(1)
            else:
                 # Fallback for simple fence
                 if content.startswith("```"):
                    lines = content.split("\n")
                    content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        elif content.startswith("```"):
             lines = content.split("\n")
             content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            # Use Pydantic parsing
            dag = TaskDAG.model_validate_json(content)
            
            # Validate core logic
            dag.validate_dag()
            
            return dag

        except Exception as e:
            logger.error("Failed to parse tasks JSON: %s", e)
            logger.debug("Content was: %s", content[:500])
            return TaskDAG(tasks=[])

    def get_next_tasks(self, plan: TaskDAG, completed_ids: set[str]) -> list[TaskNode]:
        """Get ALL next runnable tasks (parallel execution support).

        Args:
            plan: The refactoring plan (TaskDAG).
            completed_ids: Set of completed task IDs.

        Returns:
            List of pending tasks with satisfied dependencies.
        """
        runnable = []
        for task in plan.tasks:
            if task.id in completed_ids:
                continue
            
            if all(dep in completed_ids for dep in task.dependencies):
                runnable.append(task)
                
        return runnable
