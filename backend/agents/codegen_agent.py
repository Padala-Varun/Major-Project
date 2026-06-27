"""
Code Generation Agent
Generates new code aligned with the repository's existing architecture,
coding style, and project dependencies.
"""

from langchain_mistralai import ChatMistralAI
from config import MISTRAL_API_KEY, LLM_MODEL, LLM_MAX_TOKENS
from explainability.logger import ExplainabilityLogger


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

EXISTING CODE PATTERNS:
{graph_context}

SIMILAR CODE FROM REPOSITORY:
{code_chunks}
"""

    def __init__(self):
        self.llm = ChatMistralAI(
            model=LLM_MODEL,
            api_key=MISTRAL_API_KEY,
            temperature=0.4,  # Slightly higher for creativity
            max_tokens=LLM_MAX_TOKENS,
        )

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
        )

        logger.log_llm_call("Code generation with architecture alignment", LLM_MODEL)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Generate code for: {query}"},
        ]

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
        """Extract code blocks from markdown response."""
        blocks = []
        lines = text.split("\n")
        in_block = False
        current_lang = ""
        current_lines = []

        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                current_lang = line.strip().removeprefix("```").strip()
                current_lines = []
            elif line.strip() == "```" and in_block:
                in_block = False
                blocks.append({
                    "language": current_lang or "text",
                    "code": "\n".join(current_lines),
                })
            elif in_block:
                current_lines.append(line)

        return blocks
