"""
Architecture Map
Condenses the knowledge graph into a file-level dependency map for the UI:
modules, entry points, and an explainable risk score per file.
"""

import os
import re
from collections import Counter

import networkx as nx

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
    ".swift", ".kt", ".scala", ".cs", ".cpp", ".c", ".h", ".hpp", ".vue", ".svelte",
}
TEST_PATTERN = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+$|_test\.[a-z]+$|\.(test|spec)\.[a-z]+$",
    re.IGNORECASE,
)
ENTRY_NAMES = {"main", "app", "index", "server", "cli", "__main__", "manage", "wsgi", "asgi"}
MAX_FILES = 600          # keeps the canvas responsive on large repos
MAX_NAMES = 40           # classes/functions listed per file

# Risk weights: how much breaks if it changes, how much is in it, whether tests guard it
W_FAN_IN, W_SIZE, W_UNTESTED = 0.55, 0.25, 0.20


PACKAGE_ENTRIES = {"__init__", "index", "mod"}


def _is_test(path: str) -> bool:
    return bool(TEST_PATTERN.search(path.replace("\\", "/")))


def _is_package_entry(path: str) -> bool:
    return os.path.splitext(os.path.basename(path))[0] in PACKAGE_ENTRIES


TARGET_MODULES = 7       # split folders until about this many groups


def _assign_modules(paths: dict[str, str]) -> dict[str, str]:
    """Group files into readable modules by folder.

    Starts with everything in one group and repeatedly splits the largest
    group by its next folder level, collapsing single-folder chains
    (src/pkg/ → "src/pkg"), until there are about TARGET_MODULES groups.
    """
    dirs = {n: p.replace("\\", "/").split("/")[:-1] for n, p in paths.items()}
    groups: dict[tuple, list[str]] = {(): list(paths)}

    def split(prefix, members):
        depth = len(prefix)
        out: dict[tuple, list[str]] = {}
        for n in members:
            d = dirs[n]
            key = tuple(d[:depth + 1]) if len(d) > depth else prefix
            out.setdefault(key, []).append(n)
        return out

    def collapse(prefix, members):
        # Extend the prefix while every member sits deeper in the same single folder
        while True:
            parts = split(prefix, members)
            if len(parts) != 1 or next(iter(parts)) == prefix:
                return prefix
            prefix = next(iter(parts))

    groups = {collapse((), list(paths)): list(paths)}
    while len(groups) < TARGET_MODULES:
        splittable = [(p, m) for p, m in groups.items() if len(split(p, m)) > 1]
        if not splittable:
            break
        prefix, members = max(splittable, key=lambda pm: len(pm[1]))
        parts = split(prefix, members)
        if len(groups) - 1 + len(parts) > TARGET_MODULES + 2:
            break  # splitting would scatter files into too many tiny modules
        del groups[prefix]
        for p, m in parts.items():
            groups[collapse(p, m) if p != prefix else p] = m

    return {n: ("/".join(p) or "(root)") for p, members in groups.items() for n in members}


