
import numpy as np
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class VectorStore:
    """
    Lightweight in-memory Vector Store using Numpy.
    Stores chunks of text and their embeddings.
    """
    def __init__(self):
        self.embeddings: List[np.ndarray] = []
        self.documents: List[str] = []
        self.metadata: List[Dict[str, Any]] = []

    def add(self, text: str, embedding: List[float], metadata: Dict[str, Any] = None):
        """Add a document and its embedding."""
        if not embedding:
            logger.warning("Empty embedding provided, skipping.")
            return
            
        self.documents.append(text)
        self.embeddings.append(np.array(embedding, dtype=np.float32))
        self.metadata.append(metadata or {})

    def search(self, query_embedding: List[float], k: int = 3) -> List[Tuple[str, float, Dict]]:
        """
        Search for top-k similar documents.
        Returns: List of (text, score, metadata) tuples.
        """
        if not self.embeddings:
            return []
            
        query_vec = np.array(query_embedding, dtype=np.float32)
        norm_query = np.linalg.norm(query_vec)
        
        if norm_query == 0:
            return []
            
        scores = []
        for idx, doc_vec in enumerate(self.embeddings):
            norm_doc = np.linalg.norm(doc_vec)
            if norm_doc == 0:
                score = 0
            else:
                score = np.dot(query_vec, doc_vec) / (norm_query * norm_doc)
            scores.append((score, idx))
            
        # Sort by score descending
        scores.sort(key=lambda x: x[0], reverse=True)
        top_k = scores[:k]
        
        results = []
        for score, idx in top_k:
            results.append((self.documents[idx], float(score), self.metadata[idx]))
            
        return results
