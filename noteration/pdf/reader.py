"""
noteration/pdf/reader.py

Wrapper PDF rendering dual-backend:
  1. PyMuPDF (fitz) — ekstrak teks, koordinat, render ke QPixmap
  2. QtPdf        — dipakai langsung oleh QPdfView di viewer tab

Class PdfReader dipakai oleh overlay & annotation engine untuk:
  - Render halaman ke QPixmap dengan zoom tertentu
  - Ekstrak teks + koordinat bounding-box per kata
  - Cari teks (untuk fitur Ctrl+F)
  - Verifikasi hash PDF
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import QRectF

try:
    import fitz  # type: ignore   # pymupdf
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False


@dataclass
class TextSpan:
    """Satu kata / span teks dengan posisi di halaman (dalam PDF points)."""
    text: str
    bbox: tuple[float, float, float, float]   # x0, y0, x1, y1
    page: int


@dataclass
class PageInfo:
    width: float        # dalam PDF points
    height: float
    page_index: int


class PdfReader:
    """
    Wrapper PyMuPDF untuk rendering & ekstraksi teks PDF.
    Jika fitz tidak tersedia, semua method mengembalikan nilai kosong / None.
    """

    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = pdf_path
        self._doc = None

        if not _HAS_FITZ:
            return
        if not pdf_path.exists():
            return
        try:
            self._doc = fitz.open(str(pdf_path))
        except Exception as e:
            print(f"[PdfReader] Gagal membuka {pdf_path}: {e}")

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
        Render satu halaman PDF ke QPixmap.
        zoom: 1.0 = 72 dpi, 2.0 = 144 dpi (untuk layar HiDPI).
        """
        if not self._doc or page_idx >= self.page_count:
            return None
        try:
            page = self._doc[page_idx]
            mat = fitz.Matrix(zoom * 2.0, zoom * 2.0)   # 2× = ~144 dpi baseline
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Konversi fitz Pixmap → QImage → QPixmap
            img = QImage(
                pix.samples,
                pix.width, pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )
            return QPixmap.fromImage(img)
        except Exception as e:
            print(f"[PdfReader] render_page gagal halaman {page_idx}: {e}")
            return None

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    def extract_text_spans(self, page_idx: int) -> list[TextSpan]:
        """
        Ekstrak semua span teks beserta bounding-box-nya.
        Digunakan untuk:
        - Menampilkan highlight overlay yang tepat
        - Fuzzy search
        """
        if not self._doc or page_idx >= self.page_count:
            return []
        try:
            page = self._doc[page_idx]
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            spans: list[TextSpan] = []
            for block in blocks:
                if block.get("type") != 0:   # 0 = teks, 1 = gambar
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
        """Plain text satu halaman."""
        if not self._doc or page_idx >= self.page_count:
            return ""
        try:
            return self._doc[page_idx].get_text()
        except Exception:
            return ""

    def extract_full_text(self) -> str:
        """Plain text seluruh dokumen."""
        return "\n\n".join(
            self.extract_page_text(i) for i in range(self.page_count)
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_text(self, query: str) -> list[tuple[int, tuple[float, float, float, float]]]:
        """
        Cari teks dalam seluruh dokumen.
        Return: list of (page_idx, bbox).
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
    # Coordinate helpers
    # ------------------------------------------------------------------

    def pdf_to_widget_coords(
        self,
        bbox: tuple[float, float, float, float],
        page_idx: int,
        zoom: float,
        widget_width: int,
    ) -> QRectF:
        """
        Konversi koordinat PDF points → pixel di widget (setelah zoom & scale).
        Mengasumsikan halaman di-fit ke widget_width.
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

    def __del__(self) -> None:
        self.close()
