"""
noteration/search/vault_search.py
Global search engine for the vault: notes, literature, and annotations.
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Dict, Tuple

from noteration.logger import get_logger

logger = get_logger(__name__)


@dataclass

class SearchResult:
    """A single search result."""
    type: Literal["note", "literature", "annotation"]
    title: str           # Title/filename
    snippet: str         # Text snippet with keyword
    path: Path | None    # Path to file (for navigation)
    papis_key: str = ""  # (Optional) for literature/annotation
    page: int | None = None   # (Optional) for annotation
    annotation_id: str = ""   # (Optional) for annotation
    score: float = 0.0  # Relevance score


class VaultSearch:
    """Comprehensive search engine for the vault."""

    def __init__(self, vault_path: Path, papis_bridge=None) -> None:
        self.vault_path = vault_path
        
        # Handle if papis_bridge is a Path (not a PapisBridge instance)
        if papis_bridge is not None and not hasattr(papis_bridge, 'all_entries'):
            # It might be a Path, try to create a PapisBridge
            try:
                from noteration.literature.papis_bridge import PapisBridge
                if isinstance(papis_bridge, Path):
                    papis_bridge = PapisBridge(papis_bridge)
                    print("[INFO] Converted Path to PapisBridge")
            except Exception as e:
                print(f"[WARNING] Failed to convert to PapisBridge: {e}")
                papis_bridge = None
        
        self.papis = papis_bridge
        self._notes_dir = vault_path / "notes"
        self._annotations_dir = vault_path / "annotations"
        
        # Cache for note contents to speed up repeated searches
        # key: str(path), value: (mtime, content)
        self._note_cache: Dict[str, Tuple[float, str]] = {}

    def search(
        self,
        query: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        max_results: int = 200,
    ) -> list[SearchResult]:
        """Search across the entire vault: notes, literature, annotations."""
        results: list[SearchResult] = []
        
        if not query.strip():
            return results

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            if not use_regex:
                # Escape regex special chars
                query_re = re.compile(re.escape(query), flags)
            else:
                query_re = re.compile(query, flags)
        except re.error:
            # Invalid regex, return empty results
            return []

        # 1. Search notes
        results.extend(self._search_notes(query_re))
        # 2. Search literature
        results.extend(self._search_literature(query_re))
        # 3. Search annotations
        results.extend(self._search_annotations(query_re))

        # Sort by score (descending)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

    def _get_note_content(self, md_file: Path) -> str | None:
        """Get note content with caching based on mtime."""
        path_str = str(md_file)
        try:
            mtime = md_file.stat().st_mtime
            if path_str in self._note_cache:
                cached_mtime, content = self._note_cache[path_str]
                if mtime == cached_mtime:
                    return content
            
            content = md_file.read_text(encoding="utf-8")
            self._note_cache[path_str] = (mtime, content)
            return content
        except Exception:
            return None

    def _search_notes(self, pattern: re.Pattern) -> list[SearchResult]:
        """Search all .md files in the notes/ folder."""
        results: list[SearchResult] = []
        if not self._notes_dir.exists():
            return results

        for md_file in self._notes_dir.rglob("*.md"):
            text = self._get_note_content(md_file)
            if text is None:
                continue

            matches = list(pattern.finditer(text))
            if not matches:
                continue

            # Calculate score based on match count and position
            score = len(matches) * 10
            for m in matches:
                # Bonus if in the title (first few lines)
                line_num = text[:m.start()].count("\n") + 1
                if line_num <= 3:
                    score += 5

            # Get snippet around the first match
            first_match = matches[0]
            start = max(0, first_match.start() - 40)
            end = min(len(text), first_match.end() + 40)
            snippet = text[start:end].replace("\n", " ").strip()
            # Highlight keyword (wrap in ** around matches)
            snippet = pattern.sub(lambda m: f"**{m.group()}**", snippet)

            title = md_file.stem
            # Try to get title from the first line (# Title)
            first_line = text.split("\n", 1)[0].strip()
            if first_line.startswith("#"):
                title = first_line.lstrip("#").strip()

            results.append(SearchResult(
                type="note",
                title=title,
                snippet=snippet,
                path=md_file,
                score=score,
            ))
        return results

    def _search_literature(self, pattern: re.Pattern) -> list[SearchResult]:
        """Search literature metadata (Papis)."""
        results: list[SearchResult] = []
        if not self.papis:
            return results

        try:
            entries = self.papis.all_entries()
        except Exception as e:
            print(f"[ERROR] Failed to load literature entries: {e}")
            return results

        for entry in entries:
            # Combine all text fields for searching
            searchable = " ".join(filter(None, [
                entry.title,
                entry.author,
                entry.journal,
                entry.publisher,
                entry.abstract,
                entry.doi,
                entry.isbn,
                " ".join(entry.tags),
                " ".join(entry.collections),
            ]))
            matches = list(pattern.finditer(searchable))
            if not matches:
                continue

            score = len(matches) * 10
            if pattern.search(entry.title or ""):
                score += 20
            if pattern.search(entry.abstract or ""):
                score += 5

            # Snippet from abstract or title
            snippet_parts = []
            if entry.title and pattern.search(entry.title):
                snippet_parts.append(f"Title: {entry.title}")
            if entry.author:
                snippet_parts.append(f"Author: {entry.author}")
            if entry.journal:
                snippet_parts.append(f"Journal: {entry.journal}")
            if entry.abstract:
                abs_matches = list(pattern.finditer(entry.abstract))
                if abs_matches:
                    m = abs_matches[0]
                    start = max(0, m.start() - 30)
                    end = min(len(entry.abstract), m.end() + 30)
                    snippet_parts.append(f"Abstract: ...{entry.abstract[start:end]}...")

            snippet = " | ".join(snippet_parts)
            snippet = pattern.sub(lambda m: f"**{m.group()}**", snippet)

            results.append(SearchResult(
                type="literature",
                title=f"{entry.author or 'Unknown'} - {entry.title or entry.key}",
                snippet=snippet,
                path=None,
                papis_key=entry.key,
                score=score,
            ))
        return results

    def _search_annotations(self, pattern: re.Pattern) -> list[SearchResult]:
        """Search PDF annotation JSON files."""
        results: list[SearchResult] = []
        if not self._annotations_dir.exists():
            return results

        for json_file in self._annotations_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read annotation file {json_file}: {e}")
                continue

            papis_key = data.get("papis_key", json_file.stem)
            annotations = data.get("annotations", [])

            for ann in annotations:
                text_content = ann.get("text_content", "")
                note = ann.get("note", "")
                tags = ann.get("tags", [])
                searchable = f"{text_content} {note} {' '.join(tags)}"

                if not searchable.strip():
                    continue

                matches = list(pattern.finditer(searchable))
                if not matches:
                    continue

                score = len(matches) * 8
                if pattern.search(text_content):
                    score += 10

                # Snippet
                snippet_parts = []
                if text_content and pattern.search(text_content):
                    m = pattern.search(text_content)
                    if m:
                        start = max(0, m.start() - 30)
                        end = min(len(text_content), m.end() + 30)
                        snippet_parts.append(f"Highlight: ...{text_content[start:end]}...")
                if note and pattern.search(note):
                    snippet_parts.append(f"Note: {note[:80]}")
                if tags:
                    snippet_parts.append(f"Tags: {', '.join(tags)}")

                snippet = " | ".join(snippet_parts)
                snippet = pattern.sub(lambda m: f"**{m.group()}**", snippet)

                results.append(SearchResult(
                    type="annotation",
                    title=f"{papis_key} (p. {ann.get('page', '?') + 1})",
                    snippet=snippet,
                    path=None,
                    papis_key=papis_key,
                    page=ann.get("page", 0),
                    annotation_id=ann.get("id", ""),
                    score=score,
                ))
        return results
