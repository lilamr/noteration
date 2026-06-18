"""noteration/pdf/workers.py

Background workers for PDF operations (rendering, metadata, text extraction).
These workers use PyMuPDF (fitz) and are designed to run in separate QThreads
to keep the UI responsive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QPixmap

from noteration.logger import get_logger
from noteration.pdf.reader import PdfReader, has_fitz
from noteration.utils.qt_helpers import BaseWorker

logger = get_logger(__name__)

def _get_fitz() -> Any:
    try:
        import fitz
        return fitz
    except ImportError:
        return None


class PdfMetadataWorker(BaseWorker):
    """Worker for fetching PDF page dimensions in background.
    """

    finished = Signal(list)  # list of (page_idx, width, height)

    def __init__(self, pdf_path: str) -> None:
        super().__init__()
        self._pdf_path = pdf_path

    def run(self) -> None:
        """Fetch all page rectangles in a background thread."""
        try:
            fitz = _get_fitz()
            if not fitz:
                self.error.emit("PyMuPDF not available")
                return

            doc = fitz.open(self._pdf_path)
            metadata = []
            for i in range(doc.page_count):
                page = doc[i]
                r = page.rect
                metadata.append((i, r.width, r.height))
            doc.close()
            self.finished.emit(metadata)
        except Exception as e:
            logger.error(f"PdfMetadataWorker failed: {e}")
            self.error.emit(str(e))


class PdfTextWorker(BaseWorker):
    """Worker for extracting text words and searching within PDF pages in background.
    """

    finished = Signal(int, list)  # (page_idx, words_list)
    search_finished = Signal(str, list)  # (query, results_list)
    error = Signal(str)

    def __init__(self, pdf_path: str) -> None:
        super().__init__()
        self._pdf_path = Path(pdf_path)
        self._reader: Optional[PdfReader] = None

    def _ensure_reader(self) -> bool:
        if self._reader:
            return True
        try:
            if not has_fitz():
                return False
            self._reader = PdfReader(self._pdf_path)
            return self._reader.is_open
        except Exception as e:
            logger.error(f"Text worker failed to open PDF: {e}")
            return False

    @Slot(int)
    def extract_words(self, page_idx: int) -> None:
        """Extract words for a specific page."""
        try:
            if not self._ensure_reader() or self._reader is None:
                return

            if self._reader._doc is None:
                return
            words = self._reader._doc[page_idx].get_text("words")
            self.finished.emit(page_idx, words)
        except Exception as e:
            logger.exception(f"Text worker failed for page {page_idx}: {e}")
            self.error.emit(str(e))

    @Slot(str)
    def search_text(self, query: str) -> None:
        """Search for text within the entire document asynchronously."""
        try:
            if not self._ensure_reader() or self._reader is None or not query:
                self.search_finished.emit(query, [])
                return

            results = self._reader.search_text(query)
            self.search_finished.emit(query, results)
        except Exception as e:
            logger.error(f"Text worker search failed: {e}")
            self.search_finished.emit(query, [])

    @Slot()
    def cleanup(self) -> None:
        """Close the document and release resources."""
        if self._reader:
            self._reader.close()
            self._reader = None


class PdfRenderWorker(BaseWorker):
    """Worker for asynchronous PDF page rendering and clip capture.
    """

    finished = Signal(int, QPixmap)
    clip_finished = Signal(int, bytes, list)  # (page_idx, image_bytes, rect_pts)
    error = Signal(int, str)

    def __init__(self, pdf_path: str) -> None:
        super().__init__()
        self._pdf_path = Path(pdf_path)
        self._reader: Optional[PdfReader] = None

    def _ensure_reader(self) -> bool:
        if self._reader:
            return True
        try:
            if not has_fitz():
                return False
            self._reader = PdfReader(self._pdf_path)
            return self._reader.is_open
        except Exception as e:
            logger.error(f"Render worker failed to open PDF: {e}")
            return False

    @Slot(int, float)
    def render_page(self, page_idx: int, zoom: float) -> None:
        """Render a specific page at a specific zoom level."""
        try:
            if not self._ensure_reader() or self._reader is None:
                return

            qpix = self._reader.render_page(page_idx, zoom)
            if qpix:
                self.finished.emit(page_idx, qpix)
            else:
                self.error.emit(page_idx, "Rendering failed")
        except Exception as e:
            logger.exception(f"Render worker failed for page {page_idx}: {e}")
            self.error.emit(page_idx, str(e))

    @Slot(int, list, float)
    def render_clip(self, page_idx: int, rect_pts: list[float], zoom: float) -> None:
        """Capture a rectangular area and emit its image bytes."""
        try:
            if not self._ensure_reader() or self._reader is None:
                return

            img_bytes = self._reader.render_clip(page_idx, rect_pts, zoom)
            if img_bytes:
                self.clip_finished.emit(page_idx, img_bytes, rect_pts)
        except Exception as e:
            logger.error(f"Render worker clip failed: {e}")

    @Slot()
    def cleanup(self) -> None:
        """Close the document and release resources."""
        if self._reader:
            self._reader.close()
            self._reader = None
