"""
Change Preparation
Turns the Engineer's code blocks into complete files ready to commit or test.
Each existing file is fetched from GitHub; if a block only contains part of
it (a changed function, say), an LLM merges the fragment into the full file
so committing never wipes out the rest of the file. Every file gets a diff.
"""

import base64
import difflib
import re

import requests

from agents.llm import make_llm

MAX_MERGE_LINES = 1500   # larger files are flagged for manual review instead of merged
DEF_PATTERN = re.compile(
    r"^\s*(?:async\s+def|def|class|function|export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let)"
    r"|(?:public|private|protected)\s+[\w<>\[\]]+\s+)\s*(\w+)",
    re.MULTILINE,
)

MERGE_PROMPT = """You apply a code change to an existing file.

Below is the CURRENT file and a CHANGE written by another engineer for this task:
{task}

The change may be a fragment (one function, one class, a few lines) rather than the whole
file. Return the COMPLETE updated file: apply the change, and keep everything else exactly
as it is (same imports, order, formatting and comments). If the change adds new imports,
put them with the existing imports.

Return only the file content. No markdown fences, no explanations.

CURRENT FILE ({path}):
{original}

CHANGE:
{fragment}"""


def parse_repo(repo_url: str) -> tuple[str, str]:
    parts = repo_url.rstrip("/").removesuffix(".git").split("/")
    return parts[-2], parts[-1]


def fetch_file(owner: str, repo: str, path: str, ref: str | None, token: str | None) -> str | None:
    """Current content of a repository file, or None if it doesn't exist."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {"ref": ref} if ref else {}
    resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                        headers=headers, params=params, timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) or data.get("encoding") != "base64":
        return None  # a directory, or too large for the contents API
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def _definitions(code: str) -> set[str]:
    return set(DEF_PATTERN.findall(code))


def is_fragment(original: str, new: str) -> bool:
    """Whether `new` looks like part of `original` rather than a full replacement."""
    orig_lines = [ln for ln in original.splitlines() if ln.strip()]
    new_lines = [ln for ln in new.splitlines() if ln.strip()]
    if len(orig_lines) < 15:
        return False  # small files are usually rewritten whole
    missing = _definitions(original) - _definitions(new)
    orig_defs = _definitions(original)
    if orig_defs and len(missing) >= max(1, len(orig_defs) // 3):
        return True
    return len(new_lines) < 0.6 * len(orig_lines)


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```[\w+-]*\n(.*?)\n```$", text, re.DOTALL)
    return m.group(1) if m else text


def keep_blank_lines(original: str, merged: str) -> str:
    """Undo blank-line-only edits an LLM merge made, so diffs show only real changes."""
    a, b = original.splitlines(), merged.splitlines()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "delete" and all(not ln.strip() for ln in a[i1:i2]):
            out.extend(a[i1:i2])          # blank lines the merge dropped
        elif op == "insert" and all(not ln.strip() for ln in b[j1:j2]):
            continue                      # blank lines the merge added
        elif op == "replace":
            # Keep the original's blank lines around an edited region
            seg = b[j1:j2]
            while seg and not seg[0].strip():
                seg = seg[1:]
            while seg and not seg[-1].strip():
                seg = seg[:-1]
            lead = next((k for k, ln in enumerate(a[i1:i2]) if ln.strip()), i2 - i1)
            trail = next((k for k, ln in enumerate(reversed(a[i1:i2])) if ln.strip()), 0)
            out.extend(a[i1:i1 + lead] + seg + (a[i2 - trail:i2] if trail and seg else []))
        else:
            out.extend(b[j1:j2])
    return "\n".join(out)


def unified_diff(original: str, new: str, path: str) -> tuple[str, int, int]:
    lines = list(difflib.unified_diff(
        original.splitlines(), new.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="", n=3,
    ))
    added = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
    return "\n".join(lines), added, removed


def prepare_changes(repo_url: str, blocks: list[dict], task: str, token: str | None = None,
                    ref: str | None = None, base_files: list[dict] | None = None) -> list[dict]:
    """Complete file contents and diffs for the code blocks that name a file.

    `base_files` is an earlier prepared change set (a follow-up fix builds on
    it): its files are the starting point instead of the repository's versions,
    and files this round doesn't touch are carried forward unchanged. Diffs are
    always against the repository, so the result is the whole cumulative change.
    """
    owner, repo = parse_repo(repo_url)
    base = {f["path"]: f for f in base_files or []}
    merger = None
    files = []

    for block in blocks:
        path = (block.get("filename") or "").strip().lstrip("./")
        code = block.get("code", "")
        if not path or not code.strip():
            continue

        repo_version = fetch_file(owner, repo, path, ref, token)
        start = base[path]["content"] if path in base else repo_version
        entry = {"path": path, "language": block.get("language", "text"), "merged": False, "note": None,
                 "status": "new" if repo_version is None else "modified"}

        if start is None:
            content = code
        elif is_fragment(start, code):
            if start.count("\n") > MAX_MERGE_LINES:
                content = code
                entry.update(status="fragment", note="Partial change to a large file; review before committing.")
            else:
                merger = merger or make_llm(0.0)
                content = keep_blank_lines(start, _strip_fences(merger.invoke(MERGE_PROMPT.format(
                    task=task, path=path, original=start, fragment=code)).content))
                entry.update(merged=True, note="The change was merged into the existing file.")
        else:
            content = code

        entry["content"] = content.rstrip("\n") + "\n"
        diff, added, removed = unified_diff(repo_version or "", entry["content"], path)
        entry.update(diff=diff, additions=added, deletions=removed)
        files.append(entry)

    touched = {f["path"] for f in files}
    carried = [{**f, "note": "Unchanged from the previous round."} for p, f in base.items() if p not in touched]
    return carried + files
