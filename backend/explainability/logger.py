"""
Explainability Logger
Tracks reasoning steps, graph traversals, and FAISS retrievals
to provide transparent, verifiable AI outputs.
"""

import time
from datetime import datetime
from typing import Any


class ExplainabilityLogger:
    """Structured logging for AI reasoning transparency."""

    def __init__(self, query: str, agent_type: str):
        self.query = query
        self.agent_type = agent_type
        self.start_time = time.time()
        self.steps: list[dict] = []
        self.graph_nodes_visited: list[str] = []
        self.faiss_chunks_retrieved: list[dict] = []
        self.intermediate_conclusions: list[str] = []

    def log_step(self, step_name: str, details: Any = None):
        """Log a reasoning step."""
        self.steps.append({
            "step": step_name,
            "timestamp": time.time() - self.start_time,
            "details": details,
        })

    def log_graph_traversal(self, node_ids: list[str], context: str = ""):
        """Log graph nodes visited during reasoning."""
        self.graph_nodes_visited.extend(node_ids)
        self.log_step("graph_traversal", {
            "nodes_visited": node_ids,
            "context": context,
        })

    def log_faiss_retrieval(self, results: list[dict]):
        """Log FAISS search results."""
        simplified = []
        for r in results:
            simplified.append({
                "file_path": r.get("file_path", "unknown"),
                "score": round(r.get("score", 0), 4),
                "entities": r.get("entities", []),
                "start_line": r.get("start_line"),
                "end_line": r.get("end_line"),
            })
        self.faiss_chunks_retrieved.extend(simplified)
        self.log_step("faiss_retrieval", {
            "chunks_retrieved": len(results),
            "top_score": round(results[0]["score"], 4) if results else 0,
        })

    def log_conclusion(self, conclusion: str):
        """Log an intermediate conclusion."""
        self.intermediate_conclusions.append(conclusion)
        self.log_step("intermediate_conclusion", {"conclusion": conclusion})

    def log_llm_call(self, prompt_summary: str, model: str):
        """Log an LLM invocation."""
        self.log_step("llm_call", {
            "model": model,
            "prompt_summary": prompt_summary[:200],
        })

    def to_dict(self) -> dict:
        """Export the full explainability log as a dict."""
        return {
            "query": self.query,
            "agent_type": self.agent_type,
            "timestamp": datetime.now().isoformat(),
            "total_time_seconds": round(time.time() - self.start_time, 2),
            "reasoning_steps": self.steps,
            "graph_nodes_visited": list(set(self.graph_nodes_visited)),
            "graph_nodes_count": len(set(self.graph_nodes_visited)),
            "faiss_chunks_retrieved": self.faiss_chunks_retrieved,
            "faiss_chunks_count": len(self.faiss_chunks_retrieved),
            "intermediate_conclusions": self.intermediate_conclusions,
        }
