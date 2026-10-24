"""
Change Impact Analysis
Given the files a change touches, walks the import graph backwards to find
every file that depends on them, and rates the change's risk with reasons.
"""

from collections import deque

MAX_DEPTH = 3        # dependents of dependents of dependents
MAX_LISTED = 50      # affected files returned to the client


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _match_file(path: str, by_path: dict[str, dict]) -> dict | None:
    """Repo file a generated path refers to: exact, or a unique suffix match
    ("flask/helpers.py" → "src/flask/helpers.py")."""
    p = _norm(path)
    if p in by_path:
        return by_path[p]
    hits = [n for k, n in by_path.items() if k.endswith("/" + p)]
    return hits[0] if len(hits) == 1 else None


def analyze_impact(map_data: dict, changed_paths: list[str]) -> dict | None:
    """Impact of changing `changed_paths`, using the architecture map (graph_map.build_map)."""
    paths = list(dict.fromkeys(p for p in changed_paths if p))
    if not paths:
        return None

    nodes = map_data["nodes"]
    by_id = {n["id"]: n for n in nodes}
    by_path = {_norm(n["path"]): n for n in nodes}
    importers: dict[str, set] = {}
    for link in map_data["links"]:
        importers.setdefault(link["target"], set()).add(link["source"])

    changed, modified_ids = [], []
    for p in paths:
        node = _match_file(p, by_path)
        if node:
            modified_ids.append(node["id"])
            changed.append({"path": node["path"], "status": "modified", "risk": node["risk"],
                            "fan_in": node["fan_in"], "tested": node["tested"] or node["is_test"]})
        else:
            changed.append({"path": _norm(p), "status": "new", "risk": 0, "fan_in": 0, "tested": False})

    # Breadth-first over "who imports this", so depth = distance from the change
    affected: dict[str, dict] = {}
    queue = deque((mid, 0, by_id[mid]["path"]) for mid in modified_ids)
    while queue:
        nid, depth, via = queue.popleft()
        if depth == MAX_DEPTH:
            continue
        for src in importers.get(nid, ()):
            if src in modified_ids or src in affected:
                continue
            node = by_id[src]
            affected[src] = {"path": node["path"], "depth": depth + 1, "via": via,
                             "tested": node["tested"] or node["is_test"], "is_test": node["is_test"]}
            queue.append((src, depth + 1, via))

    affected_list = sorted(affected.values(), key=lambda a: (a["depth"], a["path"]))
    untested = sum(1 for a in affected_list if not a["tested"])
    direct = sum(1 for a in affected_list if a["depth"] == 1)
    max_risk = max((c["risk"] for c in changed), default=0)
    modified = [c for c in changed if c["status"] == "modified"]
    new = [c for c in changed if c["status"] == "new"]

    reasons = []
    if modified:
        riskiest = max(modified, key=lambda c: c["risk"])
        reasons.append(f"Changes {riskiest['path']} (risk {riskiest['risk']}/100, "
                       f"imported by {riskiest['fan_in']} file{'s' if riskiest['fan_in'] != 1 else ''})")
    if affected_list:
        reasons.append(f"{len(affected_list)} file{'s' if len(affected_list) != 1 else ''} depend on the "
                       f"changed code ({direct} directly)")
    if untested:
        reasons.append(f"{untested} affected file{'s have' if untested != 1 else ' has'} no tests")
    untested_changes = [c for c in modified if not c["tested"]]
    if untested_changes:
        reasons.append(f"{len(untested_changes)} modified file{'s are' if len(untested_changes) != 1 else ' is'} not covered by tests")
    if new and not modified:
        reasons.append("Only adds new files; nothing existing imports them yet")

    if max_risk >= 50 or len(affected_list) >= 15:
        level = "high"
    elif max_risk >= 25 or len(affected_list) >= 5 or untested_changes:
        level = "medium"
    else:
        level = "low"

    parts = []
    if modified:
        parts.append(f"modifies {len(modified)} file{'s' if len(modified) != 1 else ''}")
    if new:
        parts.append(f"adds {len(new)} new file{'s' if len(new) != 1 else ''}")
    summary = f"{' and '.join(parts).capitalize()}; {len(affected_list)} file{'s' if len(affected_list) != 1 else ''} depend on it."

    return {
        "level": level,
        "summary": summary,
        "reasons": reasons,
        "changed": changed,
        "affected": affected_list[:MAX_LISTED],
        "affected_count": len(affected_list),
        "untested_affected": untested,
    }


def format_impact(impact: dict | None) -> str:
    """Plain-text impact for agent prompts."""
    if not impact:
        return "No impact analysis (no file paths in the code)."
    lines = [f"Risk level: {impact['level'].upper()}. {impact['summary']}"]
    lines += [f"- {r}" for r in impact["reasons"]]
    direct = [a["path"] for a in impact["affected"] if a["depth"] == 1][:12]
    if direct:
        lines.append("Direct dependents: " + ", ".join(direct))
    return "\n".join(lines)
