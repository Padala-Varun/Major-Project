"""
Conversational Q&A Agent
Answers technical and architectural questions by traversing the knowledge graph
and performing semantic retrieval to provide grounded, contextual responses.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from config import GEMINI_API_KEY, LLM_MODEL, LLM_TEMPERATURE
from explainability.logger import ExplainabilityLogger


class QAAgent:
    """Answers questions about the codebase using graph + vector context."""

    SYSTEM_PROMPT = """You are DevCopilot's Q&A Agent — an expert code analyst.
You answer technical and architectural questions about a software repository.

RULES:
1. Base your answers ONLY on the provided code context, graph structure, and retrieved chunks.
2. Reference specific files, classes, and functions by name.
3. If the context doesn't contain enough information, say so explicitly.
4. Explain architectural patterns, design decisions, and code relationships.
5. Use markdown formatting with code blocks for code references.
6. Be concise but thorough.

GRAPH CONTEXT:
{graph_context}

RETRIEVED CODE CHUNKS:
{code_chunks}
"""

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=LLM_TEMPERATURE,
        )

    def run(self, state: dict) -> dict:
        """Execute the Q&A agent."""
        query = state.get("query", "")
        logger = ExplainabilityLogger(query, "qa")

        # Step 1: gather context
        logger.log_step("gathering_context", "Collecting graph and vector context")

        graph_context = state.get("graph_context", "No graph context available.")
        retrieved_chunks = state.get("retrieved_chunks", [])

        if retrieved_chunks:
            logger.log_faiss_retrieval(retrieved_chunks)

        graph_nodes = state.get("graph_nodes", [])
        if graph_nodes:
            node_ids = [n.get("id", "") for n in graph_nodes]
            logger.log_graph_traversal(node_ids, "Relevant nodes for query")

        # Step 2: format code chunks for prompt
        code_chunks_text = self._format_chunks(retrieved_chunks)
        logger.log_conclusion(f"Retrieved {len(retrieved_chunks)} relevant code chunks")

        # Step 3: call LLM
        prompt = self.SYSTEM_PROMPT.format(
            graph_context=graph_context,
            code_chunks=code_chunks_text,
        )

        logger.log_llm_call("Q&A synthesis with graph + vector context", LLM_MODEL)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]

        try:
            response = self.llm.invoke(messages)
            answer = response.content
            logger.log_conclusion("Generated answer successfully")
        except Exception as e:
            answer = f"Error generating response: {str(e)}"
            logger.log_step("error", str(e))

        return {
            **state,
            "response": answer,
            "explanation_log": logger.to_dict(),
            "status": "success",
        }

    def _format_chunks(self, chunks: list[dict]) -> str:
        """Format retrieved chunks for the LLM prompt."""
        if not chunks:
            return "No code chunks retrieved."

        parts = []
        for i, chunk in enumerate(chunks[:8], 1):  # Limit to top 8
            file_path = chunk.get("file_path", "unknown")
            score = chunk.get("score", 0)
            content = chunk.get("content", "")
            entities = chunk.get("entities", [])
            lines = f"L{chunk.get('start_line', '?')}-{chunk.get('end_line', '?')}"

            header = f"### Chunk {i}: {file_path} ({lines}) [Score: {score:.3f}]"
            if entities:
                header += f"\nEntities: {', '.join(entities)}"

            parts.append(f"{header}\n```\n{content[:1500]}\n```")

        return "\n\n".join(parts)
