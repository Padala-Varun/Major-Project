"""
Code Parser
Extracts structural elements (classes, functions, imports) from source files.
Uses regex-based parsing for broad language support.
"""

import re
from typing import Optional


class CodeParser:
    """Parses source code files to extract structural elements."""

    # ── Regex patterns per language family ──────────────────
    PATTERNS = {
        "python": {
            "class": re.compile(
                r"^class\s+(\w+)\s*(?:\((.*?)\))?\s*:", re.MULTILINE
            ),
            "function": re.compile(
                r"^(?:    |\t)?def\s+(\w+)\s*\((.*?)\)", re.MULTILINE
            ),
            "import": re.compile(
                r"^(?:from\s+([\w.]+)\s+)?import\s+(.+)", re.MULTILINE
            ),
            "docstring": re.compile(
                r'(?:\"\"\"(.*?)\"\"\"|\'\'\'(.*?)\'\'\')', re.DOTALL
            ),
        },
        "javascript": {
            "class": re.compile(
                r"class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{", re.MULTILINE
            ),
            "function": re.compile(
                r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function))",
                re.MULTILINE,
            ),
            "import": re.compile(
                r"(?:import\s+.*?from\s+['\"](.+?)['\"]|require\s*\(\s*['\"](.+?)['\"]\s*\))",
                re.MULTILINE,
            ),
        },
        "java": {
            "class": re.compile(
                r"(?:public|private|protected)?\s*(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
                re.MULTILINE,
            ),
            "function": re.compile(
                r"(?:public|private|protected)\s+(?:static\s+)?(?:\w+(?:<.*?>)?)\s+(\w+)\s*\(",
                re.MULTILINE,
            ),
            "import": re.compile(
                r"import\s+([\w.]+(?:\.\*)?)\s*;", re.MULTILINE
            ),
        },
        "generic": {
            "class": re.compile(
                r"class\s+(\w+)", re.MULTILINE
            ),
            "function": re.compile(
                r"(?:def|func|fn|function)\s+(\w+)", re.MULTILINE
            ),
            "import": re.compile(
                r"(?:import|include|require|use)\s+[\"']?([^\s\"';]+)", re.MULTILINE
            ),
        },
    }

    LANG_MAP = {
        ".py": "python",
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "javascript", ".tsx": "javascript",
        ".mjs": "javascript", ".cjs": "javascript",
        ".vue": "javascript", ".svelte": "javascript",
        ".java": "java", ".kt": "java", ".scala": "java",
        ".go": "generic", ".rs": "generic", ".rb": "generic",
        ".php": "generic", ".swift": "generic", ".cs": "generic",
        ".cpp": "generic", ".c": "generic", ".h": "generic", ".hpp": "generic",
    }

    def parse_file(self, file_path: str, content: str, extension: str) -> dict:
        """
        Parse a source file and extract structural elements.

        Returns:
            dict with classes, functions, imports, and raw content
        """
        lang = self.LANG_MAP.get(extension, "generic")
        patterns = self.PATTERNS.get(lang, self.PATTERNS["generic"])

        classes = self._extract_classes(content, patterns, file_path)
        functions = self._extract_functions(content, patterns, file_path)
        imports = self._extract_imports(content, patterns)
        docstring = self._extract_module_docstring(content, lang)

        return {
            "file_path": file_path,
            "language": lang,
            "classes": classes,
            "functions": functions,
            "imports": imports,
            "docstring": docstring,
            "content": content,
            "line_count": content.count("\n") + 1,
        }

    def _extract_classes(self, content: str, patterns: dict, file_path: str) -> list[dict]:
        """Extract class definitions with their methods."""
        classes = []
        pattern = patterns.get("class")
        if not pattern:
            return classes

        for match in pattern.finditer(content):
            class_name = match.group(1)
            parent = match.group(2) if match.lastindex and match.lastindex >= 2 else None
            line_no = content[:match.start()].count("\n") + 1

            # Try to extract methods within this class
            methods = self._extract_class_methods(content, match.start(), file_path)

            classes.append({
                "name": class_name,
                "parent": parent,
                "line": line_no,
                "methods": methods,
                "file_path": file_path,
            })

        return classes

    def _extract_class_methods(self, content: str, class_start: int, file_path: str) -> list[str]:
        """Extract method names from a class body (heuristic)."""
        methods = []
        lines = content[class_start:].split("\n")
        in_class = False
        for line in lines:
            stripped = line.strip()
            if not in_class:
                if stripped.startswith("class "):
                    in_class = True
                continue
            # End of class heuristic: non-indented, non-empty line
            if line and not line[0].isspace() and stripped and not stripped.startswith("#"):
                break
            method_match = re.match(r"\s+def\s+(\w+)", line)
            if method_match:
                methods.append(method_match.group(1))
        return methods

    def _extract_functions(self, content: str, patterns: dict, file_path: str) -> list[dict]:
        """Extract top-level function definitions."""
        functions = []
        pattern = patterns.get("function")
        if not pattern:
            return functions

        for match in pattern.finditer(content):
            # Get first non-None group as the function name
            name = next((g for g in match.groups() if g is not None), None)
            if not name or name.startswith("_") and name != "__init__":
                pass  # include private functions too
            if name:
                line_no = content[:match.start()].count("\n") + 1
                functions.append({
                    "name": name,
                    "line": line_no,
                    "file_path": file_path,
                })

        return functions

    def _extract_imports(self, content: str, patterns: dict) -> list[str]:
        """Extract import/require statements."""
        imports = []
        pattern = patterns.get("import")
        if not pattern:
            return imports

        for match in pattern.finditer(content):
            # Collect all non-None groups
            for group in match.groups():
                if group:
                    imports.append(group.strip())

        return list(set(imports))

    def _extract_module_docstring(self, content: str, lang: str) -> Optional[str]:
        """Extract the module-level docstring (Python only for now)."""
        if lang == "python":
            pattern = self.PATTERNS["python"]["docstring"]
            match = pattern.search(content[:500])  # Only check first 500 chars
            if match:
                return (match.group(1) or match.group(2) or "").strip()
        return None
