"""
Import Resolver
Maps an import specifier ("flask.json", ".helpers", "./utils/api") to the
repository file it refers to, or None for external packages. Only exact
module paths match; a filename appearing somewhere in a path is not enough.
"""

import posixpath
from typing import Optional

JS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte")
JS_SUFFIXES = ("",) + JS_EXTENSIONS + tuple(f"/index{ext}" for ext in JS_EXTENSIONS)
JS_ALIAS_ROOTS = ("src/", "")  # "@/x" and "~/x" usually mean src/x


class ImportResolver:
    def __init__(self, file_paths: list[str]):
        # Work in forward-slash paths; remember each file's original spelling
        self.original = {p.replace("\\", "/"): p for p in file_paths}
        self.paths = set(self.original)
        self.no_ext = {}
        for p in self.paths:
            self.no_ext.setdefault(posixpath.splitext(p)[0], p)
        self.py_modules = self._index_python()

    # ── Python ────────────────────────────────────────────
    def _index_python(self) -> dict[str, str]:
        """Dotted module name → file, for every plausible import root.

        Roots are the repo root, plus each directory that holds a top-level
        package (src/, examples/tutorial/, ...), so `import flaskr.db` and
        `import flask` resolve the way Python would see them on sys.path.
        """
        py = [p for p in self.paths if p.endswith(".py")]
        package_dirs = {posixpath.dirname(p) for p in py if p.endswith("/__init__.py") or p == "__init__.py"}
        roots = {""}
        for d in package_dirs:
            parent = posixpath.dirname(d)
            if parent not in package_dirs:
                roots.add(parent)
        # Script directories (no __init__) import their siblings directly
        roots |= {posixpath.dirname(p) for p in py if posixpath.dirname(p) not in package_dirs}

        modules: dict[str, str] = {}
        # Deeper roots first so "flask" maps to src/flask, not a same-named top-level dir
        for root in sorted(roots, key=lambda r: -r.count("/") if r else 1):
            prefix = f"{root}/" if root else ""
            for p in py:
                if not p.startswith(prefix):
                    continue
                rel = p[len(prefix):-3]
                if rel.endswith("/__init__") or rel == "__init__":
                    rel = rel[: -len("__init__")].rstrip("/")
                if rel:
                    modules.setdefault(rel.replace("/", "."), p)
        return modules

    def _resolve_python(self, spec: str, importer: str) -> Optional[str]:
        if spec.startswith("."):
            level = len(spec) - len(spec.lstrip("."))
            base = posixpath.dirname(importer)
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            parts = spec[level:].split(".") if spec[level:] else []
            # Try the full path, then drop trailing names (they may be classes/functions)
            for n in range(len(parts), -1, -1):
                target = posixpath.join(base, *parts[:n]) if parts[:n] else base
                for candidate in (f"{target}.py", f"{target}/__init__.py"):
                    if candidate in self.paths:
                        return candidate
            return None

        parts = spec.split(".")
        for n in range(len(parts), 0, -1):
            hit = self.py_modules.get(".".join(parts[:n]))
            if hit:
                return hit
        return None

    # ── JavaScript / TypeScript ───────────────────────────
    def _resolve_js(self, spec: str, importer: str) -> Optional[str]:
        if spec.startswith("."):
            bases = [posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))]
        elif spec.startswith(("@/", "~/")):
            bases = [root + spec[2:] for root in JS_ALIAS_ROOTS]
        else:
            return None  # bare specifier: an npm package
        for base in bases:
            for suffix in JS_SUFFIXES:
                if base + suffix in self.paths:
                    return base + suffix
        return None

    # ── Other languages ───────────────────────────────────
    def _resolve_generic(self, spec: str) -> Optional[str]:
        """Java/Go/etc.: the specifier must match the end of a path at a segment boundary."""
        key = spec.strip("\"'<>").rstrip(";")
        if key.endswith(".*"):
            return None
        key = key.replace("::", "/")
        if "/" not in key:
            key = key.replace(".", "/")
        hit = self.no_ext.get(key)
        if hit:
            return hit
        for stem, path in self.no_ext.items():
            if stem.endswith("/" + key):
                return path
        return None

    def resolve(self, spec: str, importer: str) -> Optional[str]:
        importer = importer.replace("\\", "/")
        spec = spec.strip()
        if not spec:
            return None
        if importer.endswith(".py"):
            hit = self._resolve_python(spec, importer)
        elif importer.endswith(JS_EXTENSIONS):
            hit = self._resolve_js(spec, importer)
        else:
            hit = self._resolve_generic(spec)
        return self.original.get(hit) if hit else None
