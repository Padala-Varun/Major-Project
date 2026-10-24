"""
FastAPI API Routes
REST endpoints for DevCopilot: ingestion, querying, status, and graph stats.
Every repository has its own session (see workspace.py); requests name the
repo they target with a `repo` id, falling back to the last one ingested.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import json
import threading
import traceback

import workspace

router = APIRouter()

# ── Request / Response Models ─────────────────────────────

class IngestRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL")
    github_token: Optional[str] = Field(None, description="GitHub access token")
    refresh: bool = Field(False, description="Re-index even if the repo was ingested before")

class ChatTurn(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str

class QueryRequest(BaseModel):
    query: str = Field(..., description="User query")
    history: list[ChatTurn] = Field(default_factory=list, description="Earlier turns, oldest first")
    repo: Optional[str] = Field(None, description="Repo id from /ingest (defaults to the last one)")
    agent_type: Optional[str] = Field(None, description="Force agent: qa, codegen, lld, pr")
    repo_url: Optional[str] = Field(None, description="Repo URL for PR analysis")
    pr_number: Optional[int] = Field(None, description="PR number for analysis")

class QueryResponse(BaseModel):
    response: str
    agent_type: str
    agent_trace: list[str] = []
    steps: list[dict] = []
    code_blocks: list = []
    plan: Optional[dict] = None
    review: Optional[dict] = None
    impact: Optional[dict] = None
    explanation_log: dict = {}
    status: str

class StatusResponse(BaseModel):
    ingested: bool
    repo_id: Optional[str] = None
    repo_name: Optional[str] = None
    status: str
    stage: Optional[str] = None
    details: Optional[dict] = None
    error: Optional[str] = None


# ── Ingestion jobs ────────────────────────────────────────
# One ingestion runs at a time (it is CPU- and API-heavy); status is per repo.
_jobs: dict[str, dict] = {}      # repo id -> {"status", "stage", "error"}
_jobs_lock = threading.Lock()
_last_repo: dict = {"id": None}  # fallback for clients that don't send a repo id


def _active_job() -> Optional[str]:
    return next((rid for rid, j in _jobs.items() if j["status"] == "processing"), None)


def _session_or_404(repo: Optional[str]):
    repo_id = repo or _last_repo["id"]
    session = workspace.get_session(repo_id) if repo_id else None
    if not session:
        raise HTTPException(
            status_code=400,
            detail="This repository isn't loaded. Connect it again to continue.",
        )
    return session


# ── Background Ingestion Worker ───────────────────────────

def _parse_single_file(parser, file_info: dict) -> dict | None:
    """Parse one repository file; returns None on failure."""
    try:
        with open(file_info["full_path"], "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        parsed = parser.parse_file(
            file_info["path"], content, file_info["extension"]
        )
        parsed["content"] = content
        return parsed
    except Exception as parse_err:
        print(f"[INGEST] Warning: Could not parse {file_info['path']}: {parse_err}")
        return None


def _run_ingestion(repo_id: str, repo_url: str, github_token: str = None):
    """Run the heavy ingestion work in a background thread."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from ingestion.cloner import RepoCloner
    from ingestion.parser import CodeParser
    from ingestion.chunker import CodeChunker
    from knowledge_graph.graph_builder import GraphBuilder
    from vector_store.faiss_store import FAISSStore
    from config import GITHUB_TOKEN

    job = _jobs[repo_id]
    try:
        # Step 1: Clone
        print(f"[INGEST] {repo_id} Step 1: Cloning repository...")
        job["stage"] = "clone"
        token = github_token or GITHUB_TOKEN
        cloner = RepoCloner()
        repo_data = cloner.clone(repo_url, token=token)
        print(f"[INGEST] Cloned {repo_data['repo_name']}: {repo_data['file_count']} files")

        # Step 2: Parse files (parallel I/O)
        print("[INGEST] Step 2: Parsing files...")
        job["stage"] = "parse"
        parser = CodeParser()
        parsed_files = []
        workers = min(8, max(1, len(repo_data["files"])))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_parse_single_file, parser, file_info)
                for file_info in repo_data["files"]
            ]
            for future in as_completed(futures):
                parsed = future.result()
                if parsed:
                    parsed_files.append(parsed)
        print(f"[INGEST] Parsed {len(parsed_files)} files")

        # Step 3: Build knowledge graph
        print("[INGEST] Step 3: Building knowledge graph...")
        job["stage"] = "graph"
        graph_builder = GraphBuilder()
        graph = graph_builder.build_from_parsed_files(parsed_files)
        graph_stats = graph_builder.get_stats()
        print(f"[INGEST] Graph: {graph_stats['total_nodes']} nodes, {graph_stats['total_edges']} edges")

        # Step 4: Chunk and embed
        print("[INGEST] Step 4: Chunking code...")
        job["stage"] = "embed"
        chunker = CodeChunker()
        all_chunks = []
        for pf in parsed_files:
            chunks = chunker.chunk_file(pf["file_path"], pf["content"], pf)
            all_chunks.extend(chunks)
        print(f"[INGEST] Created {len(all_chunks)} chunks")

        print("[INGEST] Step 5: Generating embeddings via Mistral API...")
        embeddings = workspace.get_embedder().embed_chunks(all_chunks)
        print(f"[INGEST] Generated {len(embeddings)} embeddings")

        # Step 6: Build FAISS index
        print("[INGEST] Step 6: Building FAISS index...")
        job["stage"] = "index"
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
        print("[INGEST] FAISS index built")

        # Step 7: Save to disk and load the session (graph, index, orchestrator)
        print("[INGEST] Step 7: Saving repository session...")
        workspace.save_session(repo_id, repo_data, graph, faiss_store)
        _last_repo["id"] = repo_id
        job.update(status="done", stage=None)
        print(f"[INGEST] ✅ {repo_id} ingested")

    except Exception as e:
        print(f"[INGEST] ❌ ERROR: {str(e)}")
        traceback.print_exc()
        job.update(status="error", stage=None, error=str(e))


