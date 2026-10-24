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
MAX_HISTORY_MESSAGES = 6     # earlier turns of the conversation passed to agents
MAX_CHARS_PER_TURN = 2000


def history_messages(state: dict) -> list[dict]:
    """Earlier turns of the conversation as chat messages, oldest first.

    Lets follow-ups like "now add tests for that" resolve "that". Messages
    always alternate user/assistant and end on an assistant turn, so the
    agent's own request can follow.
    """
    turns = []
    for msg in state.get("chat_history", [])[-MAX_HISTORY_MESSAGES:]:
        role = "assistant" if msg.get("role") == "assistant" else "user"
        content = str(msg.get("content", "")).strip()[:MAX_CHARS_PER_TURN]
        if not content:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n\n" + content
        else:
            turns.append({"role": role, "content": content})
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    if turns and turns[-1]["role"] == "user":
        turns.pop()
    return turns


def history_summary(state: dict, chars: int = 300) -> str:
    """Short transcript of earlier turns, for prompts that aren't chat-shaped."""
    lines = [f"{m['role']}: {m['content'][:chars]}" for m in history_messages(state)]
    return "\n".join(lines) or "No earlier conversation."


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
