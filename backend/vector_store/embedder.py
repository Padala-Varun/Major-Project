"""
Embedder
Generates vector embeddings from code chunks using sentence-transformers.
"""

from sentence_transformers import SentenceTransformer
from config import EMBEDDING_MODEL, EMBEDDING_DIMENSION
import numpy as np


class Embedder:
    """Generates embeddings for code chunks."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.model = SentenceTransformer(model_name)
        self.dimension = EMBEDDING_DIMENSION

    def embed_texts(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed
            batch_size: Batch size for encoding

        Returns:
            numpy array of shape (len(texts), embedding_dim)
        """
        if not texts:
            return np.array([]).reshape(0, self.dimension)

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string."""
        embedding = self.model.encode(
            [query],
            normalize_embeddings=True,
        )
        return np.array(embedding, dtype=np.float32)

    def embed_chunks(self, chunks: list[dict], batch_size: int = 64) -> np.ndarray:
        """
        Embed code chunks. Uses file path + entities as context prefix.

        Args:
            chunks: List of chunk dicts with 'content', 'file_path', 'entities'

        Returns:
            numpy array of embeddings
        """
        texts = []
        for chunk in chunks:
            # Create enriched text for better semantic matching
            prefix_parts = [f"File: {chunk['file_path']}"]
            if chunk.get("entities"):
                prefix_parts.append(f"Contains: {', '.join(chunk['entities'])}")
            prefix = " | ".join(prefix_parts)
            texts.append(f"{prefix}\n\n{chunk['content']}")

        return self.embed_texts(texts, batch_size=batch_size)
