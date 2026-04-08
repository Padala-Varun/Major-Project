"""
FAISS Vector Store
Wrapper around FAISS for storing and querying code embeddings.
"""

import os
import json
import faiss
import numpy as np
from typing import Optional
from config import FAISS_INDEX_DIR, EMBEDDING_DIMENSION, TOP_K_RESULTS


class FAISSStore:
    """FAISS-based vector store for code chunk retrieval."""

    def __init__(self, dimension: int = EMBEDDING_DIMENSION, index_dir: str = FAISS_INDEX_DIR):
        self.dimension = dimension
        self.index_dir = index_dir
        self.index: Optional[faiss.IndexFlatIP] = None
        self.metadata: list[dict] = []  # Parallel list of metadata per vector
        os.makedirs(self.index_dir, exist_ok=True)

    def build_index(self, embeddings: np.ndarray, metadata: list[dict]):
        """
        Build a new FAISS index from embeddings and metadata.

        Args:
            embeddings: numpy array of shape (n, dimension)
            metadata: list of dicts, one per embedding, with chunk info
        """
        if len(embeddings) == 0:
            self.index = faiss.IndexFlatIP(self.dimension)
            self.metadata = []
            return

        # Normalize for cosine similarity via inner product
        faiss.normalize_L2(embeddings)

        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(embeddings)
        self.metadata = metadata

    def search(self, query_embedding: np.ndarray, top_k: int = TOP_K_RESULTS) -> list[dict]:
        """
        Search the index for the most similar vectors.

        Args:
            query_embedding: numpy array of shape (1, dimension)
            top_k: number of results to return

        Returns:
            List of dicts with score and metadata
        """
        if self.index is None or self.index.ntotal == 0:
            return []

        faiss.normalize_L2(query_embedding)
        scores, indices = self.index.search(query_embedding, min(top_k, self.index.ntotal))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            result = {
                "score": float(score),
                **self.metadata[idx],
            }
            results.append(result)

        return results

    def save(self, name: str = "default"):
        """Save FAISS index and metadata to disk."""
        if self.index is None:
            return

        index_path = os.path.join(self.index_dir, f"{name}.index")
        meta_path = os.path.join(self.index_dir, f"{name}_metadata.json")

        faiss.write_index(self.index, index_path)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def load(self, name: str = "default") -> bool:
        """Load FAISS index and metadata from disk. Returns True if successful."""
        index_path = os.path.join(self.index_dir, f"{name}.index")
        meta_path = os.path.join(self.index_dir, f"{name}_metadata.json")

        if not os.path.exists(index_path) or not os.path.exists(meta_path):
            return False

        self.index = faiss.read_index(index_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        return True

    def get_stats(self) -> dict:
        """Get index statistics."""
        return {
            "total_vectors": self.index.ntotal if self.index else 0,
            "dimension": self.dimension,
            "metadata_entries": len(self.metadata),
        }
