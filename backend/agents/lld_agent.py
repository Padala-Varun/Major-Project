"""
Low-Level Design Planning Agent
Creates detailed technical plans and component breakdowns before coding begins,
helping developers think through complex changes systematically.
"""

from langchain_mistralai import ChatMistralAI
from config import MISTRAL_API_KEY, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS
from explainability.logger import ExplainabilityLogger


class LLDAgent:
    """Creates detailed low-level design plans for code changes."""

    SYSTEM_PROMPT = """You are DevCopilot's Low-Level Design Planning Agent — an expert software architect.
You create detailed technical plans and component breakdowns for implementing changes
in an existing software repository.

RULES:
1. Analyze the existing architecture before proposing changes.
2. Create structured plans with clear sections:
   - **Objective**: What the change accomplishes
   - **Affected Components**: Files, classes, and functions that need modification
   - **New Components**: New files/classes/functions to create
   - **Data Flow**: How data moves through the affected components
   - **Interface Definitions**: Function signatures, API contracts, class interfaces
   - **Dependencies**: External packages or internal modules needed
   - **Implementation Steps**: Ordered list of concrete steps
   - **Testing Strategy**: How to verify the implementation
   - **Risk Assessment**: Potential issues and mitigation strategies
3. Reference specific existing files and components from the graph context.
4. Ensure the plan is actionable and concrete, not vague or theoretical.
5. Use markdown formatting with proper headers and code blocks.

EXISTING ARCHITECTURE:
{graph_context}

RELEVANT CODE:
{code_chunks}
"""

    def __init__(self):
        self.llm = ChatMistralAI(
            model=LLM_MODEL,
            api_key=MISTRAL_API_KEY,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )

    def run(self, state: dict) -> dict:
        """Execute the LLD planning agent."""
        query = state.get("query", "")
        logger = ExplainabilityLogger(query, "lld")

        # Step 1: Analyze affected components
        logger.log_step("analyzing_architecture", "Identifying affected components and dependencies")

        graph_context = state.get("graph_context", "No graph context available.")
        retrieved_chunks = state.get("retrieved_chunks", [])

        if retrieved_chunks:
            logger.log_faiss_retrieval(retrieved_chunks)

        graph_nodes = state.get("graph_nodes", [])
        if graph_nodes:
            node_ids = [n.get("id", "") for n in graph_nodes]
            logger.log_graph_traversal(node_ids, "Components analyzed for design plan")

        # Step 2: Generate plan
        code_chunks_text = self._format_chunks(retrieved_chunks)
        logger.log_conclusion(f"Identified {len(graph_nodes)} relevant components")

        prompt = self.SYSTEM_PROMPT.format(
            graph_context=graph_context,
            code_chunks=code_chunks_text,
        )

        logger.log_llm_call("Low-level design plan generation", LLM_MODEL)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Create a detailed low-level design plan for: {query}"},
        ]

        try:
            response = self.llm.invoke(messages)
            plan_text = response.content

            # Parse plan into structured sections
            plan_dict = self._parse_plan(plan_text)
            logger.log_conclusion("Generated structured design plan")
        except Exception as e:
            plan_text = f"Error generating plan: {str(e)}"
            plan_dict = {}
            logger.log_step("error", str(e))

        return {
            **state,
            "response": plan_text,
            "plan": plan_dict,
            "explanation_log": logger.to_dict(),
            "status": "success",
        }

    def _format_chunks(self, chunks: list[dict]) -> str:
        """Format chunks for architectural analysis."""
        if not chunks:
            return "No existing code available."

        parts = []
        for i, chunk in enumerate(chunks[:6], 1):
            file_path = chunk.get("file_path", "unknown")
            entities = chunk.get("entities", [])
            content = chunk.get("content", "")

            header = f"### Component {i}: {file_path}"
            if entities:
                header += f"\nEntities: {', '.join(entities)}"
            parts.append(f"{header}\n```\n{content[:1000]}\n```")

        return "\n\n".join(parts)

    def _parse_plan(self, plan_text: str) -> dict:
        """Parse plan text into structured sections."""
        sections = {}
        current_section = "overview"
        current_lines = []

        for line in plan_text.split("\n"):
            if line.startswith("## ") or line.startswith("**") and line.endswith("**"):
                if current_lines:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = line.strip("#* ").lower().replace(" ", "_")
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections[current_section] = "\n".join(current_lines).strip()

        return sections
