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
    chat_history: list[dict]                # Earlier turns: {"role": "user"|"assistant", "content"}
    require_code: bool                      # The run must end with the Engineer's code (Fix issue)

    # ── Context (populated by retrieval) ──────────────────
    retrieved_chunks: list[dict]            # FAISS search results
    graph_context: str                      # Textual graph context
    graph_nodes: list[dict]                 # Relevant graph nodes
    file_contents: dict                     # file_path -> content mapping

    # ── Agent Output ──────────────────────────────────────
    response: str                           # Final response text
    code_blocks: list[dict]                 # Generated code blocks
    plan: Optional[dict]                    # LLD plan structure

    # ── Collaboration (supervisor + critic loop) ──────────
    agent_outputs: list[dict]               # Each agent run, in order, for later agents to build on
    supervisor_decisions: list[dict]        # {"next", "reason"} per supervisor turn
    next_agent: str                         # Supervisor's pick: qa | lld | codegen | pr | finish
    step_count: int                         # Agents dispatched by the supervisor so far
    review: Optional[dict]                  # Latest critic verdict: approved, score, issues, feedback
    revision_count: int                     # Critic → codegen rework rounds used
    started_at: float                       # Pipeline start (epoch seconds) for the merged timeline

    # ── Explainability ────────────────────────────────────
    explanation_log: dict                   # Full explainability trace

    # ── Metadata ──────────────────────────────────────────
    error: Optional[str]                    # Error message if any
    status: str                             # "success" | "error" | "processing"
