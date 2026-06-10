"""noteration/literature/bibtex_export.py

Export Papis entries to BibTeX format.

Supports:
  - Exporting a single entry (@key)         → get_bibtex_string()
  - Exporting the entire library             → export_all()
  - Exporting entries with specific keys     → export_keys()
  - Exporting from a single note             → export_from_note()
  - Exporting from the entire vault          → export_from_vault()
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from noteration.logger import get_logger
from noteration.literature.papis_bridge import LiteratureEntry, PapisBridge
from noteration.editor.wiki_links import parse_citations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noteration.core.repository import NoteRepository

logger = get_logger(__name__)


# ── BibTeX Types ──────────────────────────────────────────────────────────

_TYPE_MAP: dict[str, str] = {
    "article": "article",
    "journal": "article",
    "book": "book",
    "inbook": "inbook",
    "incollection": "incollection",
    "inproceedings": "inproceedings",
    "conference": "inproceedings",
    "proceedings": "proceedings",
    "phdthesis": "phdthesis",
    "mastersthesis": "mastersthesis",
    "techreport": "techreport",
    "report": "techreport",
    "misc": "misc",
    "online": "misc",
    "preprint": "misc",
    "unpublished": "unpublished",
    "manual": "manual",
    "booklet": "booklet",
}

# Fields handled explicitly — no need to rewrite from extra_fields to avoid duplication
_HANDLED_FIELDS = frozenset(
    {
        "type",
        "title",
        "author",
        "year",
        "journal",
        "doi",
        "abstract",
        "tags",
        "keywords",
        "ref",
        "papis_id",
    }
)


# ── Escaping ──────────────────────────────────────────────────────────────


def _escape_bibtex(value: str) -> str:
    """Escape BibTeX special characters within a field value."""
    return (
        value.replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
        .replace("~", r"\~{}")
        .replace("^", r"\^{}")
    )


def _format_author_bibtex(author: Any) -> str:
    """Convert author field to BibTeX format: "Family, Given and Family2, Given2".
    Supports three input formats produced by Papis:
      - str   : already in any format, return as is
      - list[str]  : join with " and "
      - list[dict] : convert each dict {family, given} → "Family, Given"
    """
    if not author:
        return ""
    if isinstance(author, str):
        # Replace "; " (internal Noteration format) with " and " (BibTeX format)
        return re.sub(r"\s*;\s*", " and ", author)
    if isinstance(author, list):
        parts: list[str] = []
        for a in author:
            if isinstance(a, dict):
                family = a.get("family", "").strip()
                given = a.get("given", "").strip()
                if family and given:
                    parts.append(f"{family}, {given}")
                elif family:
                    parts.append(family)
                elif given:
                    parts.append(given)
            else:
                parts.append(str(a).strip())
        return " and ".join(p for p in parts if p)
    return str(author)


# ── Core Converter ────────────────────────────────────────────────────────


def entry_to_bibtex(
    entry: LiteratureEntry,
    extra_fields: dict[str, Any] | None = None,
) -> str:
    """Convert a single LiteratureEntry to a BibTeX string.

    Priority order for determining entry type:
      1. entry._raw["type"]    (from info.yaml)
      2. extra_fields["type"]  (manual override)
      3. "misc"                (fallback)
    """
    # Merge raw and extra — raw is more trusted
    raw = dict(entry._raw) if entry._raw else {}
    if extra_fields:
        for k, v in extra_fields.items():
            raw.setdefault(k, v)

    # Determine BibTeX type
    bib_type = "misc"
    for source in (raw.get("type", ""), raw.get("type_", "")):
        if source:
            bib_type = _TYPE_MAP.get(str(source).lower().strip(), "misc")
            break

    # Format author from raw (possibly list-of-dict) or from entry.author
    raw_author = raw.get("author", entry.author)
    author_str = _format_author_bibtex(raw_author)

    lines: list[str] = [f"@{bib_type}{{{entry.key},"]

    def add(field: str, value: str) -> None:
        v = value.strip() if isinstance(value, str) else str(value).strip()
        if v:
            lines.append(f"  {field} = {{{_escape_bibtex(v)}}},")

    add("title", entry.title)
    add("author", author_str)
    add("year", entry.year)
    add("journal", entry.journal)
    add("doi", entry.doi)
    add("abstract", entry.abstract)

    if entry.tags:
        add("keywords", ", ".join(entry.tags))

    # Additional fields from raw / extra_fields not yet handled
    for k, v in raw.items():
        if k not in _HANDLED_FIELDS and v is not None:
            add(k, str(v))

    # Remove trailing comma from the last field for clean BibTeX
    if len(lines) > 1 and lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]

    lines.append("}")
    return "\n".join(lines)


# ── BibTeXExporter ────────────────────────────────────────────────────────


class BibtexExporter:
    """Export Papis library to a .bib file."""

    def __init__(self, bridge: PapisBridge) -> None:
        self._bridge = bridge

    # ── Public API ────────────────────────────────────────────────────

    def export_all(self, output_path: Path) -> int:
        """Export the entire library to a single .bib file.
        Equivalent to: papis export --all --output all.bib
        Returns: number of exported entries.
        """
        entries = self._bridge.all_entries()
        return self._write(entries, output_path)

    def export_keys(self, keys: list[str], output_path: Path) -> int:
        """Export only entries with specific keys.
        Equivalent to: papis export --all --output out.bib <query>
        """
        key_set = set(keys)
        entries = [e for e in self._bridge.all_entries() if e.key in key_set]
        return self._write(entries, output_path)

    def export_from_note(self, note_path: Path, output_path: Path) -> int:
        """Export all @citations used in a single note file.
        Equivalent to: papis export --all --output note.bib (then manual filter)
        """
        text = note_path.read_text(encoding="utf-8")
        cited_keys = [c.key for c in parse_citations(text)]
        return self.export_keys(cited_keys, output_path)

    def export_from_vault(self, notes: Path | NoteRepository, output_path: Path) -> int:
        """Collect all @citations from the entire vault and export them.
        """
        cited_keys: set[str] = set()

        # Determine the note files
        if hasattr(notes, "list_notes"):
            note_files = notes.list_notes()
        else:
            note_files = list(notes.rglob("*.md"))

        for md_file in note_files:
            try:
                text = md_file.read_text(encoding="utf-8")
                for c in parse_citations(text):
                    cited_keys.add(c.key)
            except Exception as e:
                logger.debug(f"Failed to parse citations for vault export: {e}")
        return self.export_keys(list(cited_keys), output_path)

    def get_bibtex_string(self, key: str) -> str | None:
        """Return BibTeX string for a single @key (for clipboard pasting).
        Reads type from entry._raw["type"] if available.
        """
        entry = self._bridge.get(key)
        if not entry:
            return None
        return entry_to_bibtex(entry)

    # ── Internal ──────────────────────────────────────────────────────

    def _write(self, entries: list[LiteratureEntry], output_path: Path) -> int:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = [
            "% Generated by Noteration",
            f"% {len(entries)} entries  —  {ts}",
            "% DO NOT edit manually; regenerate via Tools → Export BibTeX",
            "",
        ]
        body: list[str] = []
        for e in entries:
            body.append(entry_to_bibtex(e))
            body.append("")

        output_path.write_text("\n".join(header + body), encoding="utf-8")
        return len(entries)
