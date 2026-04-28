"""
noteration/search/vault_search.py
Global search engine untuk vault: notes, literature, dan annotations.
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class SearchResult:
    """Satu hasil pencarian."""
    type: Literal["note", "literature", "annotation"]
    title: str           # Judul/nama file
    snippet: str         # Potongan teks dengan keyword
    path: Path | None    # Path ke file (untuk navigasi)
    papis_key: str = ""  # (Opsional) untuk literature/annotation
    page: int | None = None   # (Opsional) untuk annotation
    annotation_id: str = ""   # (Opsional) untuk annotation
    score: float = 0.0  # Relevansi


class VaultSearch:
    """Mesin pencarian menyeluruh untuk vault."""

    def __init__(self, vault_path: Path, papis_bridge=None) -> None:
        self.vault_path = vault_path
        
        # Handle jika papis_bridge adalah Path (bukan instance PapisBridge)
        if papis_bridge is not None and not hasattr(papis_bridge, 'all_entries'):
            # Mungkin ini adalah Path, coba buat PapisBridge
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

    def search(
        self,
        query: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        max_results: int = 200,
    ) -> list[SearchResult]:
        """Cari di seluruh vault: notes, literature, annotations."""
        results: list[SearchResult] = []
        flags = 0 if case_sensitive else re.IGNORECASE
        if not use_regex:
            # Escape regex special chars
            query_re = re.compile(re.escape(query), flags)
        else:
            query_re = re.compile(query, flags)

        # 1. Search notes
        results.extend(self._search_notes(query_re))
        # 2. Search literature
        results.extend(self._search_literature(query_re))
        # 3. Search annotations
        results.extend(self._search_annotations(query_re))

        # Sort by score (descending)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

    def _search_notes(self, pattern: re.Pattern) -> list[SearchResult]:
        """Cari di semua file .md di folder notes/."""
        results: list[SearchResult] = []
        if not self._notes_dir.exists():
            return results

        for md_file in self._notes_dir.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            matches = list(pattern.finditer(text))
            if not matches:
                continue

            # Hitung score berdasarkan jumlah match dan posisi
            score = len(matches) * 10
            for m in matches:
                # Bonus jika di judul (baris pertama/kedua)
                line_num = text[:m.start()].count("\n") + 1
                if line_num <= 3:
                    score += 5

            # Ambil snippet di sekitar match pertama
            first_match = matches[0]
            start = max(0, first_match.start() - 40)
            end = min(len(text), first_match.end() + 40)
            snippet = text[start:end].replace("\n", " ").strip()
            # Highlight keyword (tanda ** di sekitar match)
            snippet = pattern.sub(lambda m: f"**{m.group()}**", snippet)

            title = md_file.stem
            # Coba ambil judul dari baris pertama (# Title)
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
        """Cari di metadata literatur (Papis)."""
        results: list[SearchResult] = []
        if not self.papis:
            return results

        try:
            entries = self.papis.all_entries()
        except AttributeError as e:
            print(f"[ERROR] Method all_entries() not found: {e}")
            return results
        except Exception as e:
            print(f"[ERROR] Failed to load literature entries: {e}")
            return results

        for entry in entries:
            # Gabungkan semua field teks untuk pencarian
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

            # Snippet dari abstract atau title
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
        """Cari di file JSON anotasi PDF."""
        results: list[SearchResult] = []
        if not self._annotations_dir.exists():
            return results

        for json_file in self._annotations_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
            except Exception:
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
