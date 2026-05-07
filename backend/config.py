"""
DevCopilot Configuration
Central configuration for models, embeddings, chunking, and graph settings.
"""

import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# ── LLM Settings ─────────────────────────────────────────
LLM_MODEL = "gemini-2.5-flash"
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 8192

# ── Embedding Settings ───────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# ── Chunking Settings ────────────────────────────────────
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
MAX_FILE_SIZE_KB = 500  # skip files larger than this

# ── Repository Settings ──────────────────────────────────
# Use system temp dir to avoid triggering Uvicorn's file watcher
_TEMP_BASE = os.path.join(tempfile.gettempdir(), "devcopilot")
CLONE_DIR = os.path.join(_TEMP_BASE, "repos")
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".c",
    ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".scala", ".cs", ".vue", ".svelte", ".html", ".css", ".scss",
    ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini",
}
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "vendor", ".tox",
    "egg-info", ".eggs", ".mypy_cache", ".pytest_cache",
}

# ── Graph Settings ────────────────────────────────────────
NODE_TYPES = ["file", "class", "function", "module", "variable"]
EDGE_TYPES = ["contains", "imports", "calls", "inherits", "uses"]

# ── FAISS Settings ────────────────────────────────────────
FAISS_INDEX_DIR = os.path.join(_TEMP_BASE, "faiss_indices")
TOP_K_RESULTS = 10

# ── Server Settings ──────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
CORS_ORIGINS = ["*"]
