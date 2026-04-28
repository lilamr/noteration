"""
noteration/ui/pdf_viewer_tab.py

PDF viewer tab dengan anotasi, sidebar, dan progress baca.

Perbaikan:
  - AnnotationOverlay menerima event mouse dengan benar (tidak diblok scroll area)
  - Highlight ditampilkan sebagai kotak semi-transparan berwarna
  - Sidebar anotasi terupdate tiap kali anotasi dibuat/dihapus/diedit
  - Progress bar terupdate saat user scroll (berbasis halaman yang terlihat)
  - _set_page + scroll sync dua arah (tombol ↔ scroll)
"""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QSplitter, QListWidget, QListWidgetItem,
    QFrame, QStackedWidget, QLineEdit, QProgressBar, QMenu,
    QMessageBox, QCheckBox, QGroupBox, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QPointF, QTimer, QRect
from PySide6.QtGui import QShortcut, QKeySequence, QImage, QPixmap, QColor

from noteration.config import NoterationConfig
from noteration.pdf.annotations import AnnotationStore, Annotation, hash_pdf
from noteration.pdf.pdf_index import PdfIndex
from noteration.pdf.annotation_overlay import AnnotationOverlay

# ── backend detection ─────────────────────────────────────────────────────

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
    _HAS_QTPDF = True
except ImportError:
    _HAS_QTPDF = False

try:
    import fitz  # type: ignore
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False


# ── MuPDF page widget ─────────────────────────────────────────────────────

class MuPdfPageWidget(QWidget):
    """
    Widget satu halaman PDF yang dirender via PyMuPDF.
    """

    def __init__(self, doc, page_idx: int, zoom: float,
                 overlay: AnnotationOverlay, parent=None) -> None:
        super().__init__(parent)
        self._doc      = doc
        self._page_idx = page_idx
        self._zoom     = zoom
        self._overlay  = overlay

        # Container untuk menumpuk gambar dan overlay
        self._container = QWidget(self)
        
        # QLabel untuk gambar PDF
        self._img_label = QLabel(self._container)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Overlay dipasang di atas container
        self._overlay.setParent(self._container)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._container, 0, Qt.AlignmentFlag.AlignCenter)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._render()

    def _render(self) -> None:
        try:
            page = self._doc[self._page_idx]
            # Render pada 2× zoom untuk baseline tajam, lalu scale ke zoom target
            # PyMuPDF Matrix uses (scale_x, scale_y)
            mat  = fitz.Matrix(self._zoom * 2.0, self._zoom * 2.0)
            pix  = page.get_pixmap(matrix=mat, alpha=False)
            img  = QImage(pix.samples, pix.width, pix.height,
                          pix.stride, QImage.Format.Format_RGB888)
            qpix = QPixmap.fromImage(img)
            
            self._img_label.setPixmap(qpix)
            self._img_label.setFixedSize(qpix.size())
            self._container.setFixedSize(qpix.size())
            self._overlay.setGeometry(0, 0, qpix.width(), qpix.height())
            self._overlay.raise_()
            self.updateGeometry()
        except Exception as e:
            self._img_label.setText(f"[Gagal render hal. {self._page_idx}: {e}]")

    def update_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self._render()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._overlay.raise_()


# ── MuPDF multi-page viewer ───────────────────────────────────────────────

