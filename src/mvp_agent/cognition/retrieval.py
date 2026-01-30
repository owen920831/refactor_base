
import logging
from pathlib import Path
from typing import Dict, List, Optional
import re

from mvp_agent.cognition.graph import DependencyGraph
from mvp_agent.cognition.vector_store import VectorStore
from mvp_agent.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class ContextManager:
    """
    Manages shared context (interfaces/headers) across files.
    Acts as the 'Librarian' for the RAG system.
    """
    def __init__(self, root_path: Path, graph: DependencyGraph, llm_client: LLMClient, embedding_model: str = "llama3:latest"):
        self.root_path = root_path
        self.graph = graph
        self.llm_client = llm_client
        self.embedding_model = embedding_model
        
        self.vector_store = VectorStore()
        
        # Explicit Interface storage (Legacy/Exact match)
        self.interfaces: Dict[str, str] = {}

    def register_interface(self, file_path: Path, code: str):
        """
        Register the generated C++ interface for a completed file.
        Also ingests chunks into the Vector Store.
        """
        rel_path = str(file_path.relative_to(self.root_path))
        self.interfaces[rel_path] = code
        
        # Ingest into Vector Store for semantic retrieval
        self._ingest_code(rel_path, code)

    def _ingest_code(self, rel_path: str, code: str):
        """Split code into chunks and store embeddings."""
        chunks = self._chunk_code(code)
        for chunk in chunks:
            embedding = self.llm_client.embed(chunk, model=self.embedding_model)
            if embedding:
                self.vector_store.add(
                    text=chunk,
                    embedding=embedding,
                    metadata={"source": rel_path}
                )
        logger.info(f"Ingested {len(chunks)} chunks from {rel_path}")

    def _chunk_code(self, code: str) -> List[str]:
        """Simple regex-based chunking by class/function."""
        # Split by double newline as a heuristic for blocks
        # Refinement: Use tree-sitter or balanced braces in future
        raw_chunks = re.split(r'\n\s*\n', code)
        return [c.strip() for c in raw_chunks if len(c.strip()) > 50]

    def retrieve_context_for_task(self, current_file: Path, source_code: str = "") -> str:
        """
        Retrieves relevant context for refactoring 'current_file'.
        
        Strategy:
        1. Explicit: Dependencies from Graph.
        2. Implicit: Semantic search using source_code of current file.
        """
        context_parts = []
        
        # 1. Dependency-based Retrieval (Explicit)
        deps = self.graph.get_dependencies(current_file)
        if deps:
            context_parts.append(f"// --- Dependencies for {current_file.name} ---")
            for dep in deps:
                rel_dep = str(dep.relative_to(self.root_path))
                if rel_dep in self.interfaces:
                     # For now, still providing full interface, but could use RAG here too
                     context_parts.append(f"// From {rel_dep}:")
                     context_parts.append(self.interfaces[rel_dep])
        
        # 2. Semantic Retrieval (RAG)
        if source_code:
            # Create a query embedding from the *imports* or *signatures* of the source
            # Using full source might be too noisy, lets use first 500 chars (imports/headers)
            query_text = source_code[:500] 
            query_vec = self.llm_client.embed(query_text, model=self.embedding_model)
            
            results = self.vector_store.search(query_vec, k=3)
            if results:
                context_parts.append(f"// --- Similar Code / Relevant Utils ---")
                for text, score, meta in results:
                    context_parts.append(f"// From {meta['source']} (Score: {score:.2f}):")
                    context_parts.append(text)
        
        return "\n\n".join(context_parts)

    def export_rag_db_json(self) -> Dict:
        """
        Export the RAG chunk database matching V2 Schema.
        """
        rag_data = {
            "chunks": []
        }
        
        # Access VectorStore internal state to dump chunks
        # Assuming VectorStore has .documents, .metadata, .embeddings
        count = len(self.vector_store.documents)
        for i in range(count):
            meta = self.vector_store.metadata[i] if i < len(self.vector_store.metadata) else {}
            chunk_entry = {
                "chunk_id": f"ck_{i:06d}",
                "path": meta.get("source", "unknown"),
                "range": meta.get("range", [0, 0]), # Placeholder if not captured yet
                "symbol_ids": meta.get("symbol_ids", []),
                "text": self.vector_store.documents[i],
                # "embedding": ... (skip huge vectors for readable JSON unless strictly requested)
            }
            rag_data["chunks"].append(chunk_entry)
            
        return rag_data
