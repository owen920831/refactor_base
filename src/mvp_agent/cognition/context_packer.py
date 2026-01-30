
import logging
import networkx as nx
from typing import Dict, List, Tuple, Any
from mvp_agent.cognition.graph import DependencyGraph

logger = logging.getLogger(__name__)

class RepoMapGenerator:
    """
    Generates a concise Repository Map, ranked by file importance (centrality).
    Inspired by Aider's RepoMap and PageRank strategies.
    """
    def __init__(self, dependency_graph: DependencyGraph):
        self.dep_graph = dependency_graph
        self.graph = dependency_graph.graph

    def compute_ranking(self) -> List[Tuple[str, float]]:
        """
        Compute file ranking based on graph centrality.
        Returns: List of (node_id, score), sorted by score descending.
        """
        if self.graph.number_of_nodes() == 0:
            return []
            
        # Use Degree Centrality (In-Degree = popularity/importance)
        # Files that are imported by many others are likely "Core" or "Utils"
        try:
            # We want in-degree (how many files import me)
            scores = nx.in_degree_centrality(self.graph)
        except:
            # Fallback if graph is weird
            scores = {n: 0 for n in self.graph.nodes()}
            
        # Sort
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_nodes

    def generate(self, max_files: int = 20) -> str:
        """
        Generate a string representation of the most important files.
        """
        ranking = self.compute_ranking()
        top_nodes = ranking[:max_files]
        
        lines = []
        lines.append("Repository Map (Top Files):")
        for node_id, score in top_nodes:
            # node_id is relative path, e.g. "src/core.py"
            # We could add signatures here if we had them stored in graph attributes
            lines.append(f"- {node_id} (Rank: {score:.2f})")
            
        return "\n".join(lines)

class ContextPacker:
    """
    packs context into a token budget.
    Priority: RepoMap > Graph Neighbors > RAG Chunks
    """
    def __init__(self, token_limit: int = 8000, model_name: str = "gpt-4"):
        self.token_limit = token_limit
        self.model_name = model_name

    def _count_tokens(self, text: str) -> int:
        # Simple heuristic for MVP (char count / 4) or just len() for testing mocks
        # Real implementation should use tiktoken
        return len(text) // 4

    def pack_context(self, repomap: str, neighbors: List[str], rag_chunks: List[str]) -> Dict[str, Any]:
        """
        Selects content fitting within the budget.
        """
        packed = {}
        current_tokens = 0
        
        # 1. RepoMap (Highest Priority)
        map_tokens = self._count_tokens(repomap)
        if current_tokens + map_tokens <= self.token_limit:
            packed["repomap"] = repomap
            current_tokens += map_tokens
        else:
            # Truncate RepoMap if huge (rare)
            packed["repomap"] = repomap[:self.token_limit * 4] # heuristic
            return packed # Budget exhausted immediately
            
        # 2. Neighbors (Medium Priority)
        packed_neighbors = []
        for n in neighbors:
            n_tokens = self._count_tokens(n)
            if current_tokens + n_tokens <= self.token_limit:
                packed_neighbors.append(n)
                current_tokens += n_tokens
            else:
                break # Stop adding neighbors if full
        
        if packed_neighbors:
            packed["neighbors"] = packed_neighbors
            
        if current_tokens >= self.token_limit:
            return packed

        # 3. RAG Chunks (Low Priority / Recall Boost)
        packed_rag = []
        for c in rag_chunks:
            c_tokens = self._count_tokens(c)
            if current_tokens + c_tokens <= self.token_limit:
                packed_rag.append(c)
                current_tokens += c_tokens
            else:
                break
        
        if packed_rag:
            packed["rag_chunks"] = packed_rag
            
        return packed
