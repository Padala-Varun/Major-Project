"""
Multi-Agent Orchestrator
LangGraph workflow that routes queries to specialized agents
and integrates outputs with explainability logging.
"""

import re
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.qa_agent import QAAgent
from agents.codegen_agent import CodeGenAgent
from agents.lld_agent import LLDAgent
from agents.pr_agent import PRAgent
from langchain_google_genai import ChatGoogleGenerativeAI
from config import GEMINI_API_KEY, LLM_MODEL


class Orchestrator:
    """LangGraph orchestrator that routes queries to specialized agents."""

    def __init__(self, graph_query=None, faiss_store=None, embedder=None):
        self.graph_query = graph_query
        self.faiss_store = faiss_store
        self.embedder = embedder

        # Initialize agents
        self.qa_agent = QAAgent()
        self.codegen_agent = CodeGenAgent()
        self.lld_agent = LLDAgent()
        self.pr_agent = PRAgent()

        # Router LLM
        self.router_llm = ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.0,
        )

        # Build the LangGraph workflow
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("router", self._route_query)
        workflow.add_node("retriever", self._retrieve_context)
        workflow.add_node("qa", self._run_qa)
        workflow.add_node("codegen", self._run_codegen)
        workflow.add_node("lld", self._run_lld)
        workflow.add_node("pr", self._run_pr)

        # Set entry point
        workflow.set_entry_point("router")

        # Router -> Retriever
        workflow.add_edge("router", "retriever")

        # Retriever -> Agent (conditional)
        workflow.add_conditional_edges(
            "retriever",
            self._select_agent,
            {
                "qa": "qa",
                "codegen": "codegen",
                "lld": "lld",
                "pr": "pr",
            }
        )

        # All agents -> END
        workflow.add_edge("qa", END)
        workflow.add_edge("codegen", END)
        workflow.add_edge("lld", END)
        workflow.add_edge("pr", END)

        return workflow.compile()

    def _route_query(self, state: AgentState) -> AgentState:
        """Route the query to the appropriate agent using LLM classification."""
        query = state.get("query", "")

        # Check if agent_type is already specified
        if state.get("agent_type"):
            return state

        # Use LLM to classify
        router_prompt = """Classify this developer query into ONE category:
- "qa" — Questions about codebase architecture, how things work, finding code
- "codegen" — Requests to generate, write, or create new code
- "lld" — Requests for design plans, technical specifications, component breakdowns
- "pr" — Requests to analyze, review, or summarize a pull request

Respond with ONLY the category name (qa, codegen, lld, or pr).

Query: {query}"""

        try:
            response = self.router_llm.invoke(
                router_prompt.format(query=query)
            )
            agent_type = response.content.strip().lower()

            # Validate
            if agent_type not in ("qa", "codegen", "lld", "pr"):
                # Fallback heuristics
                agent_type = self._heuristic_route(query)

        except Exception:
            agent_type = self._heuristic_route(query)

        return {**state, "agent_type": agent_type}

    def _heuristic_route(self, query: str) -> str:
        """Fallback heuristic routing."""
        query_lower = query.lower()

        pr_keywords = ["pull request", "pr #", "pr#", "merge request", "diff", "review pr"]
        if any(kw in query_lower for kw in pr_keywords):
            return "pr"

        codegen_keywords = ["generate", "create", "write code", "implement", "add a function",
                            "build a", "code for", "write a"]
        if any(kw in query_lower for kw in codegen_keywords):
            return "codegen"

        lld_keywords = ["design", "plan", "architecture", "breakdown", "specification",
                        "low level", "lld", "component design", "technical plan"]
        if any(kw in query_lower for kw in lld_keywords):
            return "lld"

        return "qa"

    def _retrieve_context(self, state: AgentState) -> AgentState:
        """Retrieve relevant context from FAISS and knowledge graph."""
        query = state.get("query", "")
        retrieved_chunks = []
        graph_context = ""
        graph_nodes = []

        # FAISS retrieval
        if self.faiss_store and self.embedder:
            try:
                query_embedding = self.embedder.embed_query(query)
                retrieved_chunks = self.faiss_store.search(query_embedding, top_k=10)
            except Exception:
                retrieved_chunks = []

        # Graph context
        if self.graph_query and retrieved_chunks:
            try:
                # Get file paths from retrieved chunks
                file_paths = list(set(
                    c.get("file_path", "") for c in retrieved_chunks if c.get("file_path")
                ))

                graph_context = self.graph_query.get_summary_context(file_paths[:5])

                # Get graph nodes for these files
                for fp in file_paths[:5]:
                    node = self.graph_query.get_node(f"file:{fp}")
                    if node:
                        graph_nodes.append(node)
                        # Also get neighbors
                        neighbors = self.graph_query.get_neighbors(f"file:{fp}", direction="both")
                        graph_nodes.extend(neighbors[:3])

            except Exception:
                graph_context = "Graph context unavailable."

        return {
            **state,
            "retrieved_chunks": retrieved_chunks,
            "graph_context": graph_context or "No graph context available.",
            "graph_nodes": graph_nodes,
        }

    def _select_agent(self, state: AgentState) -> str:
        """Select which agent to run based on the routed type."""
        return state.get("agent_type", "qa")

    def _run_qa(self, state: AgentState) -> AgentState:
        return self.qa_agent.run(state)

    def _run_codegen(self, state: AgentState) -> AgentState:
        return self.codegen_agent.run(state)

    def _run_lld(self, state: AgentState) -> AgentState:
        return self.lld_agent.run(state)

    def _run_pr(self, state: AgentState) -> AgentState:
        return self.pr_agent.run(state)

    def process_query(self, query: str, agent_type: str = None,
                      repo_url: str = None, pr_number: int = None) -> dict:
        """
        Process a user query through the multi-agent pipeline.

        Args:
            query: User's question or request
            agent_type: Optional agent override (qa, codegen, lld, pr)
            repo_url: Required for PR analysis
            pr_number: Required for PR analysis

        Returns:
            Dict with response, explanation_log, and metadata
        """
        initial_state: AgentState = {
            "query": query,
            "agent_type": agent_type,
            "repo_url": repo_url,
            "pr_number": pr_number,
            "retrieved_chunks": [],
            "graph_context": "",
            "graph_nodes": [],
            "file_contents": {},
            "response": "",
            "code_blocks": [],
            "plan": None,
            "explanation_log": {},
            "error": None,
            "status": "processing",
        }

        try:
            result = self.workflow.invoke(initial_state)
            return {
                "response": result.get("response", ""),
                "agent_type": result.get("agent_type", "unknown"),
                "code_blocks": result.get("code_blocks", []),
                "plan": result.get("plan"),
                "explanation_log": result.get("explanation_log", {}),
                "status": result.get("status", "success"),
            }
        except Exception as e:
            return {
                "response": f"Error processing query: {str(e)}",
                "agent_type": agent_type or "unknown",
                "explanation_log": {},
                "status": "error",
                "error": str(e),
            }
