
import logging
from pathlib import Path
from typing import List, Optional, Dict

from mvp_agent.core.schemas import TaskDAG, TaskNode
from mvp_agent.core.llm_client import LLMClient
from mvp_agent.core.git_manager import GitManager
from mvp_agent.core.validator import ResultValidator
from mvp_agent.core.adapters import BuildAdapter, TestAdapter
from mvp_agent.cognition.scanner import RepoScanner
from mvp_agent.cognition.graph import DependencyGraph
from mvp_agent.cognition.context_packer import ContextPacker, RepoMapGenerator
from mvp_agent.cognition.retrieval import ContextManager
from mvp_agent.agents.planner import Planner
from mvp_agent.agents.executor import Executor

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    The Brain of the Refactoring Agent.
    Coordinates Scan -> Plan -> Execute -> Verify loop.
    """
    def __init__(self, root_path: Path):
        self.root = root_path
        self.llm_client = LLMClient()
        self.git = GitManager(root_path)
        self.validator = ResultValidator()
        self.scanner = RepoScanner(root_path)
        self.graph = DependencyGraph(root_path)
        
        # Will be initialized after scan
        self.context_manager: Optional[ContextManager] = None
        self.packer: Optional[ContextPacker] = None
        self.planner = Planner(self.llm_client)
        self.executor = Executor(self.llm_client)

    def run(self, build_adapter: Optional[BuildAdapter] = None, test_adapter: Optional[TestAdapter] = None):
        """
        Execute the full refactoring workflow.
        """
        logger.info("Starting Refactoring Orchestration...")
        
        # 1. Scan & Index
        files = self.scanner.scan()
        parsed_files = [self.scanner.parse_file(f) for f in files]
        self.graph.build(parsed_files)
        
        # Initialize Context Components
        self.context_manager = ContextManager(self.root, self.graph, self.llm_client)
        # Populate RAG (Naive all-in-one for MVP, later incremental)
        # Ideally we only ingest relevant files or pack on demand.
        
        repo_gen = RepoMapGenerator(self.graph)
        repomap = repo_gen.generate()
        self.packer = ContextPacker()

        # 2. Plan (Global Analysis)
        # For MVP, we plan for a specific target file or "all python files".
        # Let's assume we pick the main entry point or a passed target. 
        # For this logic, let's find 'main.py' or just plan for the whole repo?
        # Planner.create_plan takes a file.
        # Let's iterate topological sort to process independent files first?
        # OR ask Planner to plan for the whole repo? Current Planner is per-file.
        # Strategy: Refactor bottom-up (leaves first).
        
        sorted_files = self.graph.get_topological_sort()
        logger.info(f"Processing order: {[f.name for f in sorted_files]}")
        
        for file_path in sorted_files:
            if file_path.suffix != ".py": continue
            
            logger.info(f"Planning for {file_path.name}")
            dag = self.planner.create_plan(file_path)
            
            self._execute_dag(dag, file_path, build_adapter, test_adapter)

    def _execute_dag(self, dag: TaskDAG, target_file: Path, build_adapter, test_adapter):
        """
        Execute a TaskDAG for a specific file with rollback protection.
        """
        completed = set()
        
        while True:
            runnable_tasks = self.planner.get_next_tasks(dag, completed)
            if not runnable_tasks:
                break
                
            # Naive: Pick first runnable (Sequential execution for now)
            task = runnable_tasks[0]
            logger.info(f"Executing Task: {task.id} - {task.description}")
            
            # Checkpoint
            ckpt_label = f"pre_{task.id}"
            self.git.create_checkpoint(ckpt_label)
            
            # Prepare Context
            # Simple RAG/Context packing for the task
            # TODO: Integrate ContextPacker fully here with specific query
            
            # Execute
            success = self.executor.execute_task(task, source_code=target_file.read_text())
            
            # Validate
            validation = self.validator.check_syntax(target_file, "python") # or cpp if converted?
            # If target language is C++, check cpp syntax. 
            # Executor modifies file in place? Or writes to new file?
            # MVP Executor writes result. assuming we overwrite source or write target.
            
            if success and validation.valid:
                logger.info(f"Task {task.id} Succeeded.")
                completed.add(task.id)
                self.git.commit(f"Refactor: {task.description} ({task.id})")
            else:
                logger.error(f"Task {task.id} Failed or Invalid. Rolling back.")
                self.git.rollback_to_checkpoint(ckpt_label)
                # Retry logic or abort?
                break
