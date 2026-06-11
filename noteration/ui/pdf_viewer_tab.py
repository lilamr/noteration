"""noteration/ui/pdf_viewer_tab.py

PDF viewer tab with annotations, sidebar, and reading progress.
"""

from __future__ import annotations

import collections
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from noteration.vault_manager import VaultManager

from PySide6.QtCore import QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from noteration.logger import get_logger
from noteration.pdf.annotation_overlay import AnnotationOverlay
from noteration.pdf.annotations import Annotation, AnnotationStore, calculate_file_hash

logger = get_logger(__name__)

# ── backend detection ─────────────────────────────────────────────────────

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    _HAS_QTPDF = True
except ImportError:
    _HAS_QTPDF = False

_fitz: Any = None
_HAS_FITZ: bool | None = None


def _get_fitz() -> Any:
    global _fitz, _HAS_FITZ
    if _HAS_FITZ is None:
        try:
            import fitz as _f

            _fitz = _f
            _HAS_FITZ = True
            # Silence MuPDF warnings/errors
            try:
                _fitz.TOOLS.mupdf_display_errors(False)
            except Exception as e:
                logger.debug(f"Could not silence MuPDF errors: {e}")

        except ImportError:
            _HAS_FITZ = False
    return _fitz


def _has_fitz() -> bool:
    _get_fitz()
    return bool(_HAS_FITZ)


# ── Global Cache ──────────────────────────────────────────────────────────


