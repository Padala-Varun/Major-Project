"""
Embedder
Generates vector embeddings via Mistral API (langchain-mistralai).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from langchain_mistralai import MistralAIEmbeddings

from config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSION,
    EMBEDDING_MAX_CHARS,
    EMBEDDING_MODEL,
    EMBEDDING_PARALLEL_BATCHES,
    MISTRAL_API_KEY,
)


class Embedder:
    """Generates embeddings for code chunks using Mistral."""

    def __init__(self):
        self.client = MistralAIEmbeddings(
            model=EMBEDDING_MODEL,
            mistral_api_key=MISTRAL_API_KEY or None,
            max_concurrent_requests=EMBEDDING_PARALLEL_BATCHES,
            timeout=120,
        )
        self.dimension = EMBEDDING_DIMENSION

    def _truncate(self, text: str) -> str:
        if len(text) <= EMBEDDING_MAX_CHARS:
            return text
        return text[:EMBEDDING_MAX_CHARS]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        batch = [self._truncate(t) for t in texts]
        return self.client.embed_documents(batch)

    def embed_texts(self, texts: list[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> np.ndarray:
        if not texts:
            return np.array([]).reshape(0, self.dimension)

        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
        results: list[list[list[float]]] = [[] for _ in batches]

        workers = min(EMBEDDING_PARALLEL_BATCHES, len(batches))
        if workers <= 1:
            for idx, batch in enumerate(batches):
                results[idx] = self._embed_batch(batch)
                print(f"[EMBED] {min((idx + 1) * batch_size, len(texts))}/{len(texts)} chunks")
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(self._embed_batch, batch): idx
                    for idx, batch in enumerate(batches)
                }
                done = 0
                for future in as_completed(future_map):
                    idx = future_map[future]
                    results[idx] = future.result()
                    done += len(results[idx])
                    print(f"[EMBED] {done}/{len(texts)} chunks")

        vectors = [vector for batch_vectors in results for vector in batch_vectors]
        return np.array(vectors, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        vector = self.client.embed_query(self._truncate(query))
        return np.array([vector], dtype=np.float32)

    def embed_chunks(self, chunks: list[dict], batch_size: int = EMBEDDING_BATCH_SIZE) -> np.ndarray:
        texts = []
        for chunk in chunks:
            prefix_parts = [f"File: {chunk['file_path']}"]
            if chunk.get("entities"):
                prefix_parts.append(f"Contains: {', '.join(chunk['entities'])}")
            prefix = " | ".join(prefix_parts)
            texts.append(f"{prefix}\n\n{chunk['content']}")

        return self.embed_texts(texts, batch_size=batch_size)
