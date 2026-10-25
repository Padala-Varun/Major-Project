"""Vector store module for ShipSafe."""
from .embedder import Embedder
from .faiss_store import FAISSStore

__all__ = ["Embedder", "FAISSStore"]
