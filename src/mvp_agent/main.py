"""Main entry point for MVP Refactoring Agent.

Usage:
    uv run python -m mvp_agent.main "Convert Python to C++" --source <file_or_dir>
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime

from mvp_agent.core.baseline import BaselineVerifier
from mvp_agent.agents.executor import Executor
from mvp_agent.core.git_manager import GitManager
from mvp_agent.core.llm_client import LLMClient, LLMConfig
from mvp_agent.agents.planner import Planner
from mvp_agent.reporter import Reporter
from mvp_agent.agents.test_generator import TestGenerator
from mvp_agent.core.verifier import Verifier
from mvp_agent.cognition.scanner import RepoScanner
from mvp_agent.cognition.graph import DependencyGraph
from mvp_agent.cognition.retrieval import ContextManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MAX_RETRIES = 3

from mvp_agent.agents.cmake_gen import CMakeGenerator

class AgentContext:
    """Holds shared components for the agent run."""
    def __init__(self, model: str, output_dir: Path, logs_dir: Path):
        self.llm_config = LLMConfig(model=model)
        self.embedding_model = "llama3:latest"  # Use a stable model for embeddings
        self.llm_client = LLMClient(self.llm_config, log_dir=logs_dir)
        self.planner = Planner(self.llm_client)
        self.executor = Executor(self.llm_client)
        self.cmake_gen = CMakeGenerator(self.llm_client)
        self.test_gen = TestGenerator(self.llm_client)
        self.verifier = Verifier()
        self.reporter = Reporter(output_dir, logs_dir)
        self.git_manager = None

    def setup_git(self, use_git: bool):
        if use_git:
            try:
                self.git_manager = GitManager(self.reporter.output_dir)
                branch = self.git_manager.create_branch()
                logger.info("Working on git branch: %s", branch)
            except Exception as e:
                logger.warning("Git setup failed, continuing without git: %s", e)
                self.git_manager = None

def process_single_file(
    ctx: AgentContext,
    source_path: Path,
    prompt: str,
    context_manager: ContextManager | None = None,
    skip_baseline: bool = False,
    is_repo_mode: bool = False,
    root_path: Path | None = None
) -> bool:
    """Process a single file refactoring task."""
    
    logger.info(f"Processing file: {source_path}")
    
    # Calculate relative path if in repo mode
    rel_path = source_path.relative_to(root_path) if root_path else Path(source_path.name)
    target_dir = ctx.reporter.final_dir / rel_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Create report object
    report = ctx.reporter.create_run_report(
        model=ctx.llm_config.model,
        source_file=str(source_path),
        target_language="C++",
    )
    
    source_code = source_path.read_text(encoding="utf-8")
    
    # Retrieve Dependency Context
    dependency_context = ""
    if context_manager:
        dependency_context = context_manager.retrieve_context_for_task(source_path, source_code)
        if dependency_context:
            logger.info("Retrieved dependency context (%d chars)", len(dependency_context))

    # Phase 0: Baseline Verification
    if not skip_baseline:
        logger.info("[Phase 0] Running baseline verification...")
        baseline_verifier = BaselineVerifier(ctx.llm_client, ctx.reporter.intermediate_dir)
        baseline_success = baseline_verifier.verify(source_path)
        if not baseline_success:
            logger.error(f"Baseline verification FAILED for {source_path.name}")
            return False

    # Phase 1: Planning
    logger.info(f"[Phase 1] Planning for {source_path.name}...")
    plan = ctx.planner.create_plan(source_path, target_language="C++")
    if not plan.tasks:
        logger.error("No tasks generated.")
        return False
    
    # Phase 2: Execution Loop
    logger.info(f"[Phase 2] Executing {len(plan.tasks)} tasks...")
    all_generated_code = {}
    
    while True:
        task = ctx.planner.get_next_task(plan)
        if task is None:
            break
            
        task.status = "running"
        task_start = time.time()
        
        # Inject Dependency Context into Execution
        combined_context = []
        if dependency_context:
            combined_context.append(dependency_context)
        if all_generated_code:
            combined_context.append("\n".join(all_generated_code.values()))
        
        execution_context = "\n\n".join(combined_context) if combined_context else None
        
        result = ctx.executor.execute(task, source_code, execution_context)
        
        if not result.success:
            task.status = "failed"
            task.error = result.error
            logger.error(f"Task {task.name} failed: {result.error}")
            continue

        task.status = "success"
        all_generated_code[task.id] = result.generated_code
        
        # Save intermediate
        outfile = ctx.reporter.intermediate_dir / f"{task.name}.cpp"
        outfile.write_text(result.generated_code, encoding="utf-8")
        
        if ctx.git_manager:
            ctx.git_manager.commit(f"feat({source_path.stem}): {task.name}")

    # Phase 3: Assembly & Final Output
    logger.info("[Phase 3] Assembly & Splitting...")
    if all_generated_code:
        assembly_result = ctx.executor.assemble_code(list(all_generated_code.values()))
        
        # Split into Header/Source
        split_result = ctx.executor.separate_header_source(assembly_result.generated_code, source_path.stem)
        
        # Handle multiple files from split if present
        if split_result.files:
            for filename, content in split_result.files.items():
                final_file = target_dir / filename
                final_file.write_text(content, encoding="utf-8")
                logger.info(f"Saved {filename} to {final_file}")
                
                # Register interface (headers) for dependents
                if context_manager and (filename.endswith('.hpp') or filename.endswith('.h')):
                    context_manager.register_interface(source_path, content)
        else:
            final_code = assembly_result.generated_code
            final_file = target_dir / f"{source_path.stem}.cpp"
            final_file.write_text(final_code, encoding="utf-8")
            logger.info(f"Saved final code to {final_file}")
            
            if context_manager:
                context_manager.register_interface(source_path, final_code)

        # Generate Tests (simplified, usually maps to one test file)
        test_res = ctx.test_gen.generate(assembly_result.generated_code, original_python=source_code)
        if test_res.success:
            test_file = target_dir / f"test_{source_path.stem}.cpp"
            test_file.write_text(test_res.test_code)

    return True

def run_repo(ctx: AgentContext, root_path: Path, prompt: str, skip_baseline: bool):
    # """Orchestrate repository refactoring."""
    logger.info(f"Scanning repository: {root_path}")
    scanner = RepoScanner(root_path)
    files = scanner.scan()
    
    # Parse all files
    parsed_files = [scanner.parse_file(f) for f in files]
    
    # Build Graph
    graph = DependencyGraph(root_path)
    graph.build(parsed_files)
    
    sorted_files = graph.get_topological_sort()
    logger.info(f"Refactoring Order: {[f.name for f in sorted_files]}")
    
    ctx_manager = ContextManager(root_path, graph, ctx.llm_client, embedding_model=ctx.embedding_model)
    
    success_count = 0
    for file_path in sorted_files:
        logger.info(f"--- Processing {file_path.name} ---")
        if process_single_file(ctx, file_path, prompt, ctx_manager, skip_baseline, is_repo_mode=True, root_path=root_path):
            success_count += 1
        else:
            logger.error(f"Failed to process {file_path.name}")
            
    logger.info(f"Repository refactoring complete. {success_count}/{len(sorted_files)} files processed.")
    
    # Generate CMakeLists.txt
    logger.info("Generating CMake distribution...")
    final_files = []
    for root, _, current_files in os.walk(ctx.reporter.final_dir):
        for f in current_files:
            p = Path(root) / f
            final_files.append(p.relative_to(ctx.reporter.final_dir))
    
    if final_files:
        ctx.cmake_gen.generate_root_cmake(ctx.reporter.final_dir, final_files)
    else:
        logger.warning("No files found in final dir, skipping CMake generation.")

def main():
    parser = argparse.ArgumentParser(description="MVP Refactoring Agent")
    parser.add_argument("prompt", nargs="?", default="Convert to C++")
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--logs", default=None)
    parser.add_argument("--model", default="gpt-oss:20b")
    parser.add_argument("--no-git", action="store_true")
    parser.add_argument("--skip-baseline", action="store_true")
    
    args = parser.parse_args()
    
    source_path = Path(args.source).resolve()
    
    # Setup Run Environment
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = Path("runs") / run_id
    output_dir = Path(args.output) if args.output else run_root / "output"
    logs_dir = Path(args.logs) if args.logs else run_root / "logs"
    
    ctx = AgentContext(args.model, output_dir, logs_dir)
    ctx.setup_git(not args.no_git)
    
    if source_path.is_dir():
        run_repo(ctx, source_path, args.prompt, args.skip_baseline)
    else:
        process_single_file(ctx, source_path, args.prompt, None, args.skip_baseline)

if __name__ == "__main__":
    main()
