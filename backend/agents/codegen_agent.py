"""
Code Generation Agent
Generates new code aligned with the repository's existing architecture,
coding style, and project dependencies.
"""

import re

from config import LLM_MODEL
from agents.llm import make_llm
from explainability.logger import ExplainabilityLogger
from agents.collaboration import format_prior_work, latest_output, history_messages

CODE_EXTENSIONS = {
    "py", "js", "jsx", "ts", "tsx", "mjs", "cjs", "html", "css", "scss", "json", "yaml", "yml",
    "md", "java", "go", "rs", "rb", "php", "cs", "cpp", "c", "h", "hpp", "kt", "swift", "vue",
    "svelte", "sql", "sh", "toml", "ini", "cfg", "txt", "xml", "gradle",
}
# Framework names that look like file names
NOT_FILES = {"node.js", "next.js", "vue.js", "react.js", "express.js", "nuxt.js", "three.js", "d3.js"}
COMMAND_LANGUAGES = {"bash", "sh", "shell", "console", "powershell", "cmd", "text", "terminal"}
PATH_TOKEN = re.compile(r"[\w@.-]*(?:/[\w@.-]+)*\.[A-Za-z]\w{0,7}")
PATH_COMMENT = re.compile(
    r"^\s*(?://|#|/\*|<!--|--|;)\s*(?:file(?:name)?\s*:\s*)?([\w@./-]+\.[A-Za-z]\w{0,7})\s*(?:\*/|-->)?\s*$",
    re.IGNORECASE,
)


def _as_path(token: str) -> str | None:
    """A plausible repository file path, or None ("Node.js", "e.g." and URLs don't count)."""
    token = token.strip("`*_'\"()[]:,").lstrip("./")
    ext = token.rsplit(".", 1)[-1].lower()
    if token.lower() in NOT_FILES or "://" in token or ext not in CODE_EXTENSIONS:
        return None
    return token


