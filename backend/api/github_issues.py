"""
GitHub Issues
Fetches an issue (title, body, labels, recent comments) so the agent team can fix it.
"""

import re

import requests

from config import GITHUB_TOKEN

ISSUE_URL = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/issues/(\d+)")
MAX_BODY_CHARS = 4000
MAX_COMMENTS = 5


def parse_issue_ref(ref: str, repo_url: str) -> tuple[str, str, int] | None:
    """(owner, repo, number) from an issue URL, or from "#123"/"123" for the connected repo."""
    m = ISSUE_URL.search(ref)
    if m:
        return m.group(1), m.group(2).removesuffix(".git"), int(m.group(3))
    m = re.fullmatch(r"\s*#?(\d+)\s*", ref)
    if m:
        parts = repo_url.rstrip("/").removesuffix(".git").split("/")
        return parts[-2], parts[-1], int(m.group(1))
    return None


def fetch_issue(owner: str, repo: str, number: int, token: str | None = None) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = token or GITHUB_TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"

    resp = requests.get(base, headers=headers, timeout=15)
    if resp.status_code == 404:
        return {"error": f"Issue #{number} wasn't found in {owner}/{repo}."}
    if not resp.ok:
        return {"error": f"Couldn't read issue #{number}: {resp.json().get('message', resp.status_code)}"}
    issue = resp.json()
    if "pull_request" in issue:
        return {"error": f"#{number} is a pull request, not an issue. Use Review PR mode for it."}

    comments = []
    if issue.get("comments"):
        c = requests.get(f"{base}/comments", headers=headers, params={"per_page": MAX_COMMENTS}, timeout=15)
        if c.ok:
            comments = [{"author": x["user"]["login"], "body": (x.get("body") or "")[:1500]} for x in c.json()]

    return {
        "number": number,
        "title": issue.get("title", ""),
        "body": (issue.get("body") or "")[:MAX_BODY_CHARS],
        "state": issue.get("state"),
        "labels": [lbl["name"] for lbl in issue.get("labels", [])],
        "author": issue.get("user", {}).get("login"),
        "url": issue.get("html_url"),
        "repo": f"{owner}/{repo}",
        "comments": comments,
    }


def issue_task(issue: dict) -> str:
    """The request the agent team works from when fixing an issue."""
    parts = [f"Fix GitHub issue #{issue['number']}: {issue['title']}", "", issue["body"] or "(no description)"]
    if issue["comments"]:
        parts += ["", "Discussion on the issue:"]
        parts += [f"- {c['author']}: {c['body'][:600]}" for c in issue["comments"]]
    parts += [
        "",
        "Find the cause in this codebase, plan the fix, and implement it as complete files with "
        "their repository paths. Add or update tests if the repository has a test suite.",
    ]
    return "\n".join(parts)