def build_map(graph: nx.DiGraph) -> dict:
    files = {n: d for n, d in graph.nodes(data=True) if d.get("type") == "file"}
    code = {n: d for n, d in files.items()
            if os.path.splitext(d.get("path", ""))[1].lower() in CODE_EXTENSIONS}
    files = code or files  # docs-only repos still get a map

    # File → file import edges, deduplicated
    links = set()
    for u, v, d in graph.edges(data=True):
        if d.get("relationship") == "imports" and u in files and v in files and u != v:
            links.add((u, v))

    fan_in = Counter(v for _, v in links)
    fan_out = Counter(u for u, _ in links)

    truncated = len(files) > MAX_FILES
    if truncated:
        keep = sorted(files, key=lambda n: fan_in[n] + fan_out[n], reverse=True)[:MAX_FILES]
        files = {n: files[n] for n in keep}
        links = {(u, v) for u, v in links if u in files and v in files}

    paths = {n: d["path"] for n, d in files.items()}
    modules = _assign_modules(paths)
    tests = {n for n, p in paths.items() if _is_test(p)}

    # A file counts as tested if a test imports it, imports a package entry
    # (__init__.py / index.*) that re-exports it, or a test file is named after it
    test_stems = {os.path.splitext(os.path.basename(paths[t]))[0].lower() for t in tests}
    tested = {v for u, v in links if u in tests}
    out_links: dict[str, set] = {}
    for u, v in links:
        out_links.setdefault(u, set()).add(v)
    frontier = [n for n in tested if _is_package_entry(paths[n])]
    while frontier:
        entry = frontier.pop()
        for v in out_links.get(entry, ()):
            if v not in tested:
                tested.add(v)
                if _is_package_entry(paths[v]):
                    frontier.append(v)
    for n, p in paths.items():
        stem = os.path.splitext(os.path.basename(p))[0].lower()
        if {f"test_{stem}", f"{stem}_test", f"{stem}.test", f"{stem}.spec"} & test_stems:
            tested.add(n)

    def children(n, kind):
        return [graph.nodes[c].get("name", "") for c in graph.successors(n)
                if graph.nodes[c].get("type") == kind]

    def method_count(n):
        return sum(len(graph.nodes[c].get("methods", [])) for c in graph.successors(n)
                   if graph.nodes[c].get("type") == "class")

    sizes = {n: len(children(n, "class")) + len(children(n, "function")) + method_count(n)
             for n in files}
    max_fan_in = max(fan_in.values(), default=0) or 1
    max_size = max(sizes.values(), default=0) or 1

    nodes = []
    for n, d in files.items():
        is_test = n in tests
        reasons = []
        if is_test:
            risk = 0
        else:
            fi, size = fan_in[n], sizes[n]
            risk = round(100 * (W_FAN_IN * fi / max_fan_in
                                + W_SIZE * size / max_size
                                + W_UNTESTED * (n not in tested)))
            if fi:
                reasons.append(f"Imported by {fi} file{'s' if fi != 1 else ''}")
            if size:
                reasons.append(f"{size} classes and functions")
            reasons.append("Covered by tests" if n in tested else "No tests reference it")

        classes = children(n, "class")
        functions = children(n, "function")
        nodes.append({
            "id": n,
            "path": d["path"],
            "name": d.get("name") or os.path.basename(d["path"]),
            "language": d.get("language", "unknown"),
            "module": modules[n],
            "lines": d.get("line_count", 0),
            "fan_in": fan_in[n],
            "fan_out": fan_out[n],
            "classes": classes[:MAX_NAMES],
            "functions": functions[:MAX_NAMES],
            "is_test": is_test,
            "tested": n in tested,
            "risk": risk,
            "risk_reasons": reasons,
            "docstring": (d.get("docstring") or "")[:300],
        })

    by_id = {node["id"]: node for node in nodes}
    non_test = [node for node in nodes if not node["is_test"]]

    hotspots = sorted(non_test, key=lambda x: x["risk"], reverse=True)[:8]

    def entry_rank(node):
        stem = os.path.splitext(node["name"])[0].lower()
        return (stem not in ENTRY_NAMES, -node["fan_out"])

    entries = sorted(
        (x for x in non_test if x["fan_in"] == 0 and
         (x["fan_out"] > 0 or os.path.splitext(x["name"])[0].lower() in ENTRY_NAMES)),
        key=entry_rank,
    )[:6]

    module_counts = Counter(node["module"] for node in nodes)
    languages = Counter(node["language"] for node in nodes)

    return {
        "nodes": nodes,
        "links": [{"source": u, "target": v} for u, v in sorted(links)],
        "modules": [{"name": m, "files": c} for m, c in module_counts.most_common()],
        "hotspots": [x["id"] for x in hotspots],
        "entry_points": [x["id"] for x in entries],
        "stats": {
            "files": len(nodes),
            "dependencies": len(links),
            "classes": sum(len(by_id[n]["classes"]) for n in by_id),
            "functions": sum(len(by_id[n]["functions"]) for n in by_id),
            "test_files": len(tests),
            "untested_files": sum(1 for x in non_test if not x["tested"]),
            "languages": dict(languages.most_common()),
            "truncated": truncated,
        },
    }
