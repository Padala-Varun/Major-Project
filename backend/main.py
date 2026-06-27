"""
DevCopilot Backend — FastAPI Application
Main entry point for the DevCopilot API server.
"""

import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import CORS_ORIGINS, API_HOST, API_PORT
from api.routes import router

# ── FastAPI App ───────────────────────────────────────────

app = FastAPI(
    title="DevCopilot API",
    description="AI-Powered Multi-Agent Codebase Assistant — "
                "Graph-based RAG with LangGraph orchestration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────
app.include_router(router, prefix="/api")


# ── Health Check ──────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name": "DevCopilot API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ── Main ──────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    # Opt-in only: reload watches .venv inside backend/ and restarts mid-ingestion.
    dev_reload = os.getenv("DEV_RELOAD", "").lower() in ("1", "true", "yes")

    reload_dirs = [
        os.path.join(backend_dir, name)
        for name in (
            "api",
            "agents",
            "ingestion",
            "knowledge_graph",
            "vector_store",
            "explainability",
        )
    ]

    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=dev_reload,
        reload_dirs=reload_dirs if dev_reload else None,
        reload_includes=["*.py"],
        reload_excludes=[
            "**/.venv/**",
            "**/__pycache__/**",
            "**/*.pyc",
        ],
    )