class _GlobalRenderCache:
    """Cost-based LRU cache for PDF page pixmaps shared across all viewer tabs.
    Prevents memory bloat by evicting based on estimated memory usage (250MB limit).
    """

    _instance: _GlobalRenderCache | None = None
    _cache: collections.OrderedDict[tuple[str, int, float], tuple[QPixmap, int]]
    _MAX_COST: int
    _current_cost: int

    def __new__(cls) -> _GlobalRenderCache:
        if cls._instance is None:
            cls._instance = super(_GlobalRenderCache, cls).__new__(cls)
            cls._instance._cache = collections.OrderedDict()
            # 250 MB limit. ARGB32 pixmaps can be huge.
            cls._instance._MAX_COST = 250 * 1024 * 1024
            cls._instance._current_cost = 0
        return cls._instance

    def get(self, pdf_path: str, page_idx: int, zoom: float) -> QPixmap | None:
        key = (pdf_path, page_idx, round(zoom, 2))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key][0]
        return None

    def set(self, pdf_path: str, page_idx: int, zoom: float, pixmap: QPixmap) -> None:
        key = (pdf_path, page_idx, round(zoom, 2))
        # Estimate cost in bytes: width * height * (depth / 8)
        cost = pixmap.width() * pixmap.height() * (pixmap.depth() // 8)

        if key in self._cache:
            self._current_cost -= self._cache[key][1]

        # Evict until we have enough space for the new pixmap
        while self._current_cost + cost > self._MAX_COST and self._cache:
            _, (_, old_cost) = self._cache.popitem(last=False)
            self._current_cost -= old_cost

        self._cache[key] = (pixmap, cost)
        self._current_cost += cost
        self._cache.move_to_end(key)

    def clear(self, pdf_path: str | None = None) -> None:
        if pdf_path:
            keys_to_del = [k for k in self._cache if k[0] == pdf_path]
            for k in keys_to_del:
                val = self._cache.pop(k, None)
                if val:
                    self._current_cost -= val[1]
        else:
            self._cache.clear()
            self._current_cost = 0


_RENDER_CACHE = _GlobalRenderCache()


# ── MuPdf page widget ─────────────────────────────────────────────────────


class MuPdfPageWidget(QWidget):
    """Single PDF page widget rendered via PyMuPDF.
    """

    def __init__(
        self,
        doc,
        page_idx: int,
        zoom: float,
        overlay: AnnotationOverlay,
        pdf_path: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._doc = doc
        self._page_idx = page_idx
        self._zoom = zoom
        self._overlay = overlay
        self._pdf_path = pdf_path
        self._rendered = False

        # Container for stacking image and overlay
        self._container = QWidget(self)

        # QLabel for PDF image
        self._img_label = QLabel(self._container)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Overlay is mounted on top of container
        self._overlay.setParent(self._container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._container, 0, Qt.AlignmentFlag.AlignCenter)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._setup_placeholder()

    def _setup_placeholder(self) -> None:
        """Set fixed size before rendering based on PDF page rect."""
        if not self._doc:
            return

        try:
            page = self._doc[self._page_idx]
            r = page.rect
            w = int(r.width * self._zoom * 2.0)
            h = int(r.height * self._zoom * 2.0)
            self._img_label.setFixedSize(w, h)
            self._container.setFixedSize(w, h)
            self._overlay.setGeometry(0, 0, w, h)
            self.updateGeometry()
        except (AttributeError, ValueError, IndexError) as e:
            logger.error(f"Failed to setup placeholder for page {self._page_idx}: {e}")
        except Exception as e:
            logger.exception(
                f"Unexpected error in _setup_placeholder for page {self._page_idx}: {e}"
            )

    def render_if_needed(self) -> None:
        """Trigger render if not already rendered."""
        if not self._rendered:
            self._render()
            self._rendered = True

    def _render(self) -> None:
        # Check global cache first
        cached = _RENDER_CACHE.get(self._pdf_path, self._page_idx, self._zoom)
        if cached:
            self._img_label.setPixmap(cached)
            self._img_label.setFixedSize(cached.size())
            self._container.setFixedSize(cached.size())
            self._overlay.setGeometry(0, 0, cached.width(), cached.height())
            self._overlay.raise_()
            self.updateGeometry()
            return

        if not self._doc:
            return

        try:
            fitz = _get_fitz()
            page = self._doc[self._page_idx]
            # Render at 2x zoom for sharp baseline, then scale to target zoom
            mat = fitz.Matrix(self._zoom * 2.0, self._zoom * 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = QImage(
                pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888
            )
            qpix = QPixmap.fromImage(img)

            # Store in global cache
            _RENDER_CACHE.set(self._pdf_path, self._page_idx, self._zoom, qpix)

            self._img_label.setPixmap(qpix)
            self._img_label.setFixedSize(qpix.size())
            self._container.setFixedSize(qpix.size())
            self._overlay.setGeometry(0, 0, qpix.width(), qpix.height())
            self._overlay.raise_()
            self.updateGeometry()
        except (AttributeError, ValueError, IndexError) as e:
            self._img_label.setText(f"[Page data error: {e}]")
            logger.error(f"Render data error for page {self._page_idx}: {e}")
        except Exception as e:
            self._img_label.setText(f"[Render failed: {e}]")
            logger.exception(f"Unexpected render failure for page {self._page_idx}: {e}")

    def update_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self._rendered = False
        if self.isVisible():
            self._render()
            self._rendered = True
        else:
            self._setup_placeholder()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._overlay.raise_()


# ── MuPDF multi-page viewer ───────────────────────────────────────────────


class MuPdfViewer(QWidget):
    """All PDF pages arranged vertically.
    Emits page_changed(int) signal when the visible page changes.
    """

    page_changed = Signal(int)  # current page (0-indexed)

    def __init__(
        self, pdf_path: Path, papis_key: str, store: AnnotationStore, zoom: float = 1.0, parent=None
    ) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.papis_key = papis_key
        self._store = store
        self._zoom = zoom
        self._overlays: list[AnnotationOverlay] = []
        self._page_widgets: list[MuPdfPageWidget] = []

        fitz = _get_fitz()
        self._doc = fitz.open(str(pdf_path))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Scroll detection for progress update
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self._scroll)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._scroll.setWidget(self._container)

        self._build_pages()

        # Debounce scroll events
        self._scroll_timer = QTimer()
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(120)
        self._scroll_timer.timeout.connect(self._detect_visible_page)

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    @property
    def overlays(self) -> list[AnnotationOverlay]:
        return self._overlays

    def invalidate_render_cache(self) -> None:
        """Clear the pixmap cache for this PDF."""
        _RENDER_CACHE.clear(str(self.pdf_path))

    def _build_pages(self) -> None:
        self._overlays.clear()
        self._page_widgets.clear()

        for i in range(self._doc.page_count):
            page = self._doc[i]
            r = page.rect
            overlay = AnnotationOverlay(
                papis_key=self.papis_key,
                page_idx=i,
                store=self._store,
                page_width_pts=r.width,
                page_height_pts=r.height,
            )
            overlay.set_fitz_page(self._doc[i])
            self._overlays.append(overlay)

            pw = MuPdfPageWidget(self._doc, i, self._zoom, overlay, pdf_path=str(self.pdf_path))
            self._page_widgets.append(pw)
            self._layout.addWidget(pw)

        self._container.adjustSize()
        # Initial render of visible pages, queued to the end of the event loop
        QTimer.singleShot(0, self._render_visible_pages)

    def set_zoom(self, zoom: float) -> None:
        old_zoom = self._zoom
        self._zoom = zoom
        # Invalidate cache if zoom level changed significantly
        if round(old_zoom, 2) != round(zoom, 2):
            self.invalidate_render_cache()

        for pw in self._page_widgets:
            pw.update_zoom(zoom)
        self._container.adjustSize()
        self._render_visible_pages()

    def scroll_to_page(self, page_idx: int) -> None:
        if 0 <= page_idx < len(self._page_widgets):
            pw = self._page_widgets[page_idx]
            self._scroll.ensureWidgetVisible(pw, 0, 0)
            # Immediate render of the target page
            pw.render_if_needed()

    def set_annotation_mode(self, mode: str) -> None:
        for ov in self._overlays:
            ov.set_mode(mode)

    def refresh_overlays(self) -> None:
        for ov in self._overlays:
            ov.refresh()

    def search_text(self, query: str) -> list[tuple[int, tuple]]:
        results = []
        for i in range(self._doc.page_count):
            for rect in self._doc[i].search_for(query):
                results.append((i, (rect.x0, rect.y0, rect.x1, rect.y1)))
        return results

    # ── Scroll-based page detection & virtual rendering ───────────────

    def _on_scroll(self, _value: int) -> None:
        self._scroll_timer.start()
        self._render_visible_pages()

    def _render_visible_pages(self) -> None:
        """Render only pages that are currently visible in the viewport plus a buffer."""
        viewport_rect = self._scroll.viewport().rect()
        scroll_y = self._scroll.verticalScrollBar().value()

        for pw in self._page_widgets:
            # Map widget position to container coordinates
            pw_pos = pw.mapTo(self._container, pw.rect().topLeft())

            # Create a rect for the page in the viewport's coordinate system
            pw_rect_in_viewport = QRect(pw_pos.x(), pw_pos.y() - scroll_y, pw.width(), pw.height())

            # Render if visible or within 1 page height buffer (above or below)
            buffer = pw.height()
            expanded_viewport = viewport_rect.adjusted(0, -buffer, 0, buffer)

            if expanded_viewport.intersects(pw_rect_in_viewport):
                pw.render_if_needed()

    def _detect_visible_page(self) -> None:
        """Find the page most visible in the viewport."""
        viewport_rect = self._scroll.viewport().rect()
        best_page = 0
        best_area = 0

        for i, pw in enumerate(self._page_widgets):
            # Coordinates in container, then in viewport
            pw_pos_in_container = pw.mapTo(self._container, pw.rect().topLeft())
            scroll_y = self._scroll.verticalScrollBar().value()
            scroll_x = self._scroll.horizontalScrollBar().value()

            pw_rect_in_viewport = QRect(
                pw_pos_in_container.x() - scroll_x,
                pw_pos_in_container.y() - scroll_y,
                pw.width(),
                pw.height(),
            )
            intersection = viewport_rect.intersected(pw_rect_in_viewport)
            area = intersection.width() * intersection.height()
            if area > best_area:
                best_area = area
                best_page = i

        if best_area > 0:
            self.page_changed.emit(best_page)

    def closeEvent(self, event) -> None:
        """Explicitly release PDF resources to prevent file locking."""
        if self._doc:
            try:
                # Clear references in children to avoid use-after-close
                for pw in self._page_widgets:
                    pw._doc = None
                self._doc.close()
            except Exception as e:
                logger.error(f"Error closing PDF document: {e}")
            finally:
                self._doc = None
        super().closeEvent(event)


# ── PdfViewerTab ──────────────────────────────────────────────────────────


class PdfViewerTab(QWidget):
    """PDF viewer tab with annotations, sidebar, and reading progress."""

    insert_quote_requested = Signal(str, str, str)  # (text, papis_key, locator)
    insert_image_requested = Signal(str, str, str)  # (image_path, papis_key, locator)
    extract_requested = Signal()  # request to create note from all annots
    note_requested = Signal(str)  # request to open a specific note
    annotation_count_changed = Signal(int)

    def __init__(self, pdf_path: Path, papis_key: str, vault: "VaultManager", parent=None) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.papis_key = papis_key or pdf_path.stem
        self.vault = vault
        self.vault_path = vault.vault_path
        self.config = vault.config

        self._current_page = 0
        self._total_pages = 0
        self._zoom = 1.0
        self._annot_mode = "view"

        self._store = AnnotationStore(
            self.vault_path, on_changed=lambda: self.vault.request_git_status()
        )
        self._doc_ann = self._store.load(self.papis_key)
        self._pdf_index = vault.pdf_index

        self._qtpdf_view: "QPdfView | None" = None
        self._mupdf_viewer: MuPdfViewer | None = None

        self._setup_ui()
        self._setup_shortcuts()
        self._load_pdf()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())
        self._search_bar = self._build_search_bar()
        root.addWidget(self._search_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._viewer_stack = QStackedWidget()
        splitter.addWidget(self._viewer_stack)
        self._annot_panel = self._build_annot_panel()
        splitter.addWidget(self._annot_panel)
        splitter.setSizes([740, 240])
        root.addWidget(splitter)

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:palette(window);border-bottom:1px solid palette(mid);}"
        )
        frame.setFixedHeight(36)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(6, 2, 8, 2)
        lay.setSpacing(4)

        self._btn_prev = QPushButton("◀")
        self._btn_prev.setFixedWidth(28)
        self._btn_prev.setToolTip("Previous page [PgUp]")
        self._btn_prev.clicked.connect(self._prev_page)
        lay.addWidget(self._btn_prev)

        self._page_spin = QSpinBox()
        self._page_spin.setMinimum(1)
        self._page_spin.setFixedWidth(55)
        self._page_spin.valueChanged.connect(self._on_spin_changed)
        lay.addWidget(self._page_spin)

        self._lbl_total = QLabel("/ —")
        self._lbl_total.setStyleSheet("color:gray;font-size:12px;")
        lay.addWidget(self._lbl_total)

        self._btn_next = QPushButton("▶")
        self._btn_next.setFixedWidth(28)
        self._btn_next.setToolTip("Next page [PgDn]")
        self._btn_next.clicked.connect(self._next_page)
        lay.addWidget(self._btn_next)

        lay.addWidget(_vsep())

        self._btn_zm = QPushButton("−")
        self._btn_zm.setFixedWidth(24)
        self._btn_zm.clicked.connect(self._zoom_out)
        lay.addWidget(self._btn_zm)

        self._lbl_zoom = QLabel("100%")
        self._lbl_zoom.setFixedWidth(40)
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_zoom.setStyleSheet("font-size:12px;")
        lay.addWidget(self._lbl_zoom)

        self._btn_zp = QPushButton("+")
        self._btn_zp.setFixedWidth(24)
        self._btn_zp.clicked.connect(self._zoom_in)
        lay.addWidget(self._btn_zp)

        self._btn_zfit = QPushButton("Fit")
        self._btn_zfit.setFixedWidth(32)
        self._btn_zfit.clicked.connect(lambda: self._set_zoom(1.0))
        lay.addWidget(self._btn_zfit)

        lay.addWidget(_vsep())

        self._btn_hl = QPushButton("🟡 Highlight")
        self._btn_hl.setCheckable(True)
        self._btn_hl.setToolTip("Drag to highlight area")
        self._btn_hl.clicked.connect(lambda on: self._set_mode("highlight" if on else "view"))
        lay.addWidget(self._btn_hl)

        self._btn_cm = QPushButton("💬 Comment")
        self._btn_cm.setCheckable(True)
        self._btn_cm.setToolTip("Click to add comment")
        self._btn_cm.clicked.connect(lambda on: self._set_mode("comment" if on else "view"))
        lay.addWidget(self._btn_cm)

        self._btn_bm = QPushButton("🔖")
        self._btn_bm.setFixedWidth(32)
        self._btn_bm.setToolTip("Bookmark this page")
        self._btn_bm.clicked.connect(self._add_bookmark)
        lay.addWidget(self._btn_bm)

        self._btn_img = QPushButton("🖼 Image")
        self._btn_img.setCheckable(True)
        self._btn_img.setToolTip("Drag to capture image from PDF")
        self._btn_img.clicked.connect(lambda on: self._set_mode("image" if on else "view"))
        lay.addWidget(self._btn_img)

        self._btn_extract = QPushButton("📤 Extract")
        self._btn_extract.setToolTip("Export all annotations to a new Markdown note")
        self._btn_extract.clicked.connect(self.extract_requested.emit)
        lay.addWidget(self._btn_extract)

        lay.addWidget(_vsep())

        self._btn_toggle_annot = QPushButton("📋")
        self._btn_toggle_annot.setFixedWidth(32)
        self._btn_toggle_annot.setCheckable(True)
        self._btn_toggle_annot.setChecked(True)
        self._btn_toggle_annot.setToolTip("Toggle annotation panel [Ctrl+Alt+A]")
        self._btn_toggle_annot.clicked.connect(self._toggle_annot_panel)
        lay.addWidget(self._btn_toggle_annot)

        lay.addStretch()

        be = "QtPdf" if _HAS_QTPDF else ("PyMuPDF" if _has_fitz() else "—")
        lbl_be = QLabel(f"[{be}]")
        lbl_be.setStyleSheet("color:#bbb;font-size:10px;")
        lay.addWidget(lbl_be)

        return frame

    def _build_search_bar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:palette(window);border-bottom:1px solid palette(mid);}"
        )
        frame.setVisible(False)
        frame.setFixedHeight(32)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(4)

        lay.addWidget(QLabel("Search:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Type and press Enter…")
        self._search_input.returnPressed.connect(self._do_search)
        lay.addWidget(self._search_input)

        btn = QPushButton("Search")
        btn.clicked.connect(self._do_search)
        lay.addWidget(btn)

        self._lbl_search_result = QLabel("")
        self._lbl_search_result.setStyleSheet("color:gray;font-size:11px;")
        lay.addWidget(self._lbl_search_result)

        close = QPushButton("✕")
        close.setFixedWidth(22)
        close.clicked.connect(lambda: frame.setVisible(False))
        lay.addWidget(close)
        return frame

    def _build_annot_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(180)
        w.setMaximumWidth(260)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(5)

        hr = QHBoxLayout()
        lbl = QLabel("Annotations")
        lbl.setStyleSheet("font-weight:bold;font-size:13px;")
        hr.addWidget(lbl)
        hr.addStretch()
        self._lbl_count = QLabel("0")
        self._lbl_count.setStyleSheet(
            "font-size:10px;background:#E1F5EE;color:#0F6E56;padding:1px 6px;border-radius:8px;"
        )
        hr.addWidget(self._lbl_count)
        lay.addLayout(hr)

        fr = QHBoxLayout()
        self._chk_hl = QCheckBox("Highlight")
        self._chk_hl.setChecked(True)
        self._chk_hl.stateChanged.connect(self._refresh_annot_list)
        self._chk_cm = QCheckBox("Comment")
        self._chk_cm.setChecked(True)
        self._chk_cm.stateChanged.connect(self._refresh_annot_list)
        self._chk_bm = QCheckBox("Bookmark")
        self._chk_bm.setChecked(True)
        self._chk_bm.stateChanged.connect(self._refresh_annot_list)
        fr.addWidget(self._chk_hl)
        fr.addWidget(self._chk_cm)
        fr.addWidget(self._chk_bm)
        lay.addLayout(fr)

        self._annot_list = QListWidget()
        self._annot_list.setStyleSheet("font-size:11px;")
        self._annot_list.itemDoubleClicked.connect(self._on_annot_dblclick)
        self._annot_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._annot_list.customContextMenuRequested.connect(self._annot_context_menu)
        self._annot_list.itemSelectionChanged.connect(self._on_annot_selection_changed)
        lay.addWidget(self._annot_list, 1)

        grp = QGroupBox("Reading Progress")
        gl = QVBoxLayout(grp)
        gl.setContentsMargins(4, 4, 4, 4)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setStyleSheet(
            "QProgressBar{font-size:10px;border-radius:4px;}"
            "QProgressBar::chunk{background:#4CAF50;border-radius:4px;}"
        )
        gl.addWidget(self._progress_bar)
        self._lbl_progress = QLabel("Page 0 / 0")
        self._lbl_progress.setStyleSheet("font-size:10px;color:gray;")
        gl.addWidget(self._lbl_progress)
        lay.addWidget(grp)

        self._btn_insert = QPushButton("Insert to Editor")
        self._btn_insert.setEnabled(False)
        self._btn_insert.clicked.connect(self._on_insert_quote)
        lay.addWidget(self._btn_insert)

        self._btn_del = QPushButton("Delete Annotation")
        self._btn_del.setEnabled(False)
        self._btn_del.setStyleSheet("color:#c0392b;")
        self._btn_del.clicked.connect(self._on_delete_annot)
        lay.addWidget(self._btn_del)

        return w

    # ── Shortcuts ─────────────────────────────────────────────────────

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+F"), self, self._toggle_search)
        QShortcut(QKeySequence("Ctrl++"), self, self._zoom_in)
        QShortcut(QKeySequence("Ctrl+="), self, self._zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, self._zoom_out)
        QShortcut(QKeySequence("PgDown"), self, self._next_page)
        QShortcut(QKeySequence("PgUp"), self, self._prev_page)
        QShortcut(QKeySequence("Ctrl+Alt+A"), self, self._toggle_annot_panel)

    # ── Loading ───────────────────────────────────────────────────────

    def _load_pdf(self) -> None:
        if not self.pdf_path.exists():
            self._show_error(f"File not found:\n{self.pdf_path}")
            return

        self._pdf_index.find_or_register(self.pdf_path, self.papis_key)
        if not self._doc_ann.pdf_hash:
            self._doc_ann.pdf_hash = calculate_file_hash(self.pdf_path)
            self._store.save(self.papis_key)

        if _has_fitz():
            self._load_mupdf()
        elif _HAS_QTPDF:
            self._load_qtpdf()
        else:
            self._show_error("No PDF renderer found.\n\nInstall: pip install pymupdf")

    def _load_qtpdf(self) -> None:
        doc = QPdfDocument(self)
        doc.load(str(self.pdf_path))
        view = QPdfView(self)
        view.setDocument(doc)
        view.setPageMode(QPdfView.PageMode.MultiPage)
        view.setZoomMode(QPdfView.ZoomMode.Custom)
        self._qtpdf_view = view
        self._viewer_stack.addWidget(view)
        self._viewer_stack.setCurrentWidget(view)
        self._total_pages = doc.pageCount()
        self._finish_load()

    def _load_mupdf(self) -> None:
        viewer = MuPdfViewer(
            pdf_path=self.pdf_path,
            papis_key=self.papis_key,
            store=self._store,
            zoom=self._zoom,
        )
        # Connect scroll signal to update page & progress
        viewer.page_changed.connect(self._on_viewer_page_changed)

        for ov in viewer.overlays:
            ov.annotation_created.connect(self._on_ov_created)
            ov.annotation_deleted.connect(self._on_ov_deleted)
            ov.annotation_edited.connect(self._on_ov_edited)
            ov.jump_to_note_requested.connect(self._on_jump_to_note)

        self._mupdf_viewer = viewer
        self._viewer_stack.addWidget(viewer)
        self._viewer_stack.setCurrentWidget(viewer)
        self._total_pages = viewer.page_count
        self._finish_load()

    def _finish_load(self) -> None:
        self._page_spin.setMaximum(max(1, self._total_pages))
        self._lbl_total.setText(f"/ {self._total_pages}")

        last = self._doc_ann.last_page
        if 0 < last < self._total_pages:
            self._current_page = last
            self._page_spin.blockSignals(True)
            self._page_spin.setValue(last + 1)
            self._page_spin.blockSignals(False)
            if self._mupdf_viewer:
                QTimer.singleShot(200, lambda: self._mupdf_viewer.scroll_to_page(last))  # type: ignore[union-attr]

        self._update_progress()
        self._refresh_annot_list()

    def _show_error(self, msg: str) -> None:
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color:gray;padding:32px;")
        lbl.setWordWrap(True)
        self._viewer_stack.addWidget(lbl)
        self._viewer_stack.setCurrentWidget(lbl)

    # ── Navigation ────────────────────────────────────────────────────

    def _prev_page(self) -> None:
        if self._current_page > 0:
            self._set_page(self._current_page - 1)

    def _next_page(self) -> None:
        if self._current_page < self._total_pages - 1:
            self._set_page(self._current_page + 1)

    def _on_spin_changed(self, value: int) -> None:
        self._set_page(value - 1)

    def _on_viewer_page_changed(self, page_idx: int) -> None:
        """Called when user scrolls — update toolbar & progress without re-scrolling."""
        if page_idx == self._current_page:
            return
        self._current_page = page_idx
        self._page_spin.blockSignals(True)
        self._page_spin.setValue(page_idx + 1)
        self._page_spin.blockSignals(False)
        self._save_progress(page_idx)

    def _set_page(self, idx: int) -> None:
        """Navigate to specific page from buttons/spinbox."""
        idx = max(0, min(idx, self._total_pages - 1))
        self._current_page = idx
        self._page_spin.blockSignals(True)
        self._page_spin.setValue(idx + 1)
        self._page_spin.blockSignals(False)

        if self._qtpdf_view:
            nav = self._qtpdf_view.pageNavigator()
            if nav:
                nav.jump(idx, QPointF())
        if self._mupdf_viewer:
            self._mupdf_viewer.scroll_to_page(idx)

        self._save_progress(idx)

    def _toggle_annot_panel(self, on: bool | None = None) -> None:
        if on is None:
            on = not self._annot_panel.isVisible()
        self._annot_panel.setVisible(on)
        self._btn_toggle_annot.blockSignals(True)
        self._btn_toggle_annot.setChecked(on)
        self._btn_toggle_annot.blockSignals(False)

    def _save_progress(self, page_idx: int) -> None:
        progress = (page_idx + 1) / max(1, self._total_pages)
        self._doc_ann.last_page = page_idx
        self._doc_ann.reading_progress = progress
        self._store.save(self.papis_key)
        self._update_progress()

    # ── Zoom ──────────────────────────────────────────────────────────

    def _zoom_in(self) -> None:
        self._set_zoom(min(4.0, self._zoom + 0.25))

    def _zoom_out(self) -> None:
        self._set_zoom(max(0.25, self._zoom - 0.25))

    def _set_zoom(self, z: float) -> None:
        self._zoom = z
        self._lbl_zoom.setText(f"{int(z * 100)}%")
        if self._qtpdf_view:
            self._qtpdf_view.setZoomFactor(z)
        if self._mupdf_viewer:
            self._mupdf_viewer.set_zoom(z)

    # ── Annotation mode ───────────────────────────────────────────────

    def _set_mode(self, mode: str) -> None:
        self._annot_mode = mode
        self._btn_hl.setChecked(mode == "highlight")
        self._btn_cm.setChecked(mode == "comment")
        self._btn_img.setChecked(mode == "image")
        if self._mupdf_viewer:
            self._mupdf_viewer.set_annotation_mode(mode)

    def _add_bookmark(self) -> None:
        ann = Annotation(
            id=f"ann-{uuid.uuid4().hex[:8]}",
            type="bookmark",
            page=self._current_page,
            position=[0.0, 0.0],
            note=f"Bookmark page {self._current_page + 1}",
        )
        self._store.add_annotation(self.papis_key, ann)
        self._refresh_annot_list()

    # ── Search ────────────────────────────────────────────────────────

    def _toggle_search(self) -> None:
        vis = not self._search_bar.isVisible()
        self._search_bar.setVisible(vis)
        if vis:
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _do_search(self) -> None:
        q = self._search_input.text().strip()
        if not q:
            return
        if self._mupdf_viewer:
            results = self._mupdf_viewer.search_text(q)
            if results:
                self._set_page(results[0][0])
                self._lbl_search_result.setText(f"{len(results)} results")
            else:
                self._lbl_search_result.setText("Not found")
        else:
            self._lbl_search_result.setText("Search requires PyMuPDF")

    # ── Annotation panel ──────────────────────────────────────────────

    def _reload_doc_ann(self) -> None:
        """Reload DocumentAnnotations from store to keep it fresh."""
        self._doc_ann = self._store.load(self.papis_key, force_reload=True)

    def _refresh_annot_list(self) -> None:
        self._reload_doc_ann()
        self._annot_list.clear()
        show_hl = self._chk_hl.isChecked()
        show_cm = self._chk_cm.isChecked()
        show_bm = self._chk_bm.isChecked()
        count = 0

        for ann in self._doc_ann.annotations:
            if ann.type in ("highlight", "image") and not show_hl:
                continue
            if ann.type == "comment" and not show_cm:
                continue
            if ann.type == "bookmark" and not show_bm:
                continue

            # Badge color matching annotation color
            color_hex = ann.color if ann.type in ("highlight", "image") else "#FFF9C4"
            color = QColor(color_hex)
            color.setAlpha(180)

            if ann.type == "highlight":
                excerpt = (ann.text_content or "(drag area)")[:35]
                label = f"🟡  Page {ann.page + 1}  {excerpt}"
                if ann.note:
                    label += f"\n   ↳ {ann.note[:35]}"
            elif ann.type == "image":
                label = f"🖼  Page {ann.page + 1}  (image)"
                if ann.note:
                    label += f"\n   ↳ {ann.note[:35]}"
            elif ann.type == "comment":
                label = f"💬  Page {ann.page + 1}  {ann.note[:40]}"
            else:
                label = f"🔖  Page {ann.page + 1}  {ann.note or 'Bookmark'}"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, ann)
            item.setBackground(color)
            if ann.tags:
                item.setToolTip(", ".join(ann.tags))
            self._annot_list.addItem(item)
            count += 1

        self._lbl_count.setText(str(count))
        self.annotation_count_changed.emit(count)

    def _update_progress(self) -> None:
        pct = int(self._doc_ann.reading_progress * 100)
        self._progress_bar.setValue(pct)
        self._progress_bar.setFormat(f"{pct}%")
        self._lbl_progress.setText(f"Page {self._current_page + 1} / {self._total_pages}")

    # ── Selection handling ────────────────────────────────────────────

    def _on_annot_selection_changed(self) -> None:
        sel = self._annot_list.selectedItems()
        has = bool(sel)
        self._btn_del.setEnabled(has)
        if has:
            ann: Annotation = sel[0].data(Qt.ItemDataRole.UserRole)
            # Enable button for text highlights OR image captures
            can = bool(
                ann
                and (
                    (ann.type == "highlight" and ann.text_content)
                    or (ann.type == "image" and ann.image_path)
                )
            )
            self._btn_insert.setEnabled(can)
        else:
            self._btn_insert.setEnabled(False)

    def _on_annot_dblclick(self, item: QListWidgetItem) -> None:
        ann: Annotation = item.data(Qt.ItemDataRole.UserRole)
        if ann:
            self._set_page(ann.page)

    def _annot_context_menu(self, pos) -> None:
        item = self._annot_list.itemAt(pos)
        if not item:
            return
        ann: Annotation = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        act_jump = menu.addAction(f"Go to Page {ann.page + 1}")
        act_ins = None
        act_ins_img = None

        if ann.type == "highlight":
            if ann.text_content:
                act_ins = menu.addAction("Insert Text to Editor")
            if ann.image_path:
                act_ins_img = menu.addAction("Insert Image to Editor")
        elif ann.type == "image" and ann.image_path:
            act_ins_img = menu.addAction("Insert Image to Editor")

        menu.addSeparator()
        act_del = menu.addAction("Delete")

        chosen = menu.exec(self._annot_list.mapToGlobal(pos))
        if chosen == act_jump:
            self._set_page(ann.page)
        elif act_ins and chosen == act_ins:
            self.insert_quote_requested.emit(ann.text_content, self.papis_key, f"p.{ann.page + 1}")
        elif act_ins_img and chosen == act_ins_img:
            self.insert_image_requested.emit(ann.image_path, self.papis_key, f"p.{ann.page + 1}")
        elif chosen == act_del:
            self._on_delete_annot()

    def _on_insert_quote(self) -> None:
        sel = self._annot_list.selectedItems()
        if not sel:
            return
        ann: Annotation = sel[0].data(Qt.ItemDataRole.UserRole)
        if ann:
            loc = f"p.{ann.page + 1}"
            if ann.type == "image" and ann.image_path:
                self.insert_image_requested.emit(ann.image_path, self.papis_key, loc)
            elif ann.text_content:
                self.insert_quote_requested.emit(ann.text_content, self.papis_key, loc)

    def _on_delete_annot(self) -> None:
        sel = self._annot_list.selectedItems()
        if not sel:
            return
        ann: Annotation = sel[0].data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self,
            "Delete Annotation",
            f"Delete this annotation?\n\n{ann.type.capitalize()} • Page {ann.page + 1}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._store.remove_annotation(self.papis_key, ann.id)
            self._refresh_annot_list()
            if self._mupdf_viewer:
                self._mupdf_viewer.refresh_overlays()

    # ── Overlay callbacks ─────────────────────────────────────────────

    def _on_ov_created(self, ann: Annotation) -> None:
        """Called by overlay → reload store & refresh sidebar."""
        self._refresh_annot_list()

    def _on_ov_deleted(self, ann_id: str) -> None:
        self._refresh_annot_list()

    def _on_ov_edited(self, ann: Annotation) -> None:
        self._refresh_annot_list()

    def _on_jump_to_note(self, note_path: str) -> None:
        self.note_requested.emit(Path(note_path).stem)

    def closeEvent(self, event) -> None:
        """Clear cache and shutdown viewer when tab is closed."""
        if self._mupdf_viewer:
            self._mupdf_viewer.close()

        # Explicitly clear cache for this PDF
        _RENDER_CACHE.clear(str(self.pdf_path))

        super().closeEvent(event)


# ── helpers ───────────────────────────────────────────────────────────────


def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setStyleSheet("color:palette(mid);")
    sep.setFixedWidth(1)
    return sep
