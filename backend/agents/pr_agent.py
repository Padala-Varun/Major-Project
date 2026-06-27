"""
Pull Request Analysis Agent
Reviews and summarizes code changes, identifies impacted components,
traces dependencies, and highlights potential risks.
"""

import requests
from langchain_mistralai import ChatMistralAI
from config import MISTRAL_API_KEY, GITHUB_TOKEN, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS
from explainability.logger import ExplainabilityLogger


class PRAgent:
    """Analyzes pull requests for impact, risks, and quality."""

    SYSTEM_PROMPT = """You are DevCopilot's Pull Request Analysis Agent — an expert code reviewer.
You analyze pull request changes to help developers understand impact, quality, and risks.

RULES:
1. Summarize what the PR changes at a high level.
2. List all modified, added, and deleted files.
3. For each significant change, explain:
   - What was changed and why (inferred from context)
   - Which components are impacted (from the knowledge graph)
   - Potential risks or side effects
4. Flag potential issues:
   - Breaking changes to public APIs
   - Missing error handling
   - Unhandled edge cases
   - Security concerns
   - Performance implications
5. Suggest improvements if applicable.
6. Use markdown formatting with clear sections.

KNOWLEDGE GRAPH CONTEXT (existing architecture):
{graph_context}

RELEVANT CODE CONTEXT:
{code_chunks}

PULL REQUEST DIFF:
{pr_diff}

PR METADATA:
{pr_metadata}
"""

    def __init__(self):
        self.llm = ChatMistralAI(
            model=LLM_MODEL,
            api_key=MISTRAL_API_KEY,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )

    def run(self, state: dict) -> dict:
        """Execute the PR analysis agent."""
        query = state.get("query", "")
        repo_url = state.get("repo_url", "")
        pr_number = state.get("pr_number")
        logger = ExplainabilityLogger(query, "pr")

        if not repo_url:
            return {
                **state,
                "response": "**No repository URL provided.** Please enter a GitHub repository URL in the PR Analysis fields above and try again.",
                "explanation_log": logger.to_dict(),
                "status": "error",
            }

        # If no PR number, list available PRs
        if not pr_number:
            logger.log_step("listing_prs", f"Listing available PRs for {repo_url}")
            pr_list = self._list_prs(repo_url)
            if pr_list.get("error"):
                return {
                    **state,
                    "response": f"Error listing PRs: {pr_list['error']}",
                    "explanation_log": logger.to_dict(),
                    "status": "error",
                }

            prs = pr_list.get("prs", [])
            if not prs:
                return {
                    **state,
                    "response": f"**No open pull requests found** for this repository.\n\nTry checking if the repository has any PRs (open or closed) on GitHub, or provide a specific PR number.",
                    "explanation_log": logger.to_dict(),
                    "status": "success",
                }

            # Format PR list
            lines = [f"### 📋 Available Pull Requests ({len(prs)} found)\n"]
            for pr in prs:
                lines.append(
                    f"- **PR #{pr['number']}**: {pr['title']}  \n"
                    f"  by `{pr['author']}` — {pr['state']} — "
                    f"+{pr['additions']}/-{pr['deletions']} in {pr['changed_files']} files"
                )
            lines.append("\n\n💡 **Enter a PR number** in the field above and ask again to analyze a specific PR.")

            return {
                **state,
                "response": "\n".join(lines),
                "explanation_log": logger.to_dict(),
                "status": "success",
            }

        # Step 1: Fetch PR data
        logger.log_step("fetching_pr", f"Fetching PR #{pr_number} from {repo_url}")

        pr_data = self._fetch_pr_data(repo_url, pr_number)
        if pr_data.get("error"):
            # Try listing available PRs as a helpful fallback
            pr_list = self._list_prs(repo_url)
            prs = pr_list.get("prs", [])
            if prs:
                pr_nums = ", ".join([f"#{p['number']}" for p in prs[:10]])
                fallback = f"\n\n**Available PRs:** {pr_nums}\n\nEnter one of these PR numbers and try again."
            else:
                fallback = "\n\nThis repository doesn't appear to have any open PRs."

            return {
                **state,
                "response": f"**PR #{pr_number} not found.**{fallback}",
                "explanation_log": logger.to_dict(),
                "status": "error",
                "error": pr_data["error"],
            }

        logger.log_step("pr_fetched", {
            "title": pr_data.get("title", ""),
            "files_changed": pr_data.get("changed_files", 0),
        })

        # Step 2: Map changed files to graph
        graph_context = state.get("graph_context", "No graph context available.")
        retrieved_chunks = state.get("retrieved_chunks", [])

        if retrieved_chunks:
            logger.log_faiss_retrieval(retrieved_chunks)

        graph_nodes = state.get("graph_nodes", [])
        if graph_nodes:
            node_ids = [n.get("id", "") for n in graph_nodes]
            logger.log_graph_traversal(node_ids, "Components impacted by PR")

        # Step 3: Analyze PR
        code_chunks_text = self._format_chunks(retrieved_chunks)
        pr_diff = pr_data.get("diff", "No diff available.")
        pr_metadata = self._format_pr_metadata(pr_data)

        logger.log_conclusion(f"PR modifies {pr_data.get('changed_files', 0)} files")

        prompt = self.SYSTEM_PROMPT.format(
            graph_context=graph_context,
            code_chunks=code_chunks_text,
            pr_diff=pr_diff[:8000],  # Limit diff size
            pr_metadata=pr_metadata,
        )

        logger.log_llm_call("PR impact analysis", LLM_MODEL)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Analyze this pull request: {query}"},
        ]

        try:
            response = self.llm.invoke(messages)
            analysis = response.content
            logger.log_conclusion("PR analysis completed successfully")
        except Exception as e:
            analysis = f"Error analyzing PR: {str(e)}"
            logger.log_step("error", str(e))

        return {
            **state,
            "response": analysis,
            "explanation_log": logger.to_dict(),
            "status": "success",
        }

    def _list_prs(self, repo_url: str) -> dict:
        """List available PRs for a repository."""
        try:
            parts = repo_url.rstrip("/").removesuffix(".git").split("/")
            owner, repo = parts[-2], parts[-1]

            headers = {"Accept": "application/vnd.github.v3+json"}
            if GITHUB_TOKEN and len(GITHUB_TOKEN) > 10:
                headers["Authorization"] = f"token {GITHUB_TOKEN}"

            # Fetch both open and closed PRs
            url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all&per_page=20"
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            prs = resp.json()

            return {
                "prs": [
                    {
                        "number": pr.get("number"),
                        "title": pr.get("title", ""),
                        "state": pr.get("state", ""),
                        "author": pr.get("user", {}).get("login", ""),
                        "additions": pr.get("additions", 0),
                        "deletions": pr.get("deletions", 0),
                        "changed_files": pr.get("changed_files", 0),
                    }
                    for pr in prs
                ]
            }
        except Exception as e:
            return {"error": str(e)}

    def _fetch_pr_data(self, repo_url: str, pr_number: int) -> dict:
        """Fetch PR data from GitHub API."""
        try:
            # Parse owner/repo from URL
            parts = repo_url.rstrip("/").removesuffix(".git").split("/")
            owner, repo = parts[-2], parts[-1]

            headers = {"Accept": "application/vnd.github.v3+json"}
            if GITHUB_TOKEN and len(GITHUB_TOKEN) > 10:
                headers["Authorization"] = f"token {GITHUB_TOKEN}"

            # Fetch PR details
            pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
            pr_resp = requests.get(pr_url, headers=headers, timeout=15)
            pr_resp.raise_for_status()
            pr_info = pr_resp.json()

            # Fetch PR diff
            diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
            diff_resp = requests.get(pr_url, headers=diff_headers, timeout=15)
            diff_text = diff_resp.text if diff_resp.ok else "Could not fetch diff."

            # Fetch changed files
            files_url = f"{pr_url}/files"
            files_resp = requests.get(files_url, headers=headers, timeout=15)
            files = files_resp.json() if files_resp.ok else []

            return {
                "title": pr_info.get("title", ""),
                "body": pr_info.get("body", ""),
                "state": pr_info.get("state", ""),
                "author": pr_info.get("user", {}).get("login", ""),
                "changed_files": pr_info.get("changed_files", 0),
                "additions": pr_info.get("additions", 0),
                "deletions": pr_info.get("deletions", 0),
                "files": [
                    {
                        "filename": f.get("filename", ""),
                        "status": f.get("status", ""),
                        "additions": f.get("additions", 0),
                        "deletions": f.get("deletions", 0),
                    }
                    for f in files[:50]
                ],
                "diff": diff_text,
            }
        except Exception as e:
            return {"error": str(e)}

    def _format_pr_metadata(self, pr_data: dict) -> str:
        """Format PR metadata for the prompt."""
        lines = [
            f"Title: {pr_data.get('title', 'N/A')}",
            f"Author: {pr_data.get('author', 'N/A')}",
            f"State: {pr_data.get('state', 'N/A')}",
            f"Files Changed: {pr_data.get('changed_files', 0)}",
            f"Additions: +{pr_data.get('additions', 0)}",
            f"Deletions: -{pr_data.get('deletions', 0)}",
            "",
            "Changed Files:",
        ]
        for f in pr_data.get("files", [])[:20]:
            lines.append(f"  {f.get('status', '?')} {f.get('filename', '?')} "
                         f"(+{f.get('additions', 0)} -{f.get('deletions', 0)})")
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
