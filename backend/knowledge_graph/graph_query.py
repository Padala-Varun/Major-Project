"""
Knowledge Graph Query Utilities
Provides graph traversal and query operations for the code knowledge graph.
"""

import networkx as nx
from typing import Optional


class GraphQuery:
    """Query utilities for the code knowledge graph."""

    def __init__(self, graph: nx.DiGraph):
        self.graph = graph

    def get_node(self, node_id: str) -> Optional[dict]:
        """Get node data by ID."""
        if self.graph.has_node(node_id):
            return {"id": node_id, **dict(self.graph.nodes[node_id])}
        return None

    def get_neighbors(self, node_id: str, direction: str = "both") -> list[dict]:
        """Get neighbors of a node with relationship info."""
        neighbors = []

        if direction in ("out", "both"):
            for _, target, data in self.graph.out_edges(node_id, data=True):
                target_data = dict(self.graph.nodes[target])
                neighbors.append({
                    "id": target,
                    "direction": "outgoing",
                    "relationship": data.get("relationship", "unknown"),
                    **target_data,
                })

        if direction in ("in", "both"):
            for source, _, data in self.graph.in_edges(node_id, data=True):
                source_data = dict(self.graph.nodes[source])
                neighbors.append({
                    "id": source,
                    "direction": "incoming",
                    "relationship": data.get("relationship", "unknown"),
                    **source_data,
                })

        return neighbors

    def find_nodes_by_type(self, node_type: str) -> list[dict]:
        """Find all nodes of a specific type."""
        results = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") == node_type:
                results.append({"id": node_id, **data})
        return results

    def find_nodes_by_name(self, name: str, fuzzy: bool = True) -> list[dict]:
        """Find nodes by name (exact or fuzzy match)."""
        results = []
        name_lower = name.lower()
        for node_id, data in self.graph.nodes(data=True):
            node_name = data.get("name", "").lower()
            if fuzzy:
                if name_lower in node_name or node_name in name_lower:
                    results.append({"id": node_id, **data})
            else:
                if node_name == name_lower:
                    results.append({"id": node_id, **data})
        return results

    def get_file_structure(self, file_path: str) -> dict:
        """Get the complete structure of a file (classes, functions)."""
        file_node_id = f"file:{file_path}"
        if not self.graph.has_node(file_node_id):
            return {}

        file_data = dict(self.graph.nodes[file_node_id])
        children = self.get_neighbors(file_node_id, direction="out")

        return {
            "file": {"id": file_node_id, **file_data},
            "classes": [c for c in children if c.get("type") == "class"],
            "functions": [f for f in children if f.get("type") == "function"],
            "imports": [
                i for i in children
                if i.get("relationship") == "imports"
            ],
        }

    def get_dependency_chain(self, node_id: str, max_depth: int = 3) -> list[dict]:
        """Trace the dependency chain from a node (what it imports/uses)."""
        visited = set()
        chain = []

        def _traverse(nid, depth):
            if depth > max_depth or nid in visited:
                return
            visited.add(nid)
            for _, target, data in self.graph.out_edges(nid, data=True):
                if data.get("relationship") in ("imports", "calls", "uses"):
                    target_data = dict(self.graph.nodes[target])
                    chain.append({
                        "source": nid,
                        "target": target,
                        "relationship": data.get("relationship"),
                        "depth": depth,
                        **target_data,
                    })
                    _traverse(target, depth + 1)

        _traverse(node_id, 0)
        return chain

    def get_dependents(self, node_id: str, max_depth: int = 3) -> list[dict]:
        """Find what depends on this node (reverse dependencies)."""
        visited = set()
        dependents = []

        def _traverse(nid, depth):
            if depth > max_depth or nid in visited:
                return
            visited.add(nid)
            for source, _, data in self.graph.in_edges(nid, data=True):
                if data.get("relationship") in ("imports", "calls", "uses"):
                    source_data = dict(self.graph.nodes[source])
                    dependents.append({
                        "source": source,
                        "target": nid,
                        "relationship": data.get("relationship"),
                        "depth": depth,
                        **source_data,
                    })
                    _traverse(source, depth + 1)

        _traverse(node_id, 0)
        return dependents

    def get_subgraph(self, center_node: str, radius: int = 2) -> dict:
        """Get a subgraph centered on a node within a given radius."""
        if not self.graph.has_node(center_node):
            return {"nodes": [], "edges": []}

        # BFS to find nodes within radius
        visited = {center_node}
        frontier = [center_node]

        for _ in range(radius):
            next_frontier = []
            for node in frontier:
                for neighbor in list(self.graph.successors(node)) + list(self.graph.predecessors(node)):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
            frontier = next_frontier

        # Build subgraph data
        nodes = []
        for nid in visited:
            nodes.append({"id": nid, **dict(self.graph.nodes[nid])})

        edges = []
        for u, v, data in self.graph.edges(data=True):
            if u in visited and v in visited:
                edges.append({
                    "source": u,
                    "target": v,
                    "relationship": data.get("relationship", "unknown"),
                })

        return {"nodes": nodes, "edges": edges}

    def shortest_path(self, source: str, target: str) -> list[str]:
        """Find shortest path between two nodes."""
        try:
            return nx.shortest_path(self.graph, source, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_summary_context(self, file_paths: list[str]) -> str:
        """Generate a textual summary of the graph context for given files."""
        context_parts = []

        for fp in file_paths:
            structure = self.get_file_structure(fp)
            if not structure:
                continue

            file_info = structure.get("file", {})
            parts = [f"File: {fp} ({file_info.get('language', 'unknown')})"]

            classes = structure.get("classes", [])
            if classes:
                class_names = [c.get("name", "?") for c in classes]
                parts.append(f"  Classes: {', '.join(class_names)}")

            functions = structure.get("functions", [])
            if functions:
                func_names = [f.get("name", "?") for f in functions]
                parts.append(f"  Functions: {', '.join(func_names)}")

            # Dependencies
            deps = self.get_dependency_chain(f"file:{fp}", max_depth=1)
            if deps:
                dep_files = set(d.get("name", "?") for d in deps)
                parts.append(f"  Depends on: {', '.join(dep_files)}")

            context_parts.append("\n".join(parts))

        return "\n\n".join(context_parts)
