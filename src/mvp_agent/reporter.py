"""Report generator for refactoring results.

Generates REFACTOR_REPORT.md and JSON logs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from mvp_agent.agents.planner import Task

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Result of a single task."""

    task_id: str
    name: str
    status: str
    duration_s: float = 0.0
    retries: int = 0
    error: str | None = None
    generated_file: str | None = None


@dataclass
class RunReport:
    """Complete run report."""

    run_id: str
    model: str
    source_file: str
    target_language: str
    start_time: str
    end_time: str | None = None
    total_tokens: int = 0
    tasks: list[TaskResult] = field(default_factory=list)
    final_status: str = "pending"  # "success", "partial_success", "failed"
    generated_files: list[str] = field(default_factory=list)


class Reporter:
    """Generates reports and logs for refactoring runs.

    Creates both human-readable markdown reports and JSON logs.
    """

    def __init__(self, output_dir: str | Path, logs_dir: str | Path) -> None:
        """Initialize the reporter.

        Args:
            output_dir: Directory for generated code output.
            logs_dir: Directory for JSON logs.
        """
        self.output_dir = Path(output_dir)
        self.logs_dir = Path(logs_dir)

        self.final_dir = self.output_dir / "final"
        self.intermediate_dir = self.output_dir / "intermediate"

        self.final_dir.mkdir(parents=True, exist_ok=True)
        self.intermediate_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def create_run_report(
        self,
        model: str,
        source_file: str,
        target_language: str,
    ) -> RunReport:
        """Create a new run report.

        Args:
            model: LLM model used.
            source_file: Source file being converted.
            target_language: Target language.

        Returns:
            New RunReport instance.
        """
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        return RunReport(
            run_id=run_id,
            model=model,
            source_file=source_file,
            target_language=target_language,
            start_time=datetime.now().isoformat(),
        )

    def add_task_result(
        self,
        report: RunReport,
        task: Task,
        duration_s: float,
        generated_file: str | None = None,
    ) -> None:
        """Add a task result to the report.

        Args:
            report: The run report.
            task: The completed task.
            duration_s: Task duration in seconds.
            generated_file: Optional generated file path.
        """
        result = TaskResult(
            task_id=task.id,
            name=task.name,
            status=task.status,
            duration_s=duration_s,
            retries=task.retries,
            error=task.error,
            generated_file=generated_file,
        )
        report.tasks.append(result)

        if generated_file:
            report.generated_files.append(generated_file)

    def finalize_report(self, report: RunReport) -> None:
        """Finalize the run report.

        Args:
            report: The run report to finalize.
        """
        report.end_time = datetime.now().isoformat()

        success_count = sum(1 for t in report.tasks if t.status == "success")
        total_count = len(report.tasks)

        if success_count == total_count:
            report.final_status = "success"
        elif success_count > 0:
            report.final_status = "partial_success"
        else:
            report.final_status = "failed"

    def save_json_log(self, report: RunReport) -> Path:
        """Save the run report as JSON log.

        Args:
            report: The run report.

        Returns:
            Path to the saved log file.
        """
        log_path = self.logs_dir / f"run_{report.run_id}.json"

        # Convert to dict, handling dataclasses
        data = asdict(report)

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("Saved JSON log to %s", log_path)
        return log_path

    def generate_markdown_report(self, report: RunReport) -> str:
        """Generate markdown report content.

        Args:
            report: The run report.

        Returns:
            Markdown formatted report.
        """
        lines = [
            "# Refactoring Report",
            "",
            f"**Run ID**: {report.run_id}",
            f"**Model**: {report.model}",
            f"**Source**: {report.source_file}",
            f"**Target**: {report.target_language}",
            f"**Status**: {report.final_status.upper()}",
            "",
            "## Summary",
            "",
        ]

        success_count = sum(1 for t in report.tasks if t.status == "success")
        failed_count = sum(1 for t in report.tasks if t.status == "failed")
        skipped_count = sum(1 for t in report.tasks if t.status == "skipped")

        lines.extend([
            f"- **Total Tasks**: {len(report.tasks)}",
            f"- **Successful**: {success_count}",
            f"- **Failed**: {failed_count}",
            f"- **Skipped**: {skipped_count}",
            f"- **Total Tokens**: {report.total_tokens}",
            "",
            "## Tasks",
            "",
        ])

        for task in report.tasks:
            status_emoji = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(
                task.status, "⏳"
            )
            lines.append(f"### {status_emoji} {task.name}")
            lines.append(f"- Status: {task.status}")
            lines.append(f"- Duration: {task.duration_s:.2f}s")
            if task.retries > 0:
                lines.append(f"- Retries: {task.retries}")
            if task.error:
                lines.append(f"- Error: `{task.error[:200]}`")
            if task.generated_file:
                lines.append(f"- Output: `{task.generated_file}`")
            lines.append("")

        if report.generated_files:
            lines.extend([
                "## Generated Files",
                "",
            ])
            for f in report.generated_files:
                lines.append(f"- `{f}`")
            lines.append("")

        lines.extend([
            "---",
            f"*Generated at {report.end_time}*",
        ])

        return "\n".join(lines)

    def save_markdown_report(self, report: RunReport) -> Path:
        """Save the markdown report.

        Args:
            report: The run report.

        Returns:
            Path to the saved report.
        """
        report_path = self.final_dir / "REFACTOR_REPORT.md"
        content = self.generate_markdown_report(report)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Saved markdown report to %s", report_path)
        return report_path
