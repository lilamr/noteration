"""
noteration/ui/literature_tab.py

Tab browser literatur Papis dengan daftar + detail view.

Perbaikan:
  - Tombol "Tambah Dokumen" (manual + dari DOI/arXiv)
  - Edit metadata inline (update_field)
  - Tambah/hapus tag via UI (append_tag / remove_tag)
  - Lampirkan file tambahan (attach_file)
  - Pencarian mendukung field:value
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QSplitter, QFrame,
    QScrollArea, QGridLayout, QDialog, QFormLayout, QDialogButtonBox,
    QFileDialog, QInputDialog, QMessageBox, QMenu, QApplication,
    QComboBox,
)
from PySide6.QtCore import Qt, Signal, QTimer

from noteration.config import NoterationConfig
from noteration.literature.papis_bridge import PapisBridge, LiteratureEntry


# ── Dialog: Tambah Dokumen ────────────────────────────────────────────────

class AddDocumentDialog(QDialog):
    """
    Dialog untuk menambah dokumen baru ke library Papis.
    Mendukung:
      - Fetch otomatis via DOI atau arXiv URL (mengisi form secara otomatis)
      - Isi metadata manual + pilih PDF lokal
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tambah Dokumen ke Library")
        self.resize(500, 420)
        self._pdf_path: Path | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ── Fetch otomatis ──────────────────────────────────────────
        fetch_box = QFrame()
        fetch_box.setStyleSheet(
            "QFrame { border: 1px solid palette(mid); border-radius: 4px;"
            " padding: 6px; background: palette(window); }"
        )
        fetch_layout = QVBoxLayout(fetch_box)
        fetch_layout.setSpacing(4)
        fetch_layout.addWidget(QLabel("<b>Fetch otomatis dari DOI atau arXiv:</b>"))

        doi_row = QHBoxLayout()
        doi_row.addWidget(QLabel("DOI:"))
        self._fetch_doi_input = QLineEdit()
        self._fetch_doi_input.setPlaceholderText("10.1007/s11192-017-2554-0")
        self._fetch_doi_input.returnPressed.connect(self._fetch_doi)
        doi_row.addWidget(self._fetch_doi_input)
        fetch_doi_btn = QPushButton("Fetch")
        fetch_doi_btn.setFixedWidth(60)
        fetch_doi_btn.clicked.connect(self._fetch_doi)
        doi_row.addWidget(fetch_doi_btn)
        fetch_layout.addLayout(doi_row)

        arxiv_row = QHBoxLayout()
        arxiv_row.addWidget(QLabel("arXiv:"))
        self._fetch_arxiv_input = QLineEdit()
        self._fetch_arxiv_input.setPlaceholderText("https://arxiv.org/abs/2404.14339")
        self._fetch_arxiv_input.returnPressed.connect(self._fetch_arxiv)
        arxiv_row.addWidget(self._fetch_arxiv_input)
        fetch_arxiv_btn = QPushButton("Fetch")
        fetch_arxiv_btn.setFixedWidth(60)
        fetch_arxiv_btn.clicked.connect(self._fetch_arxiv)
        arxiv_row.addWidget(fetch_arxiv_btn)
        fetch_layout.addLayout(arxiv_row)

        isbn_row = QHBoxLayout()
        isbn_row.addWidget(QLabel("ISBN:"))
        self._fetch_isbn_input = QLineEdit()
        self._fetch_isbn_input.setPlaceholderText("9780131103627")
        self._fetch_isbn_input.returnPressed.connect(self._fetch_isbn)
        isbn_row.addWidget(self._fetch_isbn_input)
        fetch_isbn_btn = QPushButton("Fetch")
        fetch_isbn_btn.setFixedWidth(60)
        fetch_isbn_btn.clicked.connect(self._fetch_isbn)
        isbn_row.addWidget(fetch_isbn_btn)
        fetch_layout.addLayout(isbn_row)

        self._fetch_status = QLabel("")
        self._fetch_status.setStyleSheet("font-size: 11px; color: gray;")
        fetch_layout.addWidget(self._fetch_status)

        layout.addWidget(fetch_box)

        # ── Metadata (diisi manual atau otomatis oleh fetch) ────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._title_input  = QLineEdit()
        self._author_input = QLineEdit()
        self._author_input.setPlaceholderText("Newton, Isaac; Gauss, Carl")
        self._year_input   = QLineEdit()
        self._year_input.setMaximumWidth(70)
        self._journal_input = QLineEdit()
        self._publisher_input = QLineEdit()
        self._doi_input = QLineEdit()
        self._doi_input.setPlaceholderText("10.1007/...")
        self._isbn_input = QLineEdit()
        self._isbn_input.setPlaceholderText("978-0-13-...")
        self._volume_input = QLineEdit()
        self._volume_input.setMaximumWidth(70)
        self._issue_input = QLineEdit()
        self._issue_input.setMaximumWidth(70)
        self._page_input = QLineEdit()
        self._page_input.setPlaceholderText("1-10")
        self._page_input.setMaximumWidth(100)
        self._page_row_input = QLineEdit()
        self._abstract_input = QLineEdit()
        self._tags_input   = QLineEdit()
        self._tags_input.setPlaceholderText("fisika, mekanika  (pisah koma)")
        self._collections_input   = QLineEdit()
        self._collections_input.setPlaceholderText("GIS, Land Cover  (pisah koma)")

        # PDF picker
        pdf_row = QHBoxLayout()
        self._pdf_label = QLabel("(belum dipilih)")
        self._pdf_label.setStyleSheet("color: gray;")
        pick_btn = QPushButton("Pilih PDF…")
        pick_btn.clicked.connect(self._pick_pdf)
        pdf_row.addWidget(self._pdf_label, 1)
        pdf_row.addWidget(pick_btn)

        form.addRow("Judul:", self._title_input)
        form.addRow("Penulis:", self._author_input)
        form.addRow("Tahun:", self._year_input)
        form.addRow("Jurnal:", self._journal_input)
        form.addRow("Penerbit:", self._publisher_input)
        form.addRow("DOI:", self._doi_input)
        form.addRow("ISBN:", self._isbn_input)
        form.addRow("Volume:", self._volume_input)
        form.addRow("Issue:", self._issue_input)
        form.addRow("Halaman:", self._page_input)
        form.addRow("Abstract:", self._abstract_input)
        form.addRow("Tags:", self._tags_input)
        form.addRow("Collections:", self._collections_input)
        form.addRow("PDF:", pdf_row)
        layout.addLayout(form)

        # ── Buttons ────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Fetch handlers ────────────────────────────────────────────────

    def _fetch_doi(self) -> None:
        doi = self._fetch_doi_input.text().strip()
        if not doi:
            return
        self._fetch_status.setText("Mengambil data dari Crossref…")
        self._fetch_status.setStyleSheet("color: gray; font-size: 11px;")
        QApplication.processEvents()

        from noteration.literature.doi_fetcher import fetch_doi
        meta = fetch_doi(doi)
        self._apply_metadata(meta, source="Crossref")

    def _fetch_arxiv(self) -> None:
        url = self._fetch_arxiv_input.text().strip()
        if not url:
            return
        self._fetch_status.setText("Mengambil data dari arXiv…")
        self._fetch_status.setStyleSheet("color: gray; font-size: 11px;")
        QApplication.processEvents()

        from noteration.literature.doi_fetcher import fetch_arxiv
        meta = fetch_arxiv(url)
        self._apply_metadata(meta, source="arXiv")

    def _fetch_isbn(self) -> None:
        isbn = self._fetch_isbn_input.text().strip()
        if not isbn:
            return
        self._fetch_status.setText("Mengambil data dari OpenLibrary…")
        self._fetch_status.setStyleSheet("color: gray; font-size: 11px;")
        QApplication.processEvents()

        from noteration.literature.doi_fetcher import fetch_isbn
        meta = fetch_isbn(isbn)
        self._apply_metadata(meta, source="OpenLibrary")

    def _apply_metadata(self, meta: dict | None, source: str) -> None:
        """Isi semua field form dari dict metadata hasil fetch."""
        if not meta:
            self._fetch_status.setText(
                f"✗ Gagal mengambil data dari {source}. "
                "Periksa koneksi atau isi manual."
            )
            self._fetch_status.setStyleSheet("color: red; font-size: 11px;")
            return

        self._title_input.setText(meta.get("title", ""))
        self._author_input.setText(meta.get("author", ""))
        self._year_input.setText(str(meta.get("year", "")))
        self._journal_input.setText(meta.get("journal", ""))
        self._publisher_input.setText(meta.get("publisher", ""))
        self._volume_input.setText(meta.get("volume", ""))
        self._issue_input.setText(meta.get("issue", ""))
        self._page_input.setText(meta.get("page", ""))
        self._abstract_input.setText(meta.get("abstract", "")[:200] if meta.get("abstract") else "")

        if meta.get("doi"):
            self._doi_input.setText(meta.get("doi", ""))
        if meta.get("isbn"):
            self._isbn_input.setText(meta.get("isbn", ""))

        tags = meta.get("tags", [])
        self._tags_input.setText(", ".join(tags) if tags else "")

        self._fetch_status.setText(f"✓ Data berhasil diambil dari {source}.")
        self._fetch_status.setStyleSheet("color: green; font-size: 11px;")

    def _pick_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih PDF", "", "PDF Files (*.pdf)"
        )
        if path:
            self._pdf_path = Path(path)
            self._pdf_label.setText(self._pdf_path.name)
            self._pdf_label.setStyleSheet("")

    # ── Result accessors ──────────────────────────────────────────────

    @property
    def from_doi(self) -> str:
        return self._fetch_doi_input.text().strip()

    @property
    def from_arxiv(self) -> str:
        return self._fetch_arxiv_input.text().strip()

    @property
    def from_isbn(self) -> str:
        return self._fetch_isbn_input.text().strip()

    @property
    def title(self) -> str:
        return self._title_input.text().strip()

    @property
    def author(self) -> str:
        return self._author_input.text().strip()

    @property
    def year(self) -> str:
        return self._year_input.text().strip()

    @property
    def journal(self) -> str:
        return self._journal_input.text().strip()

    @property
    def publisher(self) -> str:
        return self._publisher_input.text().strip()

    @property
    def doi(self) -> str:
        return self._doi_input.text().strip()

    @property
    def isbn(self) -> str:
        return self._isbn_input.text().strip()

    @property
    def volume(self) -> str:
        return self._volume_input.text().strip()

    @property
    def issue(self) -> str:
        return self._issue_input.text().strip()

    @property
    def page(self) -> str:
        return self._page_input.text().strip()

    @property
    def abstract(self) -> str:
        return self._abstract_input.text().strip()

    @property
    def tags(self) -> list[str]:
        return [t.strip() for t in self._tags_input.text().split(",")
                if t.strip()]

    @property
    def collections(self) -> list[str]:
        return [c.strip() for c in self._collections_input.text().split(",")
                if c.strip()]

    @property
    def extra_fields(self) -> dict:
        return {}

    @property
    def pdf_path(self) -> Path | None:
        return self._pdf_path


