"""
Agent State
Shared state definition for LangGraph multi-agent orchestration.
"""

from typing import TypedDict, Optional, Literal


class AgentState(TypedDict, total=False):
    """Shared state passed between agents in the LangGraph workflow."""

    # ── Input ─────────────────────────────────────────────
    query: str                              # User's original query
    agent_type: Literal["qa", "codegen", "lld", "pr"]  # Routed agent
    repo_url: Optional[str]                 # For PR analysis
    pr_number: Optional[int]                # For PR analysis

    # ── Context (populated by retrieval) ──────────────────
    retrieved_chunks: list[dict]            # FAISS search results
    graph_context: str                      # Textual graph context
    graph_nodes: list[dict]                 # Relevant graph nodes
    file_contents: dict                     # file_path -> content mapping

    # ── Agent Output ──────────────────────────────────────
    response: str                           # Final response text
    code_blocks: list[dict]                 # Generated code blocks
    plan: Optional[dict]                    # LLD plan structure

    # ── Explainability ────────────────────────────────────
    explanation_log: dict                   # Full explainability trace

    # ── Metadata ──────────────────────────────────────────
    error: Optional[str]                    # Error message if any
    status: str                             # "success" | "error" | "processing"
