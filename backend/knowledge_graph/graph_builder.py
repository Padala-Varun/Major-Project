"""
Knowledge Graph Builder
Constructs a NetworkX directed graph from parsed code structures.
"""

import os
import networkx as nx
from typing import Optional


class GraphBuilder:
    """Builds a knowledge graph representing code structure and relationships."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self._node_counter = 0

    def _next_id(self, prefix: str = "node") -> str:
        self._node_counter += 1
        return f"{prefix}_{self._node_counter}"

    def build_from_parsed_files(self, parsed_files: list[dict]) -> nx.DiGraph:
        """
        Build the knowledge graph from a list of parsed file data.

        Args:
            parsed_files: List of dicts from CodeParser.parse_file()

        Returns:
            NetworkX DiGraph with code structure
        """
        # Phase 1: Add all nodes
        for file_data in parsed_files:
            self._add_file_nodes(file_data)

        # Phase 2: Add import/dependency edges
        for file_data in parsed_files:
            self._add_import_edges(file_data, parsed_files)

        return self.graph

    def _add_file_nodes(self, file_data: dict):
        """Add a file node and its contained classes/functions."""
        file_path = file_data["file_path"]

        # File node
        file_node_id = f"file:{file_path}"
        self.graph.add_node(file_node_id, **{
            "type": "file",
            "name": os.path.basename(file_path),
            "path": file_path,
            "language": file_data.get("language", "unknown"),
            "docstring": file_data.get("docstring", ""),
            "line_count": file_data.get("line_count", 0),
        })

        # Module node (directory)
        module_path = os.path.dirname(file_path)
        if module_path:
            module_node_id = f"module:{module_path}"
            if not self.graph.has_node(module_node_id):
                self.graph.add_node(module_node_id, **{
                    "type": "module",
                    "name": os.path.basename(module_path),
                    "path": module_path,
                })
            self.graph.add_edge(module_node_id, file_node_id, relationship="contains")

        # Class nodes
        for cls in file_data.get("classes", []):
            class_node_id = f"class:{file_path}:{cls['name']}"
            self.graph.add_node(class_node_id, **{
                "type": "class",
                "name": cls["name"],
                "file_path": file_path,
                "line": cls.get("line", 0),
                "parent_class": cls.get("parent"),
                "methods": cls.get("methods", []),
            })
            self.graph.add_edge(file_node_id, class_node_id, relationship="contains")

            # Inheritance edge
            if cls.get("parent"):
                parent_id = self._find_class_node(cls["parent"])
                if parent_id:
                    self.graph.add_edge(class_node_id, parent_id, relationship="inherits")

            # Method nodes
            for method_name in cls.get("methods", []):
                method_node_id = f"function:{file_path}:{cls['name']}.{method_name}"
                self.graph.add_node(method_node_id, **{
                    "type": "function",
                    "name": method_name,
                    "file_path": file_path,
                    "parent_class": cls["name"],
                    "qualified_name": f"{cls['name']}.{method_name}",
                })
                self.graph.add_edge(class_node_id, method_node_id, relationship="contains")

        # Function nodes (top-level)
        for func in file_data.get("functions", []):
            func_node_id = f"function:{file_path}:{func['name']}"
            if not self.graph.has_node(func_node_id):
                self.graph.add_node(func_node_id, **{
                    "type": "function",
                    "name": func["name"],
                    "file_path": file_path,
                    "line": func.get("line", 0),
                })
                self.graph.add_edge(file_node_id, func_node_id, relationship="contains")

    def _add_import_edges(self, file_data: dict, all_files: list[dict]):
        """Add import relationship edges between files."""
        file_path = file_data["file_path"]
        file_node_id = f"file:{file_path}"

        for imp in file_data.get("imports", []):
            # Try to resolve import to a file in the repo
            target_file = self._resolve_import(imp, all_files)
            if target_file:
                target_node_id = f"file:{target_file}"
                if self.graph.has_node(target_node_id):
                    self.graph.add_edge(
                        file_node_id, target_node_id,
                        relationship="imports",
                        import_name=imp,
                    )

    def _resolve_import(self, import_name: str, all_files: list[dict]) -> Optional[str]:
        """Try to resolve an import string to a file path in the repo."""
        # Convert dotted import to path
        import_path = import_name.replace(".", "/")

        for file_data in all_files:
            fp = file_data["file_path"]
            # Check if import matches file path
            if import_path in fp.replace("\\", "/"):
                return fp
            # Check file stem
            stem = os.path.splitext(os.path.basename(fp))[0]
            if stem == import_name.split(".")[-1]:
                return fp

        return None

    def _find_class_node(self, class_name: str) -> Optional[str]:
        """Find a class node by name."""
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") == "class" and data.get("name") == class_name:
                return node_id
        return None

    def get_stats(self) -> dict:
        """Get graph statistics."""
        node_types = {}
        for _, data in self.graph.nodes(data=True):
            ntype = data.get("type", "unknown")
            node_types[ntype] = node_types.get(ntype, 0) + 1

        edge_types = {}
        for _, _, data in self.graph.edges(data=True):
            etype = data.get("relationship", "unknown")
            edge_types[etype] = edge_types.get(etype, 0) + 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
        }