# ── LiteratureTab ─────────────────────────────────────────────────────────

class LiteratureTab(QWidget):
    """
    Tab browser literatur Papis.
    Kiri : daftar entri dengan filter (mendukung field:value).
    Kanan: detail view + aksi (buka PDF, copy key, buat catatan,
           edit metadata, tambah/hapus tag, lampirkan file).
    """

    pdf_open_requested    = Signal(Path, str)   # (pdf_path, papis_key)
    note_create_requested = Signal(str, str)   # (papis_key, title)
    library_changed        = Signal()            # dipancarkan setelah library dimodifikasi

    def __init__(self, vault_path: Path, config: NoterationConfig,
                 parent=None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        self.config     = config
        self._bridge    = PapisBridge(self.config.papis_library)
        self._entries:  list[LiteratureEntry] = []
        self._current:  LiteratureEntry | None = None

        self._setup_ui()
        QTimer.singleShot(100, self._load_entries)

    def refresh(self) -> None:
        """Public method to refresh the list - called when tab becomes visible."""
        self._load_entries(force=True)

    def select_entry(self, papis_key: str) -> None:
        """Pilih entry di list berdasarkan papis_key."""
        entry = None
        if self._bridge:
            entry = self._bridge.get(papis_key)
        if entry is None:
            for i in range(self._entry_list.count()):
                item = self._entry_list.item(i)
                e = item.data(Qt.ItemDataRole.UserRole)
                if e and e.key == papis_key:
                    entry = e
                    break
        if entry is None:
            return
        self._entry_list.blockSignals(True)
        for i in range(self._entry_list.count()):
            item = self._entry_list.item(i)
            e = item.data(Qt.ItemDataRole.UserRole)
            if e and e.key == papis_key:
                self._entry_list.setCurrentItem(item)
                self._entry_list.scrollToItem(item)
                break
        self._entry_list.blockSignals(False)
        self._current = entry
        self._show_detail(entry)

    # ── UI construction ───────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search bar
        search_bar = QFrame()
        search_bar.setStyleSheet(
            "background: palette(window); border-bottom: 1px solid palette(mid);"
        )
        search_bar.setFixedHeight(36)
        s_layout = QHBoxLayout(search_bar)
        s_layout.setContentsMargins(6, 3, 6, 3)
        s_layout.setSpacing(4)

        # Collection filter dropdown
        self._collection_combo = QComboBox()
        self._collection_combo.setFixedWidth(80)
        self._collection_combo.addItem("Semua")
        self._collection_combo.currentTextChanged.connect(self._on_collection_changed)
        s_layout.addWidget(self._collection_combo)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "Cari… judul, penulis, tahun, key — atau field:value (title:principia, tags:fisika)"
        )
        self._search_input.textChanged.connect(self._on_search)
        s_layout.addWidget(self._search_input)

        add_btn = QPushButton("+ Tambah")
        add_btn.setToolTip("Tambah dokumen baru ke library Papis")
        add_btn.clicked.connect(self._on_add_document)
        s_layout.addWidget(add_btn)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(30)
        refresh_btn.setToolTip("Muat ulang library")
        refresh_btn.clicked.connect(lambda: self._load_entries(force=True))
        s_layout.addWidget(refresh_btn)

        layout.addWidget(search_bar)

        # Splitter kiri/kanan
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._entry_list = QListWidget()
        self._entry_list.setStyleSheet("font-size: 12px;")
        self._entry_list.currentItemChanged.connect(self._on_entry_selected)
        self._entry_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._entry_list.customContextMenuRequested.connect(
            self._show_list_context_menu)
        splitter.addWidget(self._entry_list)

        self._detail_widget = self._build_detail_widget()
        splitter.addWidget(self._detail_widget)
        splitter.setSizes([280, 500])

        layout.addWidget(splitter)

    def _build_detail_widget(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self._detail_title = QLabel("Pilih entri di sebelah kiri.")
        self._detail_title.setWordWrap(True)
        self._detail_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._detail_title)

        self._detail_grid = QGridLayout()
        self._detail_grid.setColumnMinimumWidth(0, 80)
        layout.addLayout(self._detail_grid)

        # Tombol aksi utama
        btn_row = QHBoxLayout()
        self._btn_open_pdf = QPushButton("Buka PDF")
        self._btn_open_pdf.setEnabled(False)
        self._btn_open_pdf.clicked.connect(self._on_open_pdf)
        btn_row.addWidget(self._btn_open_pdf)

        self._btn_copy_key = QPushButton("Salin @key")
        self._btn_copy_key.setEnabled(False)
        self._btn_copy_key.clicked.connect(self._on_copy_key)
        btn_row.addWidget(self._btn_copy_key)

        self._btn_create_note = QPushButton("Buat Catatan")
        self._btn_create_note.setEnabled(False)
        self._btn_create_note.clicked.connect(self._on_create_note)
        btn_row.addWidget(self._btn_create_note)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Tombol edit metadata
        edit_row = QHBoxLayout()
        self._btn_edit_title = QPushButton("Edit Judul")
        self._btn_edit_title.setEnabled(False)
        self._btn_edit_title.clicked.connect(
            lambda: self._on_edit_field("title", "Judul"))
        edit_row.addWidget(self._btn_edit_title)

        self._btn_edit_author = QPushButton("Edit Penulis")
        self._btn_edit_author.setEnabled(False)
        self._btn_edit_author.clicked.connect(
            lambda: self._on_edit_field("author", "Penulis"))
        edit_row.addWidget(self._btn_edit_author)

        self._btn_add_tag = QPushButton("+ Tag")
        self._btn_add_tag.setEnabled(False)
        self._btn_add_tag.clicked.connect(self._on_add_tag)
        edit_row.addWidget(self._btn_add_tag)

        self._btn_add_collection = QPushButton("+ Collection")
        self._btn_add_collection.setEnabled(False)
        self._btn_add_collection.clicked.connect(self._on_add_collection)
        edit_row.addWidget(self._btn_add_collection)

        self._btn_attach = QPushButton("Lampirkan File")
        self._btn_attach.setEnabled(False)
        self._btn_attach.clicked.connect(self._on_attach_file)
        edit_row.addWidget(self._btn_attach)

        self._btn_delete = QPushButton("Hapus Dokumen")
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet("color: #c00;")
        self._btn_delete.clicked.connect(self._on_delete_document)
        edit_row.addWidget(self._btn_delete)

        edit_row.addStretch()
        layout.addLayout(edit_row)

        # Tag list (inline, bisa dihapus)
        self._tag_label = QLabel("")
        self._tag_label.setWordWrap(True)
        self._tag_label.setStyleSheet("margin-top: 4px;")
        layout.addWidget(self._tag_label)

        # Collection list (inline, bisa dihapus)
        self._collection_label = QLabel("")
        self._collection_label.setWordWrap(True)
        self._collection_label.setStyleSheet("margin-top: 4px;")
        layout.addWidget(self._collection_label)

        # Abstract
        self._detail_abstract = QLabel("")
        self._detail_abstract.setWordWrap(True)
        self._detail_abstract.setStyleSheet(
            "color: gray; font-size: 11px; margin-top: 8px;")
        layout.addWidget(self._detail_abstract)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Data loading ──────────────────────────────────────────────────

    def _load_entries(self, force: bool = False) -> None:
        self._bridge = PapisBridge(self.config.papis_library)
        self._entries = self._bridge.all_entries(force_reload=force)
        
        # Collect all unique collections
        all_collections = set()
        for e in self._entries:
            for col in e.collections:
                all_collections.add(col)
        
        # Update dropdown
        current = self._collection_combo.currentText()
        self._collection_combo.blockSignals(True)
        self._collection_combo.clear()
        self._collection_combo.addItem("Semua")
        for col in sorted(all_collections):
            self._collection_combo.addItem(col)
        # Restore selection if valid
        if current in all_collections:
            self._collection_combo.setCurrentText(current)
        elif current != "Semua":
            self._collection_combo.setCurrentText("Semua")
        self._collection_combo.blockSignals(False)
        
        self._filter_and_populate()

    def _filter_and_populate(self) -> None:
        collection_filter = self._collection_combo.currentText()
        search_text = self._search_input.text().lower()
        
        filtered = []
        for e in self._entries:
            # Collection filter
            if collection_filter != "Semua":
                if collection_filter not in e.collections:
                    continue
            
            # Search filter
            if search_text:
                q = search_text.lower()
                if not (q in e.title.lower() or q in e.author.lower() 
                       or q in e.key.lower() or q in e.year.lower()):
                    continue
            
            filtered.append(e)
        
        self._populate_list(filtered)

    def _on_collection_changed(self, text: str) -> None:
        self._filter_and_populate()

    def _populate_list(self, entries: list[LiteratureEntry]) -> None:
        self._entry_list.clear()
        for e in entries:
            # Show collection badge if exists
            coll_str = f" [{', '.join(e.collections)}]" if e.collections else ""
            label = f"@{e.key}{coll_str}\n{e.title[:55]}\n{e.author[:35]} · {e.year}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, e)
            self._entry_list.addItem(item)

    # ── Event handlers ────────────────────────────────────────────────

    def _on_search(self, text: str) -> None:
        self._filter_and_populate()

    def _on_entry_selected(self, current: QListWidgetItem, _prev) -> None:
        if not current:
            return
        self._current = current.data(Qt.ItemDataRole.UserRole)
        self._show_detail(self._current)

    def _show_detail(self, e: LiteratureEntry) -> None:
        self._detail_title.setText(e.title or e.key)

        # Clear grid
        for i in reversed(range(self._detail_grid.count())):
            item = self._detail_grid.itemAt(i)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        fields = [
            ("Penulis", e.author),
            ("Tahun",   e.year),
            ("Jurnal",  e.journal),
            ("Penerbit", e.publisher),
            ("DOI",    e.doi),
            ("ISBN",   e.isbn),
            ("Volume", e.volume),
            ("Issue",  e.issue),
            ("Halaman", e.page),
            ("PDF",   str(e.pdf_path) if e.pdf_path else "—"),
        ]
        for row, (label, value) in enumerate(fields):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: gray; font-size: 11px;")
            val = QLabel(value or "—")
            val.setWordWrap(True)
            val.setStyleSheet("font-size: 12px;")
            self._detail_grid.addWidget(
                lbl, row, 0, Qt.AlignmentFlag.AlignTop)
            self._detail_grid.addWidget(val, row, 1)

        # Tags (klik untuk hapus)
        self._refresh_tag_display(e)

        self._detail_abstract.setText(
            e.abstract[:400] + ("…" if len(e.abstract) > 400 else "")
            if e.abstract else ""
        )

        has_pdf = bool(e.pdf_path and e.pdf_path.exists())
        self._btn_open_pdf.setEnabled(has_pdf)
        for btn in (self._btn_copy_key, self._btn_create_note,
                    self._btn_edit_title, self._btn_edit_author,
                    self._btn_add_tag, self._btn_add_collection,
                    self._btn_attach, self._btn_delete):
            btn.setEnabled(True)

        self._refresh_tag_display(e)
        self._refresh_collection_display(e)

    def _refresh_tag_display(self, e: LiteratureEntry) -> None:
        """Tampilkan tag sebagai badge — klik kanan untuk hapus."""
        if e.tags:
            tag_str = "  ".join(f"[{t}]" for t in e.tags)
            self._tag_label.setText(f"Tags: {tag_str}  (klik kanan tag untuk hapus)")
        else:
            self._tag_label.setText("Tags: —")

    def _refresh_collection_display(self, e: LiteratureEntry) -> None:
        """Tampilkan collection sebagai badge — klik kanan untuk hapus."""
        if e.collections:
            coll_str = "  ".join(f"[{c}]" for c in e.collections)
            self._collection_label.setText(f"Collections: {coll_str}  (klik kanan collection untuk hapus)")
        else:
            self._collection_label.setText("Collections: —")

    # ── Aksi utama ────────────────────────────────────────────────────

    def _on_open_pdf(self) -> None:
        if self._current and self._current.pdf_path:
            self.pdf_open_requested.emit(
                self._current.pdf_path, self._current.key)

    def _on_copy_key(self) -> None:
        if self._current:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(f"@{self._current.key}")

    def _on_create_note(self) -> None:
        if self._current:
            self.note_create_requested.emit(
                self._current.key, self._current.title)

    # ── Tambah dokumen ────────────────────────────────────────────────

    def _on_add_document(self) -> None:
        dlg = AddDocumentDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        entry = self._bridge.add_document(
            pdf_path      = dlg.pdf_path,
            title       = dlg.title,
            author      = dlg.author,
            year       = dlg.year,
            journal    = dlg.journal,
            publisher = dlg.publisher,
            doi       = dlg.doi,
            isbn      = dlg.isbn,
            volume    = dlg.volume,
            issue     = dlg.issue,
            page      = dlg.page,
            abstract  = dlg.abstract,
            tags      = dlg.tags or None,
            collections = dlg.collections or None,
            from_doi    = dlg.from_doi,
            from_arxiv  = dlg.from_arxiv,
            from_isbn   = dlg.from_isbn,
        )
        if entry:
            self._load_entries(force=True)
            self.library_changed.emit()
            QMessageBox.information(
                self, "Berhasil",
                f"Dokumen ditambahkan: @{entry.key}"
            )
        else:
            QMessageBox.warning(
                self, "Gagal",
                "Dokumen tidak berhasil ditambahkan.\n"
                "Pastikan metadata diisi atau DOI/arXiv valid."
            )

    # ── Edit metadata ─────────────────────────────────────────────────

    def _on_edit_field(self, field_name: str, label: str) -> None:
        if not self._current:
            return
        current_val = getattr(self._current, field_name, "")
        new_val, ok = QInputDialog.getText(
            self, f"Edit {label}",
            f"{label}:", text=str(current_val)
        )
        if not ok or new_val.strip() == current_val:
            return
        if self._bridge.update_field(self._current.key, field_name,
                                     new_val.strip()):
            self._show_detail(self._current)
            self._refresh_list_item(self._current)
            self.library_changed.emit()
        else:
            QMessageBox.warning(self, "Gagal",
                                "Tidak bisa menyimpan perubahan ke info.yaml.")

    # ── Tag management ────────────────────────────────────────────────

    def _on_add_tag(self) -> None:
        if not self._current:
            return
        tag, ok = QInputDialog.getText(
            self, "Tambah Tag", "Nama tag:"
        )
        if not ok or not tag.strip():
            return
        if self._bridge.append_tag(self._current.key, tag.strip()):
            self._refresh_tag_display(self._current)
            self.library_changed.emit()
        else:
            QMessageBox.warning(self, "Gagal",
                                "Tidak bisa menambah tag.")

    def _on_remove_tag(self, tag: str) -> None:
        if not self._current:
            return
        reply = QMessageBox.question(
            self, "Hapus Tag",
            f"Hapus tag \"{tag}\" dari @{self._current.key}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._bridge.remove_tag(self._current.key, tag):
                self._refresh_tag_display(self._current)
                self.library_changed.emit()
            else:
                QMessageBox.warning(self, "Gagal", "Tidak bisa menghapus tag.")

    # ── Collection management ───────────────────────────────────────────

    def _on_add_collection(self) -> None:
        if not self._current:
            return
        coll, ok = QInputDialog.getText(
            self, "Tambah Collection", "Nama collection:"
        )
        if not ok or not coll.strip():
            return
        if self._append_collection(self._current.key, coll.strip()):
            self._refresh_collection_display(self._current)
            self._load_entries(force=True)  # Refresh dropdown
            self.library_changed.emit()
        else:
            QMessageBox.warning(self, "Gagal",
                                "Tidak bisa menambah collection.")

    def _append_collection(self, key: str, collection: str) -> bool:
        """Tambah collection ke entry."""
        entry = self._bridge.get(key)
        if not entry or not entry.info_path:
            return False
        if collection in entry.collections:
            return True  # Already exists
        entry.collections.append(collection)
        entry._raw["collections"] = entry.collections
        try:
            import yaml
            with open(entry.info_path, "w") as f:
                yaml.dump(entry._raw, f)
            return True
        except Exception:
            return False

    def _on_remove_collection(self, collection: str) -> None:
        if not self._current:
            return
        reply = QMessageBox.question(
            self, "Hapus Collection",
            f"Hapus collection \"{collection}\" dari @{self._current.key}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._remove_collection(self._current.key, collection):
                self._refresh_collection_display(self._current)
                self._load_entries(force=True)
                self.library_changed.emit()
            else:
                QMessageBox.warning(self, "Gagal", "Tidak bisa menghapus collection.")

    def _remove_collection(self, key: str, collection: str) -> bool:
        """Hapus collection dari entry."""
        entry = self._bridge.get(key)
        if not entry or not entry.info_path:
            return False
        if collection not in entry.collections:
            return True  # Already removed
        entry.collections.remove(collection)
        entry._raw["collections"] = entry.collections
        try:
            import yaml
            with open(entry.info_path, "w") as f:
                yaml.dump(entry._raw, f)
            return True
        except Exception:
            return False

    # ── Lampirkan file ────────────────────────────────────────────────

    def _on_attach_file(self) -> None:
        if not self._current:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih File", "", "All Files (*)"
        )
        if path and self._bridge.attach_file(self._current.key, Path(path)):
            self._refresh_list_item(self._current)
            self._show_detail(self._current)
            QMessageBox.information(self, "Berhasil", "File berhasil dilampirkan.")
        else:
            QMessageBox.warning(self, "Gagal", "File tidak berhasil dilampirkan.")

    # ── Hapus dokumen ────────────────────────────────────────────────

    def _on_delete_document(self) -> None:
        if not self._current:
            return
        reply = QMessageBox.question(
            self, "Hapus Dokumen",
            f"Hapus dokumen @{self._current.key}?\n\n"
            f"\"{self._current.title}\"\n\n"
            "Folder dan semua file akan dihapus permanent.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        key = self._current.key
        if self._bridge.delete_document(key):
            self._current = None
            self._load_entries(force=True)
            self.library_changed.emit()
            QMessageBox.information(
                self, "Berhasil",
                f"Dokumen @{key} telah dihapus."
            )
        else:
            QMessageBox.warning(
                self, "Gagal",
                "Dokumen tidak berhasil dihapus."
            )
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih File untuk Dilampirkan", "",
            "Semua File (*.*)"
        )
        if not path:
            return
        if self._current and self._bridge.attach_file(self._current.key, Path(path)):
            self._show_detail(self._current)  # type: ignore[arg-type]
            self.library_changed.emit()
            QMessageBox.information(
                self, "Berhasil",
                f"File dilampirkan ke @{self._current.key}."
            )
        else:
            QMessageBox.warning(self, "Gagal",
                                "Tidak bisa melampirkan file.")

    # ── Context menu list ──────────────────────────────────────────────

    def _show_list_context_menu(self, pos) -> None:
        item = self._entry_list.itemAt(pos)
        if not item:
            return
        entry: LiteratureEntry | None = item.data(Qt.ItemDataRole.UserRole)
        if not entry:
            return

        menu = QMenu(self)

        # Remove tag submenu
        if entry and entry.tags:
            tag_menu = menu.addMenu("Hapus Tag")
            for tag in entry.tags:
                act = tag_menu.addAction(tag)
                act.triggered.connect(
                    lambda checked=False, t=tag: self._on_remove_tag(t))

        # Remove collection submenu
        if entry and entry.collections:
            coll_menu = menu.addMenu("Hapus Collection")
            for coll in entry.collections:
                act = coll_menu.addAction(coll)
                act.triggered.connect(
                    lambda checked=False, c=coll: self._on_remove_collection(c))
        menu.addSeparator()

        edit_title = menu.addAction("Edit Judul…")
        edit_title.triggered.connect(
            lambda: self._on_edit_field("title", "Judul"))

        edit_author = menu.addAction("Edit Penulis…")
        edit_author.triggered.connect(
            lambda: self._on_edit_field("author", "Penulis"))

        menu.exec(self._entry_list.mapToGlobal(pos))

    # ── Helpers ───────────────────────────────────────────────────────

    def _refresh_list_item(self, entry: LiteratureEntry) -> None:
        """Perbarui teks item di list tanpa reload penuh."""
        for i in range(self._entry_list.count()):
            item = self._entry_list.item(i)
            e: LiteratureEntry = item.data(Qt.ItemDataRole.UserRole)
            if e.key == entry.key:
                label = (f"@{entry.key}\n{entry.title[:55]}\n"
                         f"{entry.author[:35]} · {entry.year}")
                item.setText(label)
                break
