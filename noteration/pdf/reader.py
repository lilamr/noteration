"""
noteration/pdf/reader.py

Dual-backend PDF rendering wrapper:
  1. PyMuPDF (fitz) — extract text, coordinates, render to QPixmap
  2. QtPdf        — used directly by QPdfView in the viewer tab

The PdfReader class is used by the overlay & annotation engine to:
  - Render pages to QPixmap at a specific zoom level
  - Extract text + bounding-box coordinates per word
  - Search text (for Ctrl+F feature)
  - Verify PDF hash
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple
from collections import OrderedDict

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import QRectF

_fitz: Any = None

def get_fitz() -> Any:
    global _fitz
    if _fitz is None:
        try:
            import fitz  # type: ignore
            _fitz = fitz
        except ImportError:
            pass
    return _fitz

def has_fitz() -> bool:
    return get_fitz() is not None


@dataclass
class TextSpan:
    """A single word / text span with its position on the page (in PDF points)."""
    text: str
    bbox: tuple[float, float, float, float]   # x0, y0, x1, y1
    page: int


@dataclass
class PageInfo:
    width: float        # in PDF points
    height: float
    page_index: int


class RenderCache:
    """Simple LRU cache for QPixmap renders."""
    def __init__(self, max_size: int = 15) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[Tuple[int, float], QPixmap] = OrderedDict()

    def get(self, page_idx: int, zoom: float) -> QPixmap | None:
        key = (page_idx, round(zoom, 2))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, page_idx: int, zoom: float, pixmap: QPixmap) -> None:
        key = (page_idx, round(zoom, 2))
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = pixmap
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


class PdfReader:
    """
    PyMuPDF wrapper for PDF rendering & text extraction.
    If fitz is not available, all methods return empty values or None.
    """

    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = pdf_path
        self._doc = None
        self._render_cache = RenderCache(max_size=15)

        fitz = get_fitz()
        if not fitz:
            return
        if not pdf_path.exists():
            return
        try:
            self._doc = fitz.open(str(pdf_path))
        except Exception as e:
            print(f"[PdfReader] Failed to open {pdf_path}: {e}")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._doc is not None

    @property
    def page_count(self) -> int:
        return self._doc.page_count if self._doc else 0

    def page_info(self, page_idx: int) -> PageInfo | None:
        if not self._doc or page_idx >= self.page_count:
            return None
        page = self._doc[page_idx]
        r = page.rect
        return PageInfo(width=r.width, height=r.height, page_index=page_idx)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render_page(self, page_idx: int, zoom: float = 1.0) -> QPixmap | None:
        """
        Render a single PDF page to QPixmap.
        zoom: 1.0 = 72 dpi, 2.0 = 144 dpi (for HiDPI screens).
        """
        if not self._doc or page_idx >= self.page_count:
            return None
            
        # Check cache first
        cached = self._render_cache.get(page_idx, zoom)
        if cached:
            return cached
            
        try:
            fitz = get_fitz()
            page = self._doc[page_idx]
            mat = fitz.Matrix(zoom * 2.0, zoom * 2.0)   # 2× = ~144 dpi baseline
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Convert fitz Pixmap → QImage → QPixmap
            img = QImage(
                pix.samples,
                pix.width, pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )
            pixmap = QPixmap.fromImage(img)
            
            # Save to cache
            self._render_cache.set(page_idx, zoom, pixmap)
            
            return pixmap
        except Exception as e:
            print(f"[PdfReader] render_page failed on page {page_idx}: {e}")
            return None

    # ------------------------------------------------------------------
    # Text Extraction
    # ------------------------------------------------------------------

    def extract_text_spans(self, page_idx: int) -> list[TextSpan]:
        """
        Extract all text spans along with their bounding boxes.
        Used for:
        - Displaying accurate highlight overlays
        - Fuzzy search
        """
        if not self._doc or page_idx >= self.page_count:
            return []
        try:
            fitz = get_fitz()
            page = self._doc[page_idx]
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            spans: list[TextSpan] = []
            for block in blocks:
                if block.get("type") != 0:   # 0 = text, 1 = image
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        txt = span.get("text", "").strip()
                        if txt:
                            b = span["bbox"]
                            spans.append(TextSpan(text=txt, bbox=tuple(b), page=page_idx))
            return spans
        except Exception:
            return []

    def extract_page_text(self, page_idx: int) -> str:
        """Get plain text for a single page."""
        if not self._doc or page_idx >= self.page_count:
            return ""
        try:
            return self._doc[page_idx].get_text()
        except Exception:
            return ""

    def extract_full_text(self) -> str:
        """Get plain text for the entire document."""
        return "\n\n".join(
            self.extract_page_text(i) for i in range(self.page_count)
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_text(self, query: str) -> list[tuple[int, tuple[float, float, float, float]]]:
        """
        Search for text within the entire document.
        Returns: list of (page_idx, bbox).
        """
        if not self._doc or not query:
            return []
        results: list[tuple[int, tuple]] = []
        for page_idx in range(self.page_count):
            page = self._doc[page_idx]
            hits = page.search_for(query)
            for rect in hits:
                results.append((page_idx, (rect.x0, rect.y0, rect.x1, rect.y1)))
        return results

    # ------------------------------------------------------------------
    # Coordinate Helpers
    # ------------------------------------------------------------------

    def pdf_to_widget_coords(
        self,
        bbox: tuple[float, float, float, float],
        page_idx: int,
        zoom: float,
        widget_width: int,
    ) -> QRectF:
        """
        Convert PDF points coordinates → pixels in widget (after zoom & scale).
        Assumes page is fit to widget_width.
        """
        info = self.page_info(page_idx)
        if info is None:
            return QRectF()
        scale = (widget_width / info.width) * zoom
        x0, y0, x1, y1 = bbox
        return QRectF(x0 * scale, y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._doc:
            self._doc.close()
            self._doc = None
        self._render_cache.clear()

    def __del__(self) -> None:
        self.close()
