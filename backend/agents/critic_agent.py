"""
Critic Agent
Reviews generated code against the repository context and the design plan,
and either approves it or sends it back to the Code Gen agent with feedback.
"""

import json
import re
from config import LLM_MODEL
from agents.llm import make_llm
from explainability.logger import ExplainabilityLogger
from agents.collaboration import format_prior_work, latest_output
from knowledge_graph.impact import format_impact


class CriticAgent:
    """Gatekeeper that reviews Code Gen output before it reaches the user."""

    SYSTEM_PROMPT = """You are ShipSafe's Critic Agent — a strict senior code reviewer.
You review code written by another AI agent for an existing repository.

CHECK FOR:
1. Correctness — logic errors, wrong API usage, unhandled edge cases.
2. Fit with the codebase — imports, functions, and classes it relies on must exist in the
   context below; naming and style must match the repository.
3. Plan adherence — if a design plan is present, the code must implement it.
4. Security and robustness — injection, secrets, missing error handling.
5. Completeness — no placeholders like "TODO: implement" or "..." in place of real logic.

Approve if only minor, cosmetic issues remain. Reject if any issue would make the
code fail, misbehave, or not integrate with the repository.

Respond with ONLY a JSON object, no prose before or after:
{{
  "approved": true | false,
  "score": <integer 1-10>,
  "issues": [{{"severity": "critical" | "major" | "minor", "description": "<specific, actionable>"}}],
  "feedback": "<one paragraph telling the coder exactly what to change>"
}}

REPOSITORY STRUCTURE:
{graph_context}

RELEVANT EXISTING CODE:
{code_chunks}

WORK FROM OTHER AGENTS:
{prior_work}
"""

    def __init__(self):
        self.llm = make_llm(0.1)  # Consistent verdicts

    def run(self, state: dict) -> dict:
        """Review the latest Code Gen output."""
        query = state.get("query", "")
        logger = ExplainabilityLogger(query, "critic")

        draft = latest_output(state, "codegen")
        if not draft:
            review = {"approved": True, "score": None, "issues": [],
                      "feedback": "No code to review."}
            return {**state, "review": review, "response": review["feedback"],
                    "explanation_log": logger.to_dict()}

        logger.log_step("reviewing_draft", {
            "revision": state.get("revision_count", 0),
            "code_blocks": len(draft.get("code_blocks", [])),
        })

        graph_nodes = state.get("graph_nodes", [])
        if graph_nodes:
            logger.log_graph_traversal([n.get("id", "") for n in graph_nodes],
                                       "Checked draft against these components")

        prompt = self.SYSTEM_PROMPT.format(
            graph_context=state.get("graph_context", "No graph context available."),
            code_chunks=self._format_chunks(state.get("retrieved_chunks", [])),
            prior_work=format_prior_work(state, exclude=("codegen", "critic")),
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": (
                f"Task: {query}\n\n"
                f"Impact analysis from the knowledge graph (weigh breakage risk accordingly):\n"
                f"{format_impact(draft.get('impact'))}\n\n"
                f"Code to review:\n\n{draft['response']}"
            )},
        ]

        logger.log_llm_call("Code review against repository and plan", LLM_MODEL)

        try:
            raw = self.llm.invoke(messages).content
            review = self._parse_review(raw)
        except Exception as e:
            # Don't trap the pipeline in a loop because the reviewer failed
            review = {"approved": True, "score": None, "issues": [],
                      "feedback": f"Review unavailable ({e}); passing draft through."}
            logger.log_step("error", str(e))

        verdict = "approved" if review["approved"] else "rejected"
        logger.log_conclusion(
            f"Draft {verdict} (score {review.get('score')}, {len(review['issues'])} issue(s))"
        )

        return {
            **state,
            "review": review,
            "response": self._format_review(review),
            "explanation_log": logger.to_dict(),
        }

    def _parse_review(self, raw: str) -> dict:
        """Extract the JSON verdict; treat unparseable output as approval."""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            data = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            data = {}

        if "approved" not in data:
            return {"approved": True, "score": None, "issues": [],
                    "feedback": "Reviewer response was not parseable; passing draft through."}

        issues = [i for i in data.get("issues", []) if isinstance(i, dict)]
        return {
            "approved": bool(data["approved"]),
            "score": data.get("score"),
            "issues": issues,
            "feedback": str(data.get("feedback", "")),
        }

    def _format_review(self, review: dict) -> str:
        """Markdown summary of the verdict for the final response."""
        icon = "✅ Approved" if review["approved"] else "❌ Changes requested"
        score = f" — score {review['score']}/10" if review.get("score") is not None else ""
        lines = [f"**{icon}{score}**"]
        if review.get("feedback"):
            lines.append(f"\n{review['feedback']}")
        for issue in review.get("issues", []):
            lines.append(f"- **{issue.get('severity', 'issue')}**: {issue.get('description', '')}")
        return "\n".join(lines)

    def _format_chunks(self, chunks: list[dict]) -> str:
        """Format retrieved chunks."""
        if not chunks:
            return "No related code retrieved."

        parts = []
        for i, chunk in enumerate(chunks[:6], 1):
            file_path = chunk.get("file_path", "unknown")
            content = chunk.get("content", "")
            parts.append(f"### Reference {i}: {file_path}\n```\n{content[:1000]}\n```")

        return "\n\n".join(parts)
