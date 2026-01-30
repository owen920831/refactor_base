"""Main entry point for MVP Refactoring Agent.

Usage:
    uv run python -m mvp_agent.main "Convert Python to C++" --source <file>

The agent runs autonomously after receiving the initial prompt.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from mvp_agent.executor import Executor
from mvp_agent.git_manager import GitManager
from mvp_agent.llm_client import LLMClient, LLMConfig
from mvp_agent.planner import Planner
from mvp_agent.reporter import Reporter
from mvp_agent.test_generator import TestGenerator
from mvp_agent.verifier import Verifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def run_agent(
    prompt: str,
    source_path: str,
    output_dir: str = "./output",
    logs_dir: str = "./logs",
    model: str = "gpt-oss:20b",
    use_git: bool = True,
) -> int:
    """Run the refactoring agent.

    Args:
        prompt: User's task description prompt.
        source_path: Path to Python source file.
        output_dir: Directory for generated code.
        logs_dir: Directory for debug logs.
        model: Ollama model to use.
        use_git: Whether to use git for rollback.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    source_path = Path(source_path).resolve()
    output_dir = Path(output_dir).resolve()
    logs_dir = Path(logs_dir).resolve()

    logger.info("=" * 60)
    logger.info("MVP Refactoring Agent")
    logger.info("=" * 60)
    logger.info("Prompt: %s", prompt)
    logger.info("Source: %s", source_path)
    logger.info("Model: %s", model)
    logger.info("=" * 60)

    # Initialize components
    llm_config = LLMConfig(model=model)
    llm_client = LLMClient(llm_config)

    planner = Planner(llm_client)
    executor = Executor(llm_client)
    test_gen = TestGenerator(llm_client)
    verifier = Verifier()
    reporter = Reporter(output_dir, logs_dir)

    git_manager = None
    if use_git:
        try:
            git_manager = GitManager(output_dir)
            branch = git_manager.create_branch()
            logger.info("Working on git branch: %s", branch)
        except Exception as e:
            logger.warning("Git setup failed, continuing without git: %s", e)
            git_manager = None

    # Create run report
    report = reporter.create_run_report(
        model=model,
        source_file=str(source_path),
        target_language="C++",
    )

    # Read source code
    source_code = source_path.read_text(encoding="utf-8")

    # Phase 1: Planning
    logger.info("[Phase 1] Creating refactoring plan...")
    plan = planner.create_plan(source_path, target_language="C++")
    report.total_tokens += plan.total_tokens

    if not plan.tasks:
        logger.error("Failed to create plan - no tasks generated")
        report.final_status = "failed"
        reporter.save_json_log(report)
        return 1

    logger.info("Generated %d tasks", len(plan.tasks))

    # Phase 2: Execution Loop
    logger.info("[Phase 2] Executing tasks...")
    all_generated_code = {}

    while True:
        task = planner.get_next_task(plan)
        if task is None:
            break

        task.status = "running"
        task_start = time.time()
        logger.info("Executing task: %s (%s)", task.name, task.id)

        # Execute conversion
        context = "\n".join(all_generated_code.values()) if all_generated_code else None
        result = executor.execute(task, source_code, context)
        report.total_tokens += result.tokens_used

        if not result.success:
            task.status = "failed"
            task.error = result.error
            logger.error("Task failed: %s", result.error)
            reporter.add_task_result(report, task, time.time() - task_start)
            continue

        # Verify compilation
        verification = verifier.check_compile(result.generated_code)

        retry_count = 0
        while not verification.compile_success and retry_count < MAX_RETRIES:
            retry_count += 1
            task.retries = retry_count
            logger.warning("Compile failed, retry %d/%d", retry_count, MAX_RETRIES)

            # Try to fix
            fix_result = executor.fix_error(
                task, result.generated_code, verification.compile_error or ""
            )
            report.total_tokens += fix_result.tokens_used

            if fix_result.success:
                result = fix_result
                verification = verifier.check_compile(result.generated_code)

        if not verification.compile_success:
            task.status = "failed"
            task.error = verification.compile_error
            logger.error("Task failed after %d retries", MAX_RETRIES)

            if git_manager:
                git_manager.rollback()

            reporter.add_task_result(report, task, time.time() - task_start)
            continue

        # Success - save code
        task.status = "success"
        all_generated_code[task.id] = result.generated_code

        # Save to file
        output_file = reporter.intermediate_dir / f"{task.name.lower().replace(' ', '_')}.cpp"
        output_file.write_text(result.generated_code, encoding="utf-8")

        if git_manager:
            git_manager.commit(f"feat: {task.name}")

        reporter.add_task_result(
            report, task, time.time() - task_start, str(output_file)
        )
        logger.info("Task completed: %s", task.name)

    # Phase 3: Generate combined output
    logger.info("[Phase 3] Generating final output...")

    if all_generated_code:
        combined_code = "\n\n".join(all_generated_code.values())
        combined_file = reporter.final_dir / f"{source_path.stem}.cpp"
        combined_file.write_text(combined_code, encoding="utf-8")
        report.generated_files.append(str(combined_file))

        # Generate tests
        logger.info("Generating unit tests...")
        test_result = test_gen.generate(combined_code, original_python=source_code)
        report.total_tokens += test_result.tokens_used

        if test_result.success:
            test_file = reporter.final_dir / f"test_{source_path.stem}.cpp"
            test_file.write_text(test_result.test_code, encoding="utf-8")
            report.generated_files.append(str(test_file))
            logger.info("Generated test file: %s", test_file)

    # Phase 4: Generate report
    logger.info("[Phase 4] Generating report...")
    reporter.finalize_report(report)
    reporter.save_json_log(report)
    reporter.save_markdown_report(report)

    logger.info("=" * 60)
    logger.info("Refactoring complete!")
    logger.info("Status: %s", report.final_status)
    logger.info("Report: %s", output_dir / "REFACTOR_REPORT.md")
    logger.info("=" * 60)

    return 0 if report.final_status in ("success", "partial_success") else 1


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MVP Refactoring Agent - Convert Python to C++",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python -m mvp_agent.main --source ./example.py
    uv run python -m mvp_agent.main --source ./example.py --model gpt-oss:20b
        """,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Convert this Python code to C++",
        help="Task description prompt (default: Convert to C++)",
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        help="Path to Python source file",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--logs",
        "-l",
        default="./logs",
        help="Logs directory (default: ./logs)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default="gpt-oss:20b",
        help="Ollama model (default: gpt-oss:20b)",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Disable git integration",
    )

    args = parser.parse_args()

    exit_code = run_agent(
        prompt=args.prompt,
        source_path=args.source,
        output_dir=args.output,
        logs_dir=args.logs,
        model=args.model,
        use_git=not args.no_git,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
