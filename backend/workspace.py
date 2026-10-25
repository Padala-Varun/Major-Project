"""
Repository Workspace
Each ingested repository gets its own session (knowledge graph, FAISS index,
orchestrator), saved under DATA_DIR so it survives restarts and can be
reopened instantly. Requests name the repo they target, so visitors working
on different repositories never overwrite each other.
"""

import json
import os
import re
import shutil
import threading
import time
from collections import OrderedDict

from networkx.readwrite import json_graph

from config import DATA_DIR, MAX_LOADED_REPOS, MODAL_VOLUME_NAME

REPOS_DIR = os.path.join(DATA_DIR, "repos")
# Bump when ingestion output changes; repos saved by an older version re-index
GRAPH_VERSION = 2

_sessions: "OrderedDict[str, RepoSession]" = OrderedDict()  # LRU of loaded repos
_lock = threading.Lock()
_embedder = None


def repo_id_from_url(url: str) -> str:
    """Stable id for a repository URL: 'https://github.com/Owner/Name.git' → 'owner__name'."""
    m = re.search(r"github\.com[/:]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url.strip())
    if m:
        raw = f"{m.group(1)}__{m.group(2)}"
    else:
        raw = url.strip().rstrip("/").split("/")[-1] or "repo"
    return re.sub(r"[^a-z0-9_.-]", "-", raw.lower())


def get_embedder():
    """Embedders are stateless, so every repo shares one."""
    global _embedder
    if _embedder is None:
        from vector_store.embedder import Embedder
        _embedder = Embedder()
    return _embedder


class RepoSession:
    """Everything needed to answer questions about one repository."""

    def __init__(self, repo_id: str, meta: dict, graph, faiss_store):
        from knowledge_graph.graph_builder import GraphBuilder
        from knowledge_graph.graph_query import GraphQuery
        from agents.orchestrator import Orchestrator

        self.id = repo_id
        self.meta = meta
        self.graph_builder = GraphBuilder()
        self.graph_builder.graph = graph
        self.graph_query = GraphQuery(graph)
        self.faiss_store = faiss_store
        self.orchestrator = Orchestrator(
            graph_query=self.graph_query,
            faiss_store=faiss_store,
            embedder=get_embedder(),
        )

    def details(self) -> dict:
        return {
            "graph": self.graph_builder.get_stats(),
            "faiss": self.faiss_store.get_stats(),
            "repo": {
                "id": self.id,
                "name": self.meta["repo_name"],
                "url": self.meta["repo_url"],
                "file_count": self.meta["file_count"],
                "ingested_at": self.meta.get("ingested_at"),
            },
        }


def _repo_dir(repo_id: str) -> str:
    return os.path.join(REPOS_DIR, repo_id)


def _remember(session: RepoSession):
    with _lock:
        _sessions[session.id] = session
        _sessions.move_to_end(session.id)
        while len(_sessions) > MAX_LOADED_REPOS:
            _sessions.popitem(last=False)


def _commit_volume():
    """Flush writes on a Modal Volume so a restarted container sees them."""
    if not MODAL_VOLUME_NAME:
        return
    try:
        import modal
        modal.Volume.from_name(MODAL_VOLUME_NAME).commit()
    except Exception as e:  # background commits still happen; don't fail ingestion
        print(f"[WORKSPACE] Volume commit skipped: {e}")


def save_session(repo_id: str, repo_data: dict, graph, faiss_store) -> RepoSession:
    """Persist a freshly ingested repo and make it the loaded session."""
    meta = {
        "id": repo_id,
        "repo_name": repo_data["repo_name"],
        "repo_url": repo_data["repo_url"],
        "file_count": repo_data["file_count"],
        "default_branch": repo_data.get("default_branch"),
        "ingested_at": time.time(),
        "graph_version": GRAPH_VERSION,
    }

    # Write to a temp dir and swap, so a crash never leaves a half-written repo
    final_dir = _repo_dir(repo_id)
    tmp_dir = final_dir + ".tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir)

    faiss_store.index_dir = tmp_dir
    faiss_store.save("faiss")
    with open(os.path.join(tmp_dir, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(json_graph.node_link_data(graph, edges="links"), f)
    with open(os.path.join(tmp_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)

    shutil.rmtree(final_dir, ignore_errors=True)
    os.replace(tmp_dir, final_dir)
    faiss_store.index_dir = final_dir
    _commit_volume()

    session = RepoSession(repo_id, meta, graph, faiss_store)
    _remember(session)
    return session


def get_session(repo_id: str) -> RepoSession | None:
    """Loaded session for a repo, reading it from disk if needed."""
    with _lock:
        if repo_id in _sessions:
            _sessions.move_to_end(repo_id)
            return _sessions[repo_id]

    repo_dir = _repo_dir(repo_id)
    meta_path = os.path.join(repo_dir, "meta.json")
    if not os.path.exists(meta_path):
        return None

    from vector_store.faiss_store import FAISSStore

    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("graph_version") != GRAPH_VERSION:
            return None  # built by an older ingestion; the next connect re-indexes it
        with open(os.path.join(repo_dir, "graph.json"), encoding="utf-8") as f:
            graph = json_graph.node_link_graph(json.load(f), edges="links")
        store = FAISSStore(index_dir=repo_dir)
        if not store.load("faiss"):
            return None
    except (OSError, ValueError) as e:
        print(f"[WORKSPACE] Could not load {repo_id}: {e}")
        return None

    session = RepoSession(repo_id, meta, graph, store)
    _remember(session)
    print(f"[WORKSPACE] Loaded {repo_id} from disk")
    return session


def read_extra(repo_id: str, name: str) -> dict | None:
    """A cached artifact saved next to the repo (e.g. its onboarding brief)."""
    path = os.path.join(_repo_dir(repo_id), f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_extra(repo_id: str, name: str, data: dict):
    with open(os.path.join(_repo_dir(repo_id), f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    _commit_volume()


def list_repos() -> list[dict]:
    """Saved repositories, most recently ingested first."""
    repos = []
    if os.path.isdir(REPOS_DIR):
        for name in os.listdir(REPOS_DIR):
            meta_path = os.path.join(REPOS_DIR, name, "meta.json")
            if os.path.exists(meta_path):
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("graph_version") == GRAPH_VERSION:
                    repos.append(meta)
    return sorted(repos, key=lambda m: m.get("ingested_at", 0), reverse=True)
