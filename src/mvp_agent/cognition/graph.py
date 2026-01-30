
import logging
from pathlib import Path
from typing import List, Dict, Set
import networkx as nx

logger = logging.getLogger(__name__)

class DependencyGraph:
    """
    Builds and manages the dependency graph of the repository.
    Nodes are file paths (relative to root).
    Edges (U -> V) mean U depends on V (U imports V).
    """
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.graph = nx.DiGraph()

    def build(self, files_data: List[Dict]):
        """
        Constructs the graph from scanner output.
        
        Args:
            files_data: List of dicts, each containing 'path' and 'imports'.
        """
        # First pass: Add all nodes (files)
        file_map = {}  # Map module name/path to canonical relative path string
        
        for file_info in files_data:
            path: Path = file_info['path']
            rel_path = path.relative_to(self.root_path)
            node_id = str(rel_path)
            
            self.graph.add_node(node_id, file_path=path)
            
            # Populate simple module mapping
            # e.g. "my_module/utils.py" -> "my_module.utils"
            module_name = self._path_to_module(rel_path)
            file_map[module_name] = node_id
            
            # Also map the filename itself as a fallback "utils" -> "my_module/utils.py"
            # (Warning: collisions possible, this is a heuristic)
            file_map[rel_path.stem] = node_id

        # Second pass: Add edges
        for file_info in files_data:
            importer_rel = file_info['path'].relative_to(self.root_path)
            importer_id = str(importer_rel)
            
            for import_name in file_info['imports']:
                # Attempt to resolve import to a file
                # 1. Exact match (e.g. "my_module.utils")
                if import_name in file_map:
                    self.graph.add_edge(importer_id, file_map[import_name])
        
        logger.info(f"Built dependency graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")

    def _path_to_module(self, rel_path: Path) -> str:
        """Converts path to python module notation (a/b.py -> a.b)."""
        parts = list(rel_path.with_suffix('').parts)
        if parts[-1] == '__init__':
            parts.pop()
        return ".".join(parts)

    def get_topological_sort(self) -> List[Path]:
        """
        Returns a list of files in topological order (dependencies first).
        Leaves (no dependencies) come first.
        """
        try:
            # networkx topological_sort returns standard order (U before V if U -> V)
            # But our edges are (Importer -> Imported).
            # We want to process Imported FIRST.
            # So we want the REVERSE of the topological sort.
            # Wait, if A imports B, we have edge A->B.
            # Dependencies are processed *before* dependents.
            # So we need to process B, then A.
            # nx.topological_sort(G) yields nodes in dependency order?
            # Docs: "items are yielded in topological order" -> if u->v, u comes before v.
            # If A -> B (A depends on B), nx gives [A, B].
            # We want to process B (independent) then A.
            # So we need the REVERSE of nx.topological_sort.
            
            ordered_nodes = list(nx.topological_sort(self.graph))
            ordered_nodes.reverse()
            
            sorted_paths = []
            for node_id in ordered_nodes:
                data = self.graph.nodes[node_id]
                sorted_paths.append(data['file_path'])
                
            return sorted_paths
            
        except nx.NetworkXUnfeasible:
            logger.error("Cycle detected in dependency graph! Fallback to arbitrary order.")
            # Fallback: Just return all files
            return [data['file_path'] for _, data in self.graph.nodes(data=True)]

    def to_json(self) -> Dict:
        """
        Export the dependency graph matching the V2 Schema.
        """
        graph_data = {
            "nodes": [],
            "edges": []
        }
        
        # Nodes
        for node in self.graph.nodes():
            # In V2 Spec, ID format is "file:src/main.py"
            # Our internal nodes are just relative paths e.g. "src/main.py"
            v2_id = f"file:{node}"
            graph_data["nodes"].append({
                "id": v2_id,
                "type": "file"
            })
            
        # Edges
        for u, v in self.graph.edges():
            # u imports v
            graph_data["edges"].append({
                "src": f"file:{u}",
                "dst": f"file:{v}",
                "type": "imports"
            })
            
        return graph_data
        
    def get_dependencies(self, file_path: Path) -> List[Path]:
        """Get direct dependencies for a file."""
        try:
            rel = str(file_path.relative_to(self.root_path))
            if rel not in self.graph:
                return []
            # Edges are Importer -> Imported
            # neighbors(Importer) = [Imported1, Imported2]
            deps = []
            for n in self.graph.neighbors(rel):
                deps.append(self.graph.nodes[n]['file_path'])
            return deps
        except ValueError:
            return []
