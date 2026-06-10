"""noteration/literature/csl_renderer.py
CSL (Citation Style Language) renderer using citeproc-py.
Transforms LiteratureEntry into formatted citation strings.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Any

if TYPE_CHECKING:
    from noteration.literature.papis_bridge import LiteratureEntry

_HAS_CITEPROC = False
try:
    from citeproc import (
        CitationStylesStyle,
        CitationStylesBibliography,
        Citation,
        CitationItem,
        formatter,
    )
    from citeproc.source.json import CiteProcJSON

    _HAS_CITEPROC = True
except ImportError:
    pass


class CSLRenderer:
    """Handles CSL-based rendering for literature citations.
    """

    def __init__(self, style_name: str = "apa", custom_style_path: Optional[Path] = None) -> None:
        self.style_name = style_name
        self.custom_style_path = custom_style_path
        self._style: Optional[CitationStylesStyle] = None
        self._bib: Optional[CitationStylesBibliography] = None
        self._source: Optional[CiteProcJSON] = None
        self._initialized = False

    def is_available(self) -> bool:
        return _HAS_CITEPROC

    def _get_style_path(self, style_path: Optional[Path] = None) -> Path:
        """Resolve the path to the CSL style file."""
        if style_path:
            return style_path
        if self.custom_style_path and self.custom_style_path.exists():
            return self.custom_style_path

        # Fallback to library-bundled style
        try:
            from citeproc_styles import get_style_filepath

            return Path(get_style_filepath(self.style_name))
        except Exception:
            return Path(self.style_name)

    def _entry_to_csl_json(self, entry: LiteratureEntry) -> dict:
        """Convert Papis LiteratureEntry to CSL-JSON format."""
        # Map known fields to CSL-JSON
        csl: dict[str, Any] = {
            "id": entry.key,
            "title": entry.title,
            "DOI": entry.doi,
            "ISBN": entry.isbn,
            "volume": entry.volume,
            "issue": entry.issue,
            "page": entry.page,
        }

        # Determine type
        if entry.journal:
            csl["type"] = "article-journal"
            csl["container-title"] = entry.journal
        elif entry.publisher:
            csl["type"] = "book"
            csl["publisher"] = entry.publisher
        else:
            csl["type"] = "article"

        # Parse date
        if entry.year.isdigit():
            csl["issued"] = {"date-parts": [[int(entry.year)]]}
        else:
            csl["issued"] = {"raw": entry.year}

        # Parse authors
        if entry.author:
            authors = []
            for a in entry.author.split(";"):
                if "," in a:
                    parts = a.strip().split(",")
                    if len(parts) == 2:
                        authors.append({"family": parts[0].strip(), "given": parts[1].strip()})
                    else:
                        authors.append({"literal": a.strip()})
                else:
                    authors.append({"literal": a.strip()})
            csl["author"] = authors

        return csl

    def render_citations(
        self, entries: List[LiteratureEntry], style_path: Optional[Path] = None
    ) -> Dict[str, str]:
        """Render a list of entries into a mapping of {key: formatted_string}.
        """
        if not self.is_available() or not entries:
            return {e.key: f"@{e.key}" for e in entries}

        try:
            csl_data = [self._entry_to_csl_json(e) for e in entries]

            source = CiteProcJSON(csl_data)

            # Resolve style path
            final_style_path = self._get_style_path(style_path)

            style = CitationStylesStyle(str(final_style_path), validate=False)
            bib = CitationStylesBibliography(style, source, formatter.html)

            results = {}
            for entry in entries:
                citation = Citation([CitationItem(entry.key)])
                bib.register(citation)
                # render_citation returns a list of fragments, we join them
                rendered = bib.cite(citation, lambda x: x)
                # citeproc-py returns list of fragments, join into string
                results[entry.key] = "".join(rendered)

            return results
        except Exception as err:
            import logging

            logging.getLogger("noteration").error(f"CSL rendering failed: {err}")
            return {entry.key: f"@{entry.key}" for entry in entries}

    def render_bibliography(
        self, entries: List[LiteratureEntry], style_path: Optional[Path] = None
    ) -> List[str]:
        """Render a full bibliography for the given entries."""
        if not self.is_available() or not entries:
            return [f"@{entry.key}" for entry in entries]

        try:
            csl_data = [self._entry_to_csl_json(e) for e in entries]
            source = CiteProcJSON(csl_data)
            style = CitationStylesStyle(
                str(style_path) if style_path else self.style_name, validate=False
            )
            bib = CitationStylesBibliography(style, source, formatter.html)

            for entry in entries:
                bib.register(Citation([CitationItem(entry.key)]))

            return [str(item) for item in bib.bibliography()]
        except Exception as err:
            import logging

            logging.getLogger("noteration").error(f"Bibliography rendering failed: {err}")
            return [f"@{entry.key}: Metadata error" for entry in entries]
