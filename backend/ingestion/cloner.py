"""
Repository Cloner
Clones GitHub repositories and extracts file metadata.
"""

import os
import shutil
import stat
from typing import Optional
from git import Repo
from config import CLONE_DIR, SUPPORTED_EXTENSIONS, SKIP_DIRS, MAX_FILE_SIZE_KB


def _force_remove_readonly(func, path, _exc_info):
    """Error handler for shutil.rmtree on Windows — clears read-only flag and retries."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


class RepoCloner:
    """Handles cloning GitHub repositories and extracting file listings."""

    def __init__(self, clone_dir: str = CLONE_DIR):
        self.clone_dir = clone_dir
        os.makedirs(self.clone_dir, exist_ok=True)

    def clone(self, repo_url: str, token: Optional[str] = None) -> dict:
        """
        Clone a GitHub repository and return metadata.

        Args:
            repo_url: GitHub repository URL (e.g., https://github.com/user/repo)
            token: Optional GitHub token for private repos

        Returns:
            dict with repo_name, local_path, file_count, files list
        """
        repo_name = self._extract_repo_name(repo_url)
        local_path = os.path.join(self.clone_dir, repo_name)

        # Clean up existing clone
        if os.path.exists(local_path):
            shutil.rmtree(local_path, onerror=_force_remove_readonly)

        # Inject token for private repos (validate token first)
        clone_url = repo_url
        if not clone_url.endswith(".git"):
            clone_url += ".git"

        is_valid_token = (
            token
            and token.strip()
            and token not in ("your_github_token_here", "your_token_here", "")
            and len(token.strip()) > 10
        )

        if is_valid_token and "github.com" in repo_url:
            clone_url = clone_url.replace(
                "https://github.com",
                f"https://{token.strip()}@github.com"
            )

        # Clone with depth=1 for speed
        repo = Repo.clone_from(clone_url, local_path, depth=1)

        # Collect file listing
        files = self._collect_files(local_path)

        return {
            "repo_name": repo_name,
            "repo_url": repo_url,
            "local_path": local_path,
            "default_branch": str(repo.active_branch),
            "file_count": len(files),
            "files": files,
        }

    def _extract_repo_name(self, url: str) -> str:
        """Extract 'owner-repo' from GitHub URL."""
        url = url.rstrip("/").removesuffix(".git")
        parts = url.split("/")
        return f"{parts[-2]}_{parts[-1]}" if len(parts) >= 2 else parts[-1]

    def _collect_files(self, root_path: str) -> list[dict]:
        """Walk directory tree and collect supported source files."""
        files = []
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Skip unwanted directories
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, root_path)
                size_kb = os.path.getsize(full_path) / 1024

                if size_kb > MAX_FILE_SIZE_KB:
                    continue

                files.append({
                    "path": rel_path.replace("\\", "/"),
                    "full_path": full_path,
                    "extension": ext,
                    "size_kb": round(size_kb, 2),
                })

        return files

    def cleanup(self, repo_name: str):
        """Remove a cloned repository."""
        local_path = os.path.join(self.clone_dir, repo_name)
        if os.path.exists(local_path):
            shutil.rmtree(local_path, onerror=_force_remove_readonly)