# ── Ingestion Endpoint ────────────────────────────────────

@router.post("/ingest")
async def ingest_repository(req: IngestRequest, background_tasks: BackgroundTasks):
    """Ingest a GitHub repository: clone, parse, build graph, index vectors.
    Returns a repo id at once; poll /api/status?repo=<id> for progress.
    A repo ingested before reopens instantly unless `refresh` is set."""
    repo_id = workspace.repo_id_from_url(req.repo_url)

    if not req.refresh and workspace.get_session(repo_id):
        _last_repo["id"] = repo_id
        return {"status": "done", "repo_id": repo_id, "message": "Repository loaded from cache."}

    with _jobs_lock:
        active = _active_job()
        if active:
            raise HTTPException(
                status_code=409,
                detail={"message": "Another repository is being ingested.", "repo_id": active},
            )
        _jobs[repo_id] = {"status": "processing", "stage": "clone", "error": None}

    # Run heavy work in background so the server stays responsive
    background_tasks.add_task(_run_ingestion, repo_id, req.repo_url, req.github_token)

    return {
        "status": "processing",
        "repo_id": repo_id,
        "message": "Ingestion started in background. Poll /api/status to check progress.",
    }


@router.get("/repos")
async def list_repositories():
    """Repositories saved on this server, most recent first."""
    return {
        "repos": [
            {k: m.get(k) for k in ("id", "repo_name", "repo_url", "file_count", "ingested_at")}
            for m in workspace.list_repos()
        ],
        "processing": _active_job(),
    }


# ── Query Endpoint ────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
def query_repository(req: QueryRequest):
    """Send a query to the multi-agent system."""
    session = _session_or_404(req.repo)

    result = session.orchestrator.process_query(
        query=req.query,
        agent_type=req.agent_type,
        repo_url=req.repo_url or session.meta["repo_url"],
        pr_number=req.pr_number,
        chat_history=[t.model_dump() for t in req.history],
    )

    return QueryResponse(
        response=result.get("response", ""),
        agent_type=result.get("agent_type", "unknown"),
        agent_trace=result.get("agent_trace", []),
        steps=result.get("steps", []),
        code_blocks=result.get("code_blocks", []),
        plan=result.get("plan"),
        review=result.get("review"),
        impact=result.get("impact"),
        explanation_log=result.get("explanation_log", {}),
        status=result.get("status", "success"),
    )


@router.post("/query/stream")
def query_repository_stream(req: QueryRequest):
    """Like /query, but streams agent progress as Server-Sent Events.
    The last event has type "final" and carries the full /query response."""
    session = _session_or_404(req.repo)

    events = session.orchestrator.stream_query(
        query=req.query,
        agent_type=req.agent_type,
        repo_url=req.repo_url or session.meta["repo_url"],
        pr_number=req.pr_number,
        chat_history=[t.model_dump() for t in req.history],
    )
    sse = (f"data: {json.dumps(event, default=str)}\n\n" for event in events)
    return StreamingResponse(sse, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Status Endpoint ──────────────────────────────────────

@router.get("/status", response_model=StatusResponse)
def get_status(repo: Optional[str] = None):
    """Ingestion progress and stats for one repository (default: the last ingested)."""
    repo_id = repo or _last_repo["id"]
    job = _jobs.get(repo_id) if repo_id else None

    if job and job["status"] == "processing":
        return StatusResponse(ingested=False, repo_id=repo_id, status="processing", stage=job["stage"])

    session = workspace.get_session(repo_id) if repo_id else None
    if session:
        return StatusResponse(
            ingested=True,
            repo_id=repo_id,
            repo_name=session.meta["repo_name"],
            status="done",
            details=session.details(),
        )

    if job and job["status"] == "error":
        return StatusResponse(ingested=False, repo_id=repo_id, status="error", error=job["error"])

    return StatusResponse(ingested=False, repo_id=repo_id, status="idle")


# ── Architecture Map Endpoint ─────────────────────────────

@router.get("/graph")
def get_graph_map(repo: Optional[str] = None):
    """File-level dependency map with modules, entry points and risk scores."""
    from knowledge_graph.graph_map import build_map

    session = _session_or_404(repo)
    if not hasattr(session, "map_cache"):
        session.map_cache = build_map(session.graph_builder.graph)
    return session.map_cache


# ── Graph Stats Endpoint ─────────────────────────────────

@router.get("/graph-stats")
def get_graph_stats(repo: Optional[str] = None):
    """Get knowledge graph statistics."""
    session = _session_or_404(repo)
    stats = session.graph_builder.get_stats()

    # Add some sample nodes for visualization
    stats["sample_files"] = [
        {"id": n["id"], "name": n.get("name", ""), "path": n.get("path", "")}
        for n in session.graph_query.find_nodes_by_type("file")[:20]
    ]
    stats["sample_classes"] = [
        {"id": n["id"], "name": n.get("name", ""), "file": n.get("file_path", "")}
        for n in session.graph_query.find_nodes_by_type("class")[:20]
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
