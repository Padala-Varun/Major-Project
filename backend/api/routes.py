"""
FastAPI API Routes
REST endpoints for DevCopilot: ingestion, querying, status, and graph stats.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
import os
import traceback

router = APIRouter()

# ── Request / Response Models ─────────────────────────────

class IngestRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL")
    github_token: Optional[str] = Field(None, description="GitHub access token")

class QueryRequest(BaseModel):
    query: str = Field(..., description="User query")
    agent_type: Optional[str] = Field(None, description="Force agent: qa, codegen, lld, pr")
    repo_url: Optional[str] = Field(None, description="Repo URL for PR analysis")
    pr_number: Optional[int] = Field(None, description="PR number for analysis")

class IngestResponse(BaseModel):
    status: str
    repo_name: str
    file_count: int
    graph_nodes: int
    graph_edges: int
    chunks_indexed: int
    message: str

class QueryResponse(BaseModel):
    response: str
    agent_type: str
    code_blocks: list = []
    plan: Optional[dict] = None
    explanation_log: dict = {}
    status: str

class StatusResponse(BaseModel):
    ingested: bool
    repo_name: Optional[str] = None
    status: str
    details: Optional[dict] = None


# ── Global state (set by main.py on startup) ─────────────
# These are populated by the app's lifespan or ingestion endpoint
_app_state = {
    "ingested": False,
    "repo_name": None,
    "repo_data": None,
    "graph_builder": None,
    "graph_query": None,
    "faiss_store": None,
    "embedder": None,
    "orchestrator": None,
    "ingestion_status": "idle",  # idle, processing, done, error
    "ingestion_error": None,
}


def get_state():
    return _app_state


def set_state(key, value):
    _app_state[key] = value


# ── Ingestion Endpoint ────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
async def ingest_repository(req: IngestRequest, background_tasks: BackgroundTasks):
    """Ingest a GitHub repository: clone, parse, build graph, index vectors."""
    from ingestion.cloner import RepoCloner
    from ingestion.parser import CodeParser
    from ingestion.chunker import CodeChunker
    from knowledge_graph.graph_builder import GraphBuilder
    from knowledge_graph.graph_query import GraphQuery
    from vector_store.embedder import Embedder
    from vector_store.faiss_store import FAISSStore
    from agents.orchestrator import Orchestrator
    from config import GITHUB_TOKEN

    if _app_state["ingestion_status"] == "processing":
        raise HTTPException(status_code=409, detail="Ingestion already in progress")

    _app_state["ingestion_status"] = "processing"

    try:
        # Step 1: Clone
        print("[INGEST] Step 1: Cloning repository...")
        token = req.github_token or GITHUB_TOKEN
        cloner = RepoCloner()
        repo_data = cloner.clone(req.repo_url, token=token)
        print(f"[INGEST] Cloned {repo_data['repo_name']}: {repo_data['file_count']} files")

        # Step 2: Parse files
        print("[INGEST] Step 2: Parsing files...")
        parser = CodeParser()
        parsed_files = []
        for file_info in repo_data["files"]:
            try:
                with open(file_info["full_path"], "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                parsed = parser.parse_file(
                    file_info["path"], content, file_info["extension"]
                )
                parsed_files.append(parsed)
            except Exception as parse_err:
                print(f"[INGEST] Warning: Could not parse {file_info['path']}: {parse_err}")
                continue
        print(f"[INGEST] Parsed {len(parsed_files)} files")

        # Step 3: Build knowledge graph
        print("[INGEST] Step 3: Building knowledge graph...")
        graph_builder = GraphBuilder()
        graph = graph_builder.build_from_parsed_files(parsed_files)
        graph_query_obj = GraphQuery(graph)
        graph_stats = graph_builder.get_stats()
        print(f"[INGEST] Graph: {graph_stats['total_nodes']} nodes, {graph_stats['total_edges']} edges")

        # Step 4: Chunk and embed
        print("[INGEST] Step 4: Chunking code...")
        chunker = CodeChunker()
        all_chunks = []
        for pf in parsed_files:
            chunks = chunker.chunk_file(pf["file_path"], pf["content"], pf)
            all_chunks.extend(chunks)
        print(f"[INGEST] Created {len(all_chunks)} chunks")

        print("[INGEST] Step 5: Generating embeddings (this may take a moment)...")
        embedder = Embedder()
        embeddings = embedder.embed_chunks(all_chunks)
        print(f"[INGEST] Generated {len(embeddings)} embeddings")

        # Step 6: Build FAISS index
        print("[INGEST] Step 6: Building FAISS index...")
        faiss_store = FAISSStore()
        chunk_metadata = [
            {
                "file_path": c["file_path"],
                "content": c["content"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
                "language": c["language"],
                "entities": c["entities"],
            }
            for c in all_chunks
        ]
        faiss_store.build_index(embeddings, chunk_metadata)
        faiss_store.save(name="default")
        print("[INGEST] FAISS index built and saved")

        # Step 7: Initialize orchestrator
        print("[INGEST] Step 7: Initializing orchestrator...")
        orchestrator = Orchestrator(
            graph_query=graph_query_obj,
            faiss_store=faiss_store,
            embedder=embedder,
        )
        print("[INGEST] Orchestrator ready")

        # Update global state
        _app_state.update({
            "ingested": True,
            "repo_name": repo_data["repo_name"],
            "repo_data": repo_data,
            "graph_builder": graph_builder,
            "graph_query": graph_query_obj,
            "faiss_store": faiss_store,
            "embedder": embedder,
            "orchestrator": orchestrator,
            "ingestion_status": "done",
            "ingestion_error": None,
        })

        print("[INGEST] ✅ Ingestion complete!")
        return IngestResponse(
            status="success",
            repo_name=repo_data["repo_name"],
            file_count=repo_data["file_count"],
            graph_nodes=graph_stats["total_nodes"],
            graph_edges=graph_stats["total_edges"],
            chunks_indexed=len(all_chunks),
            message=f"Successfully ingested {repo_data['repo_name']} with "
                    f"{graph_stats['total_nodes']} nodes and {len(all_chunks)} chunks.",
        )

    except Exception as e:
        print(f"[INGEST] ❌ ERROR: {str(e)}")
        traceback.print_exc()
        _app_state["ingestion_status"] = "error"
        _app_state["ingestion_error"] = str(e)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


# ── Query Endpoint ────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_repository(req: QueryRequest):
    """Send a query to the multi-agent system."""
    if not _app_state["ingested"] or not _app_state["orchestrator"]:
        raise HTTPException(
            status_code=400,
            detail="No repository ingested. Please ingest a repository first."
        )

    orchestrator = _app_state["orchestrator"]

    result = orchestrator.process_query(
        query=req.query,
        agent_type=req.agent_type,
        repo_url=req.repo_url or (_app_state["repo_data"] or {}).get("repo_url"),
        pr_number=req.pr_number,
    )

    return QueryResponse(
        response=result.get("response", ""),
        agent_type=result.get("agent_type", "unknown"),
        code_blocks=result.get("code_blocks", []),
        plan=result.get("plan"),
        explanation_log=result.get("explanation_log", {}),
        status=result.get("status", "success"),
    )


# ── Status Endpoint ──────────────────────────────────────

@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Get the current system status."""
    details = {}
    if _app_state["ingested"]:
        if _app_state["graph_builder"]:
            details["graph"] = _app_state["graph_builder"].get_stats()
        if _app_state["faiss_store"]:
            details["faiss"] = _app_state["faiss_store"].get_stats()
        if _app_state["repo_data"]:
            details["repo"] = {
                "name": _app_state["repo_data"]["repo_name"],
                "file_count": _app_state["repo_data"]["file_count"],
                "url": _app_state["repo_data"]["repo_url"],
            }

    return StatusResponse(
        ingested=_app_state["ingested"],
        repo_name=_app_state.get("repo_name"),
        status=_app_state["ingestion_status"],
        details=details if details else None,
    )


