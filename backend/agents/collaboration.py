"""
Agent Collaboration Helpers
Lets each agent see what earlier agents in the same pipeline produced.
"""

AGENT_TITLES = {
    "qa": "Explorer — codebase findings",
    "lld": "Architect — design plan",
    "codegen": "Engineer — implementation",
    "pr": "Reviewer — pull request analysis",
    "critic": "Critic — review",
}

MAX_CHARS_PER_OUTPUT = 3000


def latest_output(state: dict, agent: str) -> dict | None:
    """Most recent output produced by `agent`, if it has run."""
    for out in reversed(state.get("agent_outputs", [])):
        if out["agent"] == agent:
            return out
    return None


def format_prior_work(state: dict, exclude: tuple = ()) -> str:
    """Render earlier agents' outputs for inclusion in a prompt.

    Only the latest output per agent is shown, so superseded code drafts
    don't crowd the context.
    """
    seen = set()
    sections = []
    for out in reversed(state.get("agent_outputs", [])):
        agent = out["agent"]
        if agent in seen or agent in exclude:
            continue
        seen.add(agent)
        text = out.get("response", "")
        if len(text) > MAX_CHARS_PER_OUTPUT:
            text = text[:MAX_CHARS_PER_OUTPUT] + "\n…(truncated)"
        sections.append(f"### {AGENT_TITLES.get(agent, agent)}\n{text}")

    if not sections:
        return "No other agents have contributed yet."
    return "\n\n".join(reversed(sections))