class MuPdfViewer(QWidget):
    """
    Semua halaman PDF disusun vertikal.
    Memancarkan signal page_changed(int) saat halaman yang terlihat berubah.
    """

    page_changed = Signal(int)   # halaman saat ini (0-indexed)

    def __init__(self, pdf_path: Path, papis_key: str,
                 store: AnnotationStore, zoom: float = 1.0,
                 parent=None) -> None:
        super().__init__(parent)
        self.pdf_path  = pdf_path
        self.papis_key = papis_key
        self._store    = store
        self._zoom     = zoom
        self._overlays: list[AnnotationOverlay] = []
        self._page_widgets: list[MuPdfPageWidget] = []

        self._doc = fitz.open(str(pdf_path))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Deteksi scroll untuk update progress
        self._scroll.verticalScrollBar().valueChanged.connect(
            self._on_scroll)
        root.addWidget(self._scroll)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._scroll.setWidget(self._container)

        self._build_pages()

        # Debounce scroll events agar tidak terlalu sering emit
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

    def _build_pages(self) -> None:
        self._overlays.clear()
        self._page_widgets.clear()

        for i in range(self._doc.page_count):
            page = self._doc[i]
            r    = page.rect
            overlay = AnnotationOverlay(
                papis_key=self.papis_key,
                page_idx=i,
                store=self._store,
                page_width_pts=r.width,
                page_height_pts=r.height,
            )
            overlay.set_fitz_page(self._doc[i])
            self._overlays.append(overlay)

            pw = MuPdfPageWidget(self._doc, i, self._zoom, overlay)
            self._page_widgets.append(pw)
            self._layout.addWidget(pw)

        self._container.adjustSize()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        for pw in self._page_widgets:
            pw.update_zoom(zoom)
        self._container.adjustSize()

    def scroll_to_page(self, page_idx: int) -> None:
        if 0 <= page_idx < len(self._page_widgets):
            pw = self._page_widgets[page_idx]
            self._scroll.ensureWidgetVisible(pw, 0, 0)

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

    # ── Scroll-based page detection ───────────────────────────────────

    def _on_scroll(self, _value: int) -> None:
        self._scroll_timer.start()

    def _detect_visible_page(self) -> None:
        """Temukan halaman yang paling banyak terlihat di viewport."""
        viewport_rect = self._scroll.viewport().rect()
        best_page = 0
        best_area = 0

        for i, pw in enumerate(self._page_widgets):
            # Koordinat pw dalam koordinat container, lalu dalam viewport
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
        if self._doc:
            self._doc.close()
        super().closeEvent(event)


# ── PdfViewerTab ──────────────────────────────────────────────────────────