class CodeGenAgent:
    """Generates code that fits the existing codebase patterns."""

    SYSTEM_PROMPT = """You are DevCopilot's Code Generation Agent — an expert code architect.
You generate new code that seamlessly integrates with an existing software repository.

RULES:
1. Analyze the existing code patterns, imports, naming conventions, and architecture.
2. Generate code that matches the existing style and conventions.
3. Include necessary imports based on the project's dependency patterns.
4. Provide setup instructions if new dependencies are needed.
5. Explain where the generated code should be placed in the project structure.
6. Include inline comments and docstrings matching the project's documentation style.
7. Use markdown code blocks with proper language tags.
8. Put one complete file per code block, and make its first line a comment with the
   file's path from the repository root (e.g. `# src/app/auth.py` or `// web/js/login.js`).
   Use existing paths when modifying files. Shell commands go in ```bash blocks.

EXISTING CODE PATTERNS:
{graph_context}

SIMILAR CODE FROM REPOSITORY:
{code_chunks}

WORK FROM OTHER AGENTS (if a design plan is present, implement it):
{prior_work}
"""

    REVISION_PROMPT = """A code reviewer rejected your previous attempt. Fix every issue it raised
and return the complete revised code (not just a diff).

REVIEWER FEEDBACK:
{feedback}

ISSUES:
{issues}
"""

    def __init__(self):
        self.llm = make_llm(0.4)  # Slightly higher for creativity

    def run(self, state: dict) -> dict:
        """Execute the code generation agent."""
        query = state.get("query", "")
        logger = ExplainabilityLogger(query, "codegen")

        # Step 1: Analyze existing patterns
        logger.log_step("analyzing_patterns", "Reviewing existing code architecture")

        graph_context = state.get("graph_context", "No graph context available.")
        retrieved_chunks = state.get("retrieved_chunks", [])

        if retrieved_chunks:
            logger.log_faiss_retrieval(retrieved_chunks)

        graph_nodes = state.get("graph_nodes", [])
        if graph_nodes:
            node_ids = [n.get("id", "") for n in graph_nodes]
            logger.log_graph_traversal(node_ids, "Analyzed for code patterns")

        # Step 2: Format context
        code_chunks_text = self._format_chunks(retrieved_chunks)
        logger.log_conclusion(f"Analyzed {len(retrieved_chunks)} similar code sections")

        # Step 3: Generate code
        prompt = self.SYSTEM_PROMPT.format(
            graph_context=graph_context,
            code_chunks=code_chunks_text,
            prior_work=format_prior_work(state, exclude=("codegen", "critic")),
        )

        messages = [
            {"role": "system", "content": prompt},
            *history_messages(state),
            {"role": "user", "content": f"Generate code for: {query}"},
        ]

        # Revision round: the critic rejected the last draft
        review = state.get("review")
        previous = latest_output(state, "codegen")
        if review and not review.get("approved") and previous:
            issues = "\n".join(
                f"- [{i.get('severity', 'issue')}] {i.get('description', '')}"
                for i in review.get("issues", [])
            ) or "- (none listed)"
            messages.append({"role": "assistant", "content": previous["response"]})
            messages.append({"role": "user", "content": self.REVISION_PROMPT.format(
                feedback=review.get("feedback", ""),
                issues=issues,
            )})
            logger.log_step("revising", {
                "round": state.get("revision_count", 0),
                "issues_to_fix": len(review.get("issues", [])),
            })
            logger.log_llm_call("Code revision addressing critic feedback", LLM_MODEL)
        else:
            logger.log_llm_call("Code generation with architecture alignment", LLM_MODEL)

        try:
            response = self.llm.invoke(messages)
            generated = response.content
            code_blocks = self._extract_code_blocks(generated)
            logger.log_conclusion(f"Generated {len(code_blocks)} code block(s)")
        except Exception as e:
            generated = f"Error generating code: {str(e)}"
            code_blocks = []
            logger.log_step("error", str(e))

        return {
            **state,
            "response": generated,
            "code_blocks": code_blocks,
            "explanation_log": logger.to_dict(),
            "status": "success",
        }

    def _format_chunks(self, chunks: list[dict]) -> str:
        """Format chunks showing code patterns."""
        if not chunks:
            return "No existing code available for reference."

        parts = []
        for i, chunk in enumerate(chunks[:6], 1):
            file_path = chunk.get("file_path", "unknown")
            lang = chunk.get("language", "")
            content = chunk.get("content", "")

            parts.append(f"### Reference {i}: {file_path}\n```{lang}\n{content[:1200]}\n```")

        return "\n\n".join(parts)

    def _extract_code_blocks(self, text: str) -> list[dict]:
        """Extract code blocks from markdown, with the file path each belongs to when stated.

        The path comes from a first-line comment (`# src/app.py`, removed from
        the code) or from the prose line just before the block
        ("Revised signup page (web/html/signup.html):").
        """
        blocks = []
        lines = text.split("\n")
        in_block = False
        current_lang = ""
        current_lines = []
        prose = []  # recent non-empty lines outside code blocks

        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                current_lang = line.strip().removeprefix("```").strip()
                current_lines = []
            elif line.strip() == "```" and in_block:
                in_block = False
                blocks.append(self._make_block(current_lang or "text", current_lines, prose[-2:]))
                prose = []
            elif in_block:
                current_lines.append(line)
            elif line.strip():
                prose.append(line)

        return blocks

    def _make_block(self, language: str, code_lines: list[str], preceding: list[str]) -> dict:
        filename = None
        first = next((i for i, ln in enumerate(code_lines) if ln.strip()), None)
        if first is not None:
            m = PATH_COMMENT.match(code_lines[first])
            if m and _as_path(m.group(1)):
                filename = _as_path(m.group(1))
                code_lines = code_lines[:first] + code_lines[first + 1:]

        if not filename and language.lower() not in COMMAND_LANGUAGES:
            for line in reversed(preceding):
                paths = [p for p in map(_as_path, PATH_TOKEN.findall(line)) if p]
                # Prefer something that looks like a real path over a bare file name
                with_dir = [p for p in paths if "/" in p]
                if with_dir or paths:
                    filename = (with_dir or paths)[-1]
                    break

        return {"language": language, "code": "\n".join(code_lines).strip("\n"), "filename": filename}
