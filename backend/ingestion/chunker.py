"""
Code Chunker
Splits source code into overlapping chunks for embedding,
preserving function/class boundaries where possible.
"""

from config import CHUNK_SIZE, CHUNK_OVERLAP


class CodeChunker:
    """Chunks source code files for vector embedding."""

    def __init__(self, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_file(self, file_path: str, content: str, parsed_data: dict) -> list[dict]:
        """
        Chunk a file's content into overlapping segments.

        Tries to split at function/class boundaries first.
        Falls back to line-based splitting.
        """
        if len(content) <= self.chunk_size:
            return [self._make_chunk(file_path, content, 1, content.count("\n") + 1, parsed_data)]

        # Try boundary-aware chunking first
        chunks = self._boundary_chunk(file_path, content, parsed_data)
        if chunks:
            return chunks

        # Fallback: line-based chunking
        return self._line_chunk(file_path, content, parsed_data)

    def _boundary_chunk(self, file_path: str, content: str, parsed_data: dict) -> list[dict]:
        """
        Split content at function/class boundaries.
        Returns empty list if no boundaries found.
        """
        lines = content.split("\n")
        boundaries = set()

        # Collect line numbers where classes/functions start
        for cls in parsed_data.get("classes", []):
            boundaries.add(cls.get("line", 1) - 1)  # 0-indexed
        for func in parsed_data.get("functions", []):
            boundaries.add(func.get("line", 1) - 1)

        if not boundaries:
            return []

        sorted_bounds = sorted(boundaries)
        chunks = []
        i = 0

        while i < len(lines):
            # Find next boundary after current position + chunk_size
            end_line = min(i + self._lines_for_chars(lines, i, self.chunk_size), len(lines))

            # Try to snap to a boundary
            snapped = self._snap_to_boundary(sorted_bounds, end_line, i)
            if snapped and snapped > i:
                end_line = snapped

            chunk_lines = lines[i:end_line]
            chunk_text = "\n".join(chunk_lines)

            if chunk_text.strip():
                chunks.append(self._make_chunk(
                    file_path, chunk_text,
                    i + 1, end_line,
                    parsed_data
                ))

            # Move forward with overlap
            overlap_lines = max(1, self._lines_for_chars(lines, max(0, end_line - 10), self.overlap))
            i = max(i + 1, end_line - overlap_lines)

        return chunks

    def _line_chunk(self, file_path: str, content: str, parsed_data: dict) -> list[dict]:
        """Simple line-based chunking with overlap."""
        lines = content.split("\n")
        chunks = []
        i = 0

        while i < len(lines):
            end_line = min(i + self._lines_for_chars(lines, i, self.chunk_size), len(lines))
            chunk_text = "\n".join(lines[i:end_line])

            if chunk_text.strip():
                chunks.append(self._make_chunk(
                    file_path, chunk_text,
                    i + 1, end_line,
                    parsed_data
                ))

            overlap_lines = max(1, self._lines_for_chars(lines, max(0, end_line - 5), self.overlap))
            i = max(i + 1, end_line - overlap_lines)

        return chunks

    def _lines_for_chars(self, lines: list[str], start: int, char_count: int) -> int:
        """How many lines from 'start' fit within 'char_count' characters."""
        total = 0
        count = 0
        for idx in range(start, len(lines)):
            total += len(lines[idx]) + 1  # +1 for newline
            count += 1
            if total >= char_count:
                break
        return max(1, count)

    def _snap_to_boundary(self, boundaries: list[int], target: int, start: int) -> int:
        """Find the nearest boundary to 'target' that is after 'start'."""
        best = None
        for b in boundaries:
            if start < b <= target + 5:  # Allow slight overshoot
                best = b
        return best

    def _make_chunk(self, file_path: str, text: str, start_line: int,
                    end_line: int, parsed_data: dict) -> dict:
        """Create a chunk metadata dict."""
        # Identify which functions/classes are in this chunk
        contained_entities = []
        for cls in parsed_data.get("classes", []):
            if start_line <= cls.get("line", 0) <= end_line:
                contained_entities.append(f"class:{cls['name']}")
        for func in parsed_data.get("functions", []):
            if start_line <= func.get("line", 0) <= end_line:
                contained_entities.append(f"function:{func['name']}")

        return {
            "file_path": file_path,
            "content": text,
            "start_line": start_line,
            "end_line": end_line,
            "language": parsed_data.get("language", "unknown"),
            "entities": contained_entities,
            "char_count": len(text),
        }
