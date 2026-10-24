"""
Multi-Agent Orchestrator
LangGraph workflow in which a supervisor dispatches specialized agents one after
another, each building on the previous agents' work. Code Gen output always passes
through a critic that can send it back for revision.

    retriever → supervisor ⇄ {qa, lld, pr}
                supervisor → codegen → critic ─(rejected)→ codegen
                                         └──(approved)──→ supervisor
                supervisor → finalize → END
"""

import json
import re
import time
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.qa_agent import QAAgent
from agents.codegen_agent import CodeGenAgent
from agents.lld_agent import LLDAgent
from agents.pr_agent import PRAgent
from agents.critic_agent import CriticAgent
from agents.collaboration import AGENT_TITLES
from config import MAX_AGENT_STEPS, MAX_REVISIONS
from agents.llm import make_llm

WORKER_AGENTS = ("qa", "lld", "codegen", "pr")


def friendly_error(raw: str) -> str:
    """Turn an LLM provider error into something a user can act on."""
    if "429" in raw:
        return ("The AI provider is rate-limiting requests (HTTP 429). Wait a minute and try "
                "again, or set LLM_MODEL in backend/.env to a model with a higher limit on your plan.")
    if "403" in raw:
        return ("This model isn't available on your Mistral plan (HTTP 403). "
                "Set LLM_MODEL in backend/.env to a model your plan includes.")
    if "401" in raw:
        return "The Mistral API key was rejected (HTTP 401). Check MISTRAL_API_KEY in backend/.env."
    return f"An agent failed: {raw[:300]}"