class PdfViewerTab(QWidget):
    """PDF viewer tab dengan anotasi, sidebar, dan progress baca."""

    insert_quote_requested  = Signal(str, str)   # (text, papis_key)
    insert_image_requested  = Signal(str, str)   # (image_path, papis_key)
    annotation_count_changed = Signal(int)

    def __init__(self, pdf_path: Path, papis_key: str,
                 vault_path: Path, config: NoterationConfig,
                 parent=None) -> None:
        super().__init__(parent)
        self.pdf_path  = pdf_path
        self.papis_key = papis_key or pdf_path.stem
        self.vault_path = vault_path
        self.config    = config

        self._current_page = 0
        self._total_pages  = 0
        self._zoom         = 1.0
        self._annot_mode   = "view"

        self._store    = AnnotationStore(vault_path)
        self._doc_ann  = self._store.load(self.papis_key)
        self._pdf_index = PdfIndex(vault_path)

        self._qtpdf_view:  "QPdfView | None"  = None
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
        splitter.addWidget(self._build_annot_panel())
        splitter.setSizes([740, 240])
        root.addWidget(splitter)

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:palette(window);"
            "border-bottom:1px solid palette(mid);}")
        frame.setFixedHeight(36)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(6, 2, 8, 2)
        lay.setSpacing(4)

        self._btn_prev = QPushButton("◀")
        self._btn_prev.setFixedWidth(28)
        self._btn_prev.setToolTip("Halaman sebelumnya  [PgUp]")
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
        self._btn_next.setToolTip("Halaman berikutnya  [PgDn]")
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
        self._btn_hl.setToolTip("Drag untuk highlight area")
        self._btn_hl.clicked.connect(
            lambda on: self._set_mode("highlight" if on else "view"))
        lay.addWidget(self._btn_hl)

        self._btn_cm = QPushButton("💬 Komentar")
        self._btn_cm.setCheckable(True)
        self._btn_cm.setToolTip("Klik untuk tambah komentar")
        self._btn_cm.clicked.connect(
            lambda on: self._set_mode("comment" if on else "view"))
        lay.addWidget(self._btn_cm)

        self._btn_bm = QPushButton("🔖")
        self._btn_bm.setFixedWidth(32)
        self._btn_bm.setToolTip("Bookmark halaman ini")
        self._btn_bm.clicked.connect(self._add_bookmark)
        lay.addWidget(self._btn_bm)

        self._btn_img = QPushButton("🖼 Image")
        self._btn_img.setCheckable(True)
        self._btn_img.setToolTip("Drag untuk capture gambar dari PDF")
        self._btn_img.clicked.connect(
            lambda on: self._set_mode("image" if on else "view"))
        lay.addWidget(self._btn_img)

        lay.addStretch()

        be = "QtPdf" if _HAS_QTPDF else ("PyMuPDF" if _HAS_FITZ else "—")
        lbl_be = QLabel(f"[{be}]")
        lbl_be.setStyleSheet("color:#bbb;font-size:10px;")
        lay.addWidget(lbl_be)

        return frame

    def _build_search_bar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:palette(window);"
            "border-bottom:1px solid palette(mid);}")
        frame.setVisible(False)
        frame.setFixedHeight(32)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(4)

        lay.addWidget(QLabel("Cari:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Ketik lalu Enter…")
        self._search_input.returnPressed.connect(self._do_search)
        lay.addWidget(self._search_input)

        btn = QPushButton("Cari")
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
        lbl = QLabel("Anotasi")
        lbl.setStyleSheet("font-weight:bold;font-size:13px;")
        hr.addWidget(lbl)
        hr.addStretch()
        self._lbl_count = QLabel("0")
        self._lbl_count.setStyleSheet(
            "font-size:10px;background:#E1F5EE;color:#0F6E56;"
            "padding:1px 6px;border-radius:8px;")
        hr.addWidget(self._lbl_count)
        lay.addLayout(hr)

        fr = QHBoxLayout()
        self._chk_hl = QCheckBox("Highlight")
        self._chk_hl.setChecked(True)
        self._chk_hl.stateChanged.connect(self._refresh_annot_list)
        self._chk_cm = QCheckBox("Komentar")
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
        self._annot_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._annot_list.customContextMenuRequested.connect(
            self._annot_context_menu)
        self._annot_list.itemSelectionChanged.connect(
            self._on_annot_selection_changed)
        lay.addWidget(self._annot_list, 1)

        grp = QGroupBox("Progress Baca")
        gl  = QVBoxLayout(grp)
        gl.setContentsMargins(4, 4, 4, 4)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setStyleSheet(
            "QProgressBar{font-size:10px;border-radius:4px;}"
            "QProgressBar::chunk{background:#4CAF50;border-radius:4px;}")
        gl.addWidget(self._progress_bar)
        self._lbl_progress = QLabel("Hal. 0 / 0")
        self._lbl_progress.setStyleSheet("font-size:10px;color:gray;")
        gl.addWidget(self._lbl_progress)
        lay.addWidget(grp)

        self._btn_insert = QPushButton("Sisipkan ke Editor")
        self._btn_insert.setEnabled(False)
        self._btn_insert.clicked.connect(self._on_insert_quote)
        lay.addWidget(self._btn_insert)

        self._btn_del = QPushButton("Hapus Anotasi")
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
        QShortcut(QKeySequence("PgUp"),   self, self._prev_page)

    # ── Loading ───────────────────────────────────────────────────────

    def _load_pdf(self) -> None:
        if not self.pdf_path.exists():
            self._show_error(f"File tidak ditemukan:\n{self.pdf_path}")
            return

        self._pdf_index.find_or_register(self.pdf_path, self.papis_key)
        if not self._doc_ann.pdf_hash:
            self._doc_ann.pdf_hash = hash_pdf(self.pdf_path)
            self._store.save(self.papis_key)

        if _HAS_FITZ:
            self._load_mupdf()
        elif _HAS_QTPDF:
            self._load_qtpdf()
        else:
            self._show_error(
                "Tidak ada PDF renderer.\n\n"
                "Install: pip install pymupdf"
            )

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
        # Sambungkan signal scroll → update halaman & progress
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
        """Dipanggil saat user scroll — update toolbar & progress tanpa scroll ulang."""
        if page_idx == self._current_page:
            return
        self._current_page = page_idx
        self._page_spin.blockSignals(True)
        self._page_spin.setValue(page_idx + 1)
        self._page_spin.blockSignals(False)
        self._save_progress(page_idx)

    def _set_page(self, idx: int) -> None:
        """Navigasi ke halaman tertentu dari tombol/spin."""
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

    def _save_progress(self, page_idx: int) -> None:
        progress = (page_idx + 1) / max(1, self._total_pages)
        self._doc_ann.last_page       = page_idx
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
            note=f"Bookmark hal. {self._current_page + 1}",
        )
        self._doc_ann.add(ann)
        self._store.save(self.papis_key)
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
                self._lbl_search_result.setText(f"{len(results)} hasil")
            else:
                self._lbl_search_result.setText("Tidak ditemukan")
        else:
            self._lbl_search_result.setText("Pencarian butuh PyMuPDF")

    # ── Annotation panel ──────────────────────────────────────────────

    def _reload_doc_ann(self) -> None:
        """Reload DocumentAnnotations dari store agar selalu segar."""
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

            # Warna badge sesuai warna anotasi
            color_hex = ann.color if ann.type in ("highlight", "image") else "#FFF9C4"
            color     = QColor(color_hex)
            color.setAlpha(180)

            if ann.type == "highlight":
                excerpt = (ann.text_content or "(drag area)") [:35]
                label   = f"🟡  Hal.{ann.page+1}  {excerpt}"
                if ann.note:
                    label += f"\n   ↳ {ann.note[:35]}"
            elif ann.type == "image":
                label = f"🖼  Hal.{ann.page+1}  (gambar)"
                if ann.note:
                    label += f"\n   ↳ {ann.note[:35]}"
            elif ann.type == "comment":
                label = f"💬  Hal.{ann.page+1}  {ann.note[:40]}"
            else:
                label = f"🔖  Hal.{ann.page+1}  {ann.note or 'Bookmark'}"

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
        self._lbl_progress.setText(
            f"Hal. {self._current_page + 1} / {self._total_pages}")

    # ── Selection handling ────────────────────────────────────────────

    def _on_annot_selection_changed(self) -> None:
        sel = self._annot_list.selectedItems()
        has = bool(sel)
        self._btn_del.setEnabled(has)
        if has:
            ann: Annotation = sel[0].data(Qt.ItemDataRole.UserRole)
            # Enable button for text highlights OR image captures
            can = bool(ann and (
                (ann.type == "highlight" and ann.text_content) or
                (ann.type == "image" and ann.image_path)
            ))
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
        menu   = QMenu(self)
        act_jump    = menu.addAction(f"Pergi ke Hal. {ann.page + 1}")
        act_ins     = None
        act_ins_img = None
        
        if ann.type == "highlight":
            if ann.text_content:
                act_ins = menu.addAction("Sisipkan Teks ke Editor")
            if ann.image_path:
                act_ins_img = menu.addAction("Sisipkan Gambar ke Editor")
        elif ann.type == "image" and ann.image_path:
            act_ins_img = menu.addAction("Sisipkan Gambar ke Editor")
            
        menu.addSeparator()
        act_del = menu.addAction("Hapus")

        chosen = menu.exec(self._annot_list.mapToGlobal(pos))
        if chosen == act_jump:
            self._set_page(ann.page)
        elif act_ins and chosen == act_ins:
            self.insert_quote_requested.emit(ann.text_content, self.papis_key)
        elif act_ins_img and chosen == act_ins_img:
            self.insert_image_requested.emit(ann.image_path, self.papis_key)
        elif chosen == act_del:
            self._on_delete_annot()

    def _on_insert_quote(self) -> None:
        sel = self._annot_list.selectedItems()
        if not sel:
            return
        ann: Annotation = sel[0].data(Qt.ItemDataRole.UserRole)
        if ann:
            if ann.type == "image" and ann.image_path:
                self.insert_image_requested.emit(ann.image_path, self.papis_key)
            elif ann.text_content:
                self.insert_quote_requested.emit(ann.text_content, self.papis_key)

    def _on_delete_annot(self) -> None:
        sel = self._annot_list.selectedItems()
        if not sel:
            return
        ann: Annotation = sel[0].data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Hapus Anotasi",
            f"Hapus anotasi ini?\n\n"
            f"{ann.type.capitalize()} • Hal. {ann.page + 1}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._doc_ann.remove(ann.id)
            self._store.save(self.papis_key)
            self._refresh_annot_list()
            if self._mupdf_viewer:
                self._mupdf_viewer.refresh_overlays()

    # ── Overlay callbacks ─────────────────────────────────────────────

    def _on_ov_created(self, ann: Annotation) -> None:
        """Dipanggil overlay → reload store & refresh sidebar."""
        self._refresh_annot_list()

    def _on_ov_deleted(self, ann_id: str) -> None:
        self._refresh_annot_list()

    def _on_ov_edited(self, ann: Annotation) -> None:
        self._refresh_annot_list()

    def _on_jump_to_note(self, note_path: str) -> None:
        from PySide6.QtWidgets import QApplication
        mw = QApplication.activeWindow()
        if hasattr(mw, "_follow_wiki_link"):
            mw._follow_wiki_link(Path(note_path).stem)  # type: ignore[union-attr]


# ── helpers ───────────────────────────────────────────────────────────────

def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setStyleSheet("color:palette(mid);")
    sep.setFixedWidth(1)
    return sep
