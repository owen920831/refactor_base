
import pytest
from pathlib import Path
from mvp_agent.cognition.graph import DependencyGraph

def test_dependency_graph_topology():
    root = Path("/tmp/fake_repo")
    graph = DependencyGraph(root)
    
    # Simulate: A.py imports B.py; B.py imports C.py
    # Dependency Chain: A -> B -> C
    # Refactor Order: C, B, A
    
    files_data = [
        {
            "path": root / "A.py",
            "imports": ["B"]
        },
        {
            "path": root / "B.py",
            "imports": ["C"]
        },
        {
            "path": root / "C.py",
            "imports": []
        }
    ]
    
    graph.build(files_data)
    
    sorted_files = graph.get_topological_sort()
    
    assert len(sorted_files) == 3
    
    # Must be C, then B, then A
    assert sorted_files[0].name == "C.py"
    assert sorted_files[1].name == "B.py"
    assert sorted_files[2].name == "A.py"

def test_cycle_detection():
    root = Path("/tmp/fake_repo")
    graph = DependencyGraph(root)
    
    # Loop: A -> B -> A
    files_data = [
        {
            "path": root / "A.py",
            "imports": ["B"]
        },
        {
            "path": root / "B.py",
            "imports": ["A"]
        }
    ]
    
    graph.build(files_data)
    # Should fallback to arbitrary order, not crash
    sorted_files = graph.get_topological_sort()
    assert len(sorted_files) == 2