class Orchestrator:
    """LangGraph supervisor that coordinates collaborating agents."""

    SUPERVISOR_PROMPT = """You are the supervisor of a team of AI agents working on a software repository.
Decide which agent should act NEXT to fulfil the user's request, or FINISH.

AGENTS (id — name):
- "qa"      — Explorer: investigates the codebase, finds relevant code, explains how things work.
- "lld"     — Architect: writes a low-level design plan: affected components, interfaces, steps.
- "codegen" — Engineer: writes code. Its output is automatically reviewed by the Critic.
- "pr"      — Reviewer: analyzes a GitHub pull request (PR number provided: {has_pr}).

GUIDELINES:
- Use the fewest agents that fully satisfy the request.
- Pure questions → "qa", then FINISH.
- Design-only requests → "lld" (optionally "qa" first if the area is unclear).
- Small, well-scoped code requests → "codegen" directly.
- Non-trivial features or fixes → "qa" to locate the code, then "lld", then "codegen".
- PR requests → "pr"; add "codegen" only if the user asks for fixes.
- Never pick an agent that has already run. FINISH once the request is answered.

USER REQUEST:
{query}

WORK COMPLETED SO FAR:
{completed}

Respond with ONLY a JSON object: {{"next": "qa" | "lld" | "codegen" | "pr" | "finish", "reason": "<one sentence>"}}
The reason is shown to the user: refer to agents by name (Explorer, Architect, Engineer,
Critic, Reviewer), never by id."""

    def __init__(self, graph_query=None, faiss_store=None, embedder=None):
        self.graph_query = graph_query
        self.faiss_store = faiss_store
        self.embedder = embedder

        # Initialize agents
        self.agents = {
            "qa": QAAgent(),
            "codegen": CodeGenAgent(),
            "lld": LLDAgent(),
            "pr": PRAgent(),
            "critic": CriticAgent(),
        }

        # Supervisor LLM
        self.supervisor_llm = make_llm(0.0)

        # Build the LangGraph workflow
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(AgentState)

        workflow.add_node("retriever", self._retrieve_context)
        workflow.add_node("supervisor", self._supervise)
        for name in (*WORKER_AGENTS, "critic"):
            workflow.add_node(name, self._make_agent_node(name))
        workflow.add_node("finalize", self._finalize)

        workflow.set_entry_point("retriever")
        workflow.add_edge("retriever", "supervisor")

        workflow.add_conditional_edges(
            "supervisor",
            lambda state: state["next_agent"],
            {**{name: name for name in WORKER_AGENTS}, "finish": "finalize"},
        )

        # Non-coding agents report back to the supervisor
        for name in ("qa", "lld", "pr"):
            workflow.add_edge(name, "supervisor")

        # Code always goes through the critic, which may send it back
        workflow.add_edge("codegen", "critic")
        workflow.add_conditional_edges(
            "critic",
            self._after_review,
            {"codegen": "codegen", "supervisor": "supervisor"},
        )

        workflow.add_edge("finalize", END)

        return workflow.compile()

    # ── Supervisor ─────────────────────────────────────────

    def _supervise(self, state: AgentState) -> dict:
        """Pick the next agent based on the request and the work done so far."""
        outputs = state.get("agent_outputs", [])
        already_ran = {o["agent"] for o in outputs}
        step_count = state.get("step_count", 0)
        forced = state.get("agent_type") if state.get("agent_type") in WORKER_AGENTS else None

        if outputs and outputs[-1].get("error"):
            # Later agents would hit the same failure (usually the LLM provider)
            next_agent, reason = "finish", "Stopping: the last agent failed."
        elif forced:
            # User picked an agent: run it (plus the critic, for codegen), then stop
            if forced in already_ran:
                next_agent, reason = "finish", "The agent you selected has finished."
            else:
                next_agent, reason = forced, "Agent selected by the user."
        elif step_count >= MAX_AGENT_STEPS:
            next_agent, reason = "finish", f"Step budget of {MAX_AGENT_STEPS} agents reached."
        else:
            next_agent, reason = self._ask_supervisor(state, outputs)
            if next_agent in already_ran:
                next_agent, reason = "finish", f"Supervisor re-picked a finished agent; stopping. ({reason})"
            elif not outputs and next_agent == "finish":
                # Every request deserves at least one agent
                next_agent = self._heuristic_route(state.get("query", ""))
                reason = "Supervisor tried to finish before any work; using heuristic routing."

        decision = {
            "next": next_agent,
            "reason": reason,
            "at": round(time.time() - state["started_at"], 2),
        }
        return {
            "next_agent": next_agent,
            "supervisor_decisions": state.get("supervisor_decisions", []) + [decision],
            "step_count": step_count + (next_agent != "finish"),
        }

    def _ask_supervisor(self, state: AgentState, outputs: list[dict]) -> tuple[str, str]:
        """Ask the LLM for the next move; fall back to heuristics on failure."""
        completed = []
        for o in outputs:
            summary = o.get("response", "")[:600]
            completed.append(f"[{o['agent']}] {summary}")

        prompt = self.SUPERVISOR_PROMPT.format(
            has_pr="yes" if state.get("pr_number") else "no",
            query=state.get("query", ""),
            completed="\n\n".join(completed) or "Nothing yet.",
        )

        try:
            raw = self.supervisor_llm.invoke(prompt).content
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group(0)) if match else {}
            next_agent = str(data.get("next", "")).strip().lower()
            reason = str(data.get("reason", "")).strip()
            if next_agent in (*WORKER_AGENTS, "finish"):
                return next_agent, reason or "No reason given."
        except Exception:
            pass

        if outputs:
            return "finish", "Supervisor unavailable; finishing with the work done so far."
        return self._heuristic_route(state.get("query", "")), "Supervisor unavailable; heuristic routing."

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

    def _after_review(self, state: AgentState) -> str:
        """Send rejected code back to Code Gen until the revision budget runs out."""
        review = state.get("review") or {}
        if not review.get("approved") and state.get("revision_count", 0) < MAX_REVISIONS:
            return "codegen"
        return "supervisor"

    # ── Retrieval ──────────────────────────────────────────

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

    # ── Agent nodes ────────────────────────────────────────

    def _make_agent_node(self, name: str):
        """Wrap an agent so its result is appended to the shared agent_outputs."""
        agent = self.agents[name]

        def node(state: AgentState) -> dict:
            outputs = state.get("agent_outputs", [])
            if name == "critic" and outputs and outputs[-1].get("error"):
                # Code Gen failed: nothing to review, hand back to the supervisor
                return {"review": {"approved": True, "score": None, "issues": [],
                                   "feedback": "Skipped: the Code Gen agent failed."}}

            review = state.get("review")
            is_revision = name == "codegen" and review is not None and not review.get("approved")

            if name == "critic":
                reason = "Automatic review of the Engineer's code."
            elif is_revision:
                reason = "Revising the code to address the Critic's feedback."
            else:
                reason = state["supervisor_decisions"][-1]["reason"]

            started = time.time() - state["started_at"]
            result = agent.run(state)
            log = result.get("explanation_log", {})
            # Agents catch their own exceptions and log them as an "error" step
            error = next((str(s.get("details")) for s in log.get("reasoning_steps", [])
                          if s.get("step") == "error"), None)

            record = {
                "agent": name,
                "reason": reason,
                "started_offset": started,
                "error": error,
                "response": result.get("response", ""),
                "code_blocks": result.get("code_blocks", []) if name == "codegen" else [],
                "plan": result.get("plan") if name == "lld" else None,
                "review": result.get("review") if name == "critic" else None,
                "explanation_log": result.get("explanation_log", {}),
            }
            update = {"agent_outputs": state.get("agent_outputs", []) + [record]}
            if name == "critic":
                update["review"] = result.get("review")
            if is_revision:
                update["revision_count"] = state.get("revision_count", 0) + 1
            return update

        return node

    # ── Final assembly ─────────────────────────────────────

    def _finalize(self, state: AgentState) -> dict:
        """Merge every agent's contribution into one response and one explainability log."""
        outputs = state.get("agent_outputs", [])
        workers = [o for o in outputs if o["agent"] != "critic"]
        if not workers:
            return {"response": "No agent produced a result.", "status": "error",
                    "explanation_log": self._merge_logs(state)}

        if workers[-1].get("error"):
            return {"response": friendly_error(workers[-1]["error"]), "status": "error",
                    "agent_type": workers[-1]["agent"],
                    "explanation_log": self._merge_logs(state)}

        # Latest output per worker agent, in the order the agents first ran
        latest = {}
        for o in workers:
            latest[o["agent"]] = o
        order = list(dict.fromkeys(o["agent"] for o in workers))
        review = state.get("review")
        revisions = state.get("revision_count", 0)

        if len(order) == 1 and review is None:
            response = latest[order[0]]["response"]
        else:
            sections = []
            for agent in order:
                title = AGENT_TITLES.get(agent, agent)
                if agent == "codegen" and revisions:
                    title += f" (revised {revisions}× after review)"
                sections.append(f"## {title}\n\n{latest[agent]['response']}")
            if review is not None:
                verdict = next(o["response"] for o in reversed(outputs) if o["agent"] == "critic")
                sections.append(f"## {AGENT_TITLES['critic']}\n\n{verdict}")
            response = "\n\n---\n\n".join(sections)

        codegen = latest.get("codegen")
        lld = latest.get("lld")
        return {
            "response": response,
            "agent_type": workers[-1]["agent"],
            "code_blocks": codegen["code_blocks"] if codegen else [],
            "plan": lld["plan"] if lld else None,
            "status": "success",
            "explanation_log": self._merge_logs(state),
        }

    def _merge_logs(self, state: AgentState) -> dict:
        """Combine the supervisor's decisions and every agent's log into one timeline."""
        outputs = state.get("agent_outputs", [])
        steps = []
        nodes = set()
        chunks = {}
        conclusions = []
        timeline = []

        for d in state.get("supervisor_decisions", []):
            steps.append({"step": f"supervisor → {d['next']}", "timestamp": d["at"],
                          "details": d["reason"]})

        for o in outputs:
            log = o.get("explanation_log", {})
            agent = o["agent"]
            for s in log.get("reasoning_steps", []):
                steps.append({**s, "step": f"[{agent}] {s['step']}",
                              "timestamp": o["started_offset"] + s.get("timestamp", 0)})
            nodes.update(log.get("graph_nodes_visited", []))
            for c in log.get("faiss_chunks_retrieved", []):
                chunks[(c.get("file_path"), c.get("start_line"))] = c
            conclusions.extend(f"[{agent}] {c}" for c in log.get("intermediate_conclusions", []))

            entry = {"agent": agent, "reason": o["reason"],
                     "duration_seconds": log.get("total_time_seconds", 0)}
            if o.get("review"):
                entry["approved"] = o["review"]["approved"]
                entry["score"] = o["review"].get("score")
            timeline.append(entry)

        steps.sort(key=lambda s: s["timestamp"])
        return {
            "query": state.get("query", ""),
            "agent_type": " → ".join(o["agent"] for o in outputs) or "none",
            "total_time_seconds": round(time.time() - state["started_at"], 2),
            "reasoning_steps": steps,
            "graph_nodes_visited": sorted(nodes),
            "graph_nodes_count": len(nodes),
            "faiss_chunks_retrieved": list(chunks.values()),
            "faiss_chunks_count": len(chunks),
            "intermediate_conclusions": conclusions,
            "agent_timeline": timeline,
            "supervisor_decisions": state.get("supervisor_decisions", []),
            "revision_count": state.get("revision_count", 0),
        }

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
        try:
            final = self.workflow.invoke(
                self._initial_state(query, agent_type, repo_url, pr_number),
                config={"recursion_limit": 50},
            )
            return self._result(final)
        except Exception as e:
            return self._error_result(e, agent_type)

    def stream_query(self, query: str, agent_type: str = None,
                     repo_url: str = None, pr_number: int = None):
        """Same pipeline as process_query, yielding progress events as agents work.

        Events (dicts with a "type" key):
            context  — retrieval finished
            decision — supervisor picked the next agent
            working  — an agent started
            step     — an agent finished (same shape as result["steps"] items)
            final    — the full result, as returned by process_query
        """
        state = None
        seen_decisions = seen_outputs = 0
        try:
            for state in self.workflow.stream(
                self._initial_state(query, agent_type, repo_url, pr_number),
                config={"recursion_limit": 50},
                stream_mode="values",
            ):
                if seen_decisions == 0 and not state.get("supervisor_decisions") and state.get("graph_context"):
                    yield {"type": "context",
                           "chunks": len(state.get("retrieved_chunks", [])),
                           "graph_nodes": len(state.get("graph_nodes", []))}

                decisions = state.get("supervisor_decisions", [])
                for d in decisions[seen_decisions:]:
                    yield {"type": "decision", "next": d["next"], "reason": d["reason"]}
                    if d["next"] != "finish":
                        yield {"type": "working", "agent": d["next"]}
                seen_decisions = len(decisions)

                outputs = state.get("agent_outputs", [])
                for o in outputs[seen_outputs:]:
                    yield {"type": "step", **self._step(o)}
                    following = self._following_agent(o, state)
                    if following:
                        yield {"type": "working", "agent": following}
                seen_outputs = len(outputs)

            yield {"type": "final", **self._result(state)}
        except Exception as e:
            yield {"type": "final", **self._error_result(e, agent_type)}

    def _following_agent(self, output: dict, state: AgentState) -> str | None:
        """Agent that runs next without a supervisor decision (the critic loop)."""
        if output["agent"] == "codegen":
            return None if output.get("error") else "critic"
        if output["agent"] == "critic" and self._after_review(state) == "codegen":
            return "codegen"
        return None

    def _step(self, output: dict) -> dict:
        """Client-facing view of one agent run."""
        review = output.get("review") or {}
        return {
            "agent": output["agent"],
            "reason": output["reason"],
            "response": output["response"],
            "code_blocks": output.get("code_blocks", []),
            "duration_seconds": output.get("explanation_log", {}).get("total_time_seconds", 0),
            "error": friendly_error(output["error"]) if output.get("error") else None,
            "approved": review.get("approved"),
            "score": review.get("score"),
        }

    def _result(self, state: AgentState) -> dict:
        return {
            "response": state.get("response", ""),
            "agent_type": state.get("agent_type", "unknown"),
            "agent_trace": [o["agent"] for o in state.get("agent_outputs", [])],
            "steps": [self._step(o) for o in state.get("agent_outputs", [])],
            "code_blocks": state.get("code_blocks", []),
            "plan": state.get("plan"),
            "review": state.get("review"),
            "explanation_log": state.get("explanation_log", {}),
            "status": state.get("status", "success"),
        }

    def _error_result(self, error: Exception, agent_type: str = None) -> dict:
        return {
            "response": f"Error processing query: {error}",
            "agent_type": agent_type or "unknown",
            "agent_trace": [],
            "steps": [],
            "explanation_log": {},
            "status": "error",
            "error": str(error),
        }

    def _initial_state(self, query: str, agent_type: str = None,
                       repo_url: str = None, pr_number: int = None) -> AgentState:
        return {
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
            "agent_outputs": [],
            "supervisor_decisions": [],
            "next_agent": "",
            "step_count": 0,
            "review": None,
            "revision_count": 0,
            "started_at": time.time(),
            "explanation_log": {},
            "error": None,
            "status": "processing",
        }
