"""
noteration/editor/wiki_links.py
Parser [[wiki-link]] dan @citation dari teks Markdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_WIKI_PATTERN = re.compile(r'\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]')
_CITATION_PATTERN = re.compile(r'@([A-Za-z][A-Za-z0-9_:\-]+)')


@dataclass
class WikiLink:
    target: str          # nama note target (tanpa .md)
    heading: str | None  # anchor heading jika ada
    alias: str | None    # teks tampilan jika ada
    start: int           # posisi karakter di teks
    end: int


@dataclass
class Citation:
    key: str
    start: int
    end: int


def parse_wiki_links(text: str) -> list[WikiLink]:
    """Ekstrak semua [[wiki-link]] dari teks."""
    links = []
    for m in _WIKI_PATTERN.finditer(text):
        links.append(WikiLink(
            target=m.group(1).strip(),
            heading=m.group(2).strip() if m.group(2) else None,
            alias=m.group(3).strip() if m.group(3) else None,
            start=m.start(),
            end=m.end(),
        ))
    return links


def parse_citations(text: str) -> list[Citation]:
    """Ekstrak semua @citation dari teks."""
    return [
        Citation(key=m.group(1), start=m.start(), end=m.end())
        for m in _CITATION_PATTERN.finditer(text)
    ]


def extract_headings(text: str) -> list[tuple[int, str]]:
    """
    Ekstrak heading dari Markdown.
    Return list of (level, title).
    """
    headings = []
    in_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        m = re.match(r'^(#{1,6})\s+(.+)', line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((level, title))
    return headings


def resolve_link(target: str, vault_path: Path) -> Path | None:
    """
    Temukan file note yang sesuai dengan target wiki-link.
    Mendukung:
    - nama file biasai: "idea-1" → notes/idea-1.md
    - path relatif: "drafts/idea-1" → notes/drafts/idea-1.md
    - heading: [[note#heading]]
    """
    notes_dir = vault_path / "notes"

    # Handle path like "drafts/idea-1"
    if "/" in target:
        direct = notes_dir / f"{target}.md"
        if direct.exists():
            return direct
        direct = notes_dir / target
        if direct.exists() and direct.is_file():
            return direct

    # Try as-is first (without extension)
    candidates = [
        notes_dir / f"{target}.md",
        notes_dir / target,
    ]
    for c in candidates:
        if c.exists():
            return c

    # Case-insensitive search
    target_lower = target.lower()
    for md_file in notes_dir.rglob("*.md"):
        stem = md_file.stem
        # Match: "idea-1" matches "idea-1.md"
        # Also: "drafts/idea-1" path would match
        if stem.lower() == target_lower:
            return md_file
        # Match just the filename part
        if stem.lower() == target.split("/")[-1].lower():
            return md_file

    return None
