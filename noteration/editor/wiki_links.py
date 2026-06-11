"""noteration/editor/wiki_links.py
Parser for [[wiki-link]] and @citation from Markdown text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


_WIKI_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")
_CITATION_PATTERN = re.compile(r"@([A-Za-z][A-Za-z0-9_:\-]+)(?:\[([^\]]+)\])?")


@dataclass
class WikiLink:
    target: str  # target note name (without .md)
    heading: str | None  # anchor heading if present
    alias: str | None  # display text if present
    start: int  # character position in text
    end: int


@dataclass
class Citation:
    key: str
    locator: str | None = None
    start: int = 0
    end: int = 0


def parse_wiki_links(text: str) -> list[WikiLink]:
    """Extract all [[wiki-link]] tokens from text."""
    links = []
    for m in _WIKI_PATTERN.finditer(text):
        links.append(
            WikiLink(
                target=m.group(1).strip(),
                heading=m.group(2).strip() if m.group(2) else None,
                alias=m.group(3).strip() if m.group(3) else None,
                start=m.start(),
                end=m.end(),
            )
        )
    return links


def parse_citations(text: str) -> list[Citation]:
    """Extract all @citation[locator] tokens from text."""
    return [
        Citation(key=m.group(1), locator=m.group(2), start=m.start(), end=m.end())
        for m in _CITATION_PATTERN.finditer(text)
    ]


def extract_headings(text: str) -> list[tuple[int, str]]:
    """Extract headings from Markdown content.
    Returns a list of (level, title).
    """
    headings = []
    in_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((level, title))
    return headings


def resolve_link(target: str, vault_path: Path) -> Path | None:
    """Resolve a wiki-link target to its corresponding note file.
    Supports:
    - standard filename: "idea-1" → notes/idea-1.md
    - relative path: "drafts/idea-1" → notes/drafts/idea-1.md
    - headings: [[note#heading]]
    """
    notes_dir = vault_path / "notes"

    # Handle paths like "drafts/idea-1"
    if "/" in target:
        direct = notes_dir / f"{target}.md"
        if direct.exists():
            return direct
        direct = notes_dir / target
        if direct.exists() and direct.is_file():
            return direct

    # Try direct lookup (without extension)
    candidates = [
        notes_dir / f"{target}.md",
        notes_dir / target,
    ]
    for c in candidates:
        if c.exists():
            return c

    # Case-insensitive global search
    target_lower = target.lower()

    note_files = []
    if not isinstance(notes_dir, Path) and hasattr(notes_dir, "list_notes"):
        note_files = notes_dir.list_notes()
        actual_notes_dir = notes_dir.notes_dir  # type: ignore
    else:
        note_files = list(notes_dir.rglob("*.md"))
        actual_notes_dir = notes_dir

    for md_file in note_files:
        stem = md_file.stem
        # Match: "idea-1" matches "idea-1.md" (case-insensitive)
        if stem.lower() == target_lower:
            return md_file
        # Match relative path if slash is in target, or match stem if no slash is in target
        if "/" in target:
            try:
                rel_path = str(md_file.relative_to(actual_notes_dir)).lower().replace("\\", "/")
                if rel_path == f"{target_lower}.md" or rel_path == target_lower:
                    return md_file
            except ValueError:
                continue
        else:
            if stem.lower() == target.split("/")[-1].lower():
                return md_file

    return None
