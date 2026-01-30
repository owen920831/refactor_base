
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field

class TaskNode(BaseModel):
    id: str = Field(..., description="Unique task identifier, e.g. 'task_001'")
    description: str = Field(..., description="Detailed description of the task")
    dependencies: List[str] = Field(default_factory=list, description="List of task IDs that must complete before this task")
    files_involved: List[str] = Field(default_factory=list, description="List of file paths involved in this task")
    estimated_cost: int = Field(default=1, description="Complexity/Token cost estimation (1-10)")
    source_lines: Optional[tuple[int, int]] = Field(default=None, description="Start and End lines for this task (1-based)")
    
class TaskDAG(BaseModel):
    tasks: List[TaskNode] = Field(..., description="List of all tasks in the workflow")
    
    def get_task(self, task_id: str) -> Optional[TaskNode]:
        return next((t for t in self.tasks if t.id == task_id), None)
        
    def validate_dag(self) -> bool:
        """
        Check for cycles and valid dependencies.
        Returns True if valid, raises ValueError if invalid.
        """
        # 1. Check dependency existence
        ids = set(t.id for t in self.tasks)
        for t in self.tasks:
            for dep in t.dependencies:
                if dep not in ids:
                    raise ValueError(f"Task {t.id} depends on unknown task {dep}")
        
        # 2. Check for cycles (DFS)
        visited = set()
        recursion_stack = set()
        
        def has_cycle(current_id):
            visited.add(current_id)
            recursion_stack.add(current_id)
            
            node = self.get_task(current_id)
            if node:
                for dep in node.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in recursion_stack:
                        return True
            
            recursion_stack.remove(current_id)
            return False
            
        for t in self.tasks:
            if t.id not in visited:
                if has_cycle(t.id):
                    raise ValueError("Cycle detected in Task Dependency Graph")
        
        return True