# ── Graph Stats Endpoint ─────────────────────────────────

@router.get("/graph-stats")
async def get_graph_stats():
    """Get knowledge graph statistics."""
    if not _app_state["ingested"] or not _app_state["graph_builder"]:
        raise HTTPException(status_code=400, detail="No repository ingested.")

    stats = _app_state["graph_builder"].get_stats()

    # Add some sample nodes for visualization
    graph_query = _app_state["graph_query"]
    if graph_query:
        stats["sample_files"] = [
            {"id": n["id"], "name": n.get("name", ""), "path": n.get("path", "")}
            for n in graph_query.find_nodes_by_type("file")[:20]
        ]
        stats["sample_classes"] = [
            {"id": n["id"], "name": n.get("name", ""), "file": n.get("file_path", "")}
            for n in graph_query.find_nodes_by_type("class")[:20]
        ]

    return stats


# ── Create PR Endpoint ───────────────────────────────────

class PRFileItem(BaseModel):
    path: str = Field(..., description="File path in the repo (e.g., src/auth/login.py)")
    content: str = Field(..., description="File content to commit")

class CreatePRRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL")
    github_token: Optional[str] = Field(None, description="GitHub access token")
    files: list[PRFileItem] = Field(..., description="Files to commit")
    branch_name: Optional[str] = Field(None, description="Branch name (auto-generated if empty)")
    commit_message: str = Field("Add code generated by DevCopilot", description="Commit message")
    pr_title: str = Field("DevCopilot: Generated Code", description="PR title")
    pr_body: Optional[str] = Field(None, description="PR description")


@router.post("/create-pr")
async def create_pr_endpoint(req: CreatePRRequest):
    """Create a GitHub Pull Request with generated code."""
    from api.github_pr import create_pull_request
    from config import GITHUB_TOKEN as DEFAULT_TOKEN

    token = req.github_token or DEFAULT_TOKEN

    files = [{"path": f.path, "content": f.content} for f in req.files]

    result = create_pull_request(
        repo_url=req.repo_url,
        files=files,
        branch_name=req.branch_name or None,
        commit_message=req.commit_message,
        pr_title=req.pr_title,
        pr_body=req.pr_body or "",
        github_token=token,
    )

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result
