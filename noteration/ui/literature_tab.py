"""noteration/ui/literature_tab.py

Papis literature browser tab with list + detail view.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noteration.vault_manager import VaultManager

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QLabel,
    QPushButton,
    QSplitter,
    QFrame,
    QScrollArea,
    QGridLayout,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QMenu,
    QApplication,
    QComboBox,
)
from PySide6.QtCore import (
    Qt,
    Signal,
    QTimer,
    QAbstractListModel,
    QModelIndex,
    QSortFilterProxyModel,
)

from noteration.literature.papis_bridge import LiteratureEntry
from noteration.logger import get_logger

logger = get_logger(__name__)


# ── Data Model ──────────────────────────────────────────────────────────


class LiteratureFilterProxy(QSortFilterProxyModel):
    """Proxy model for advanced filtering and sorting of literature."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._collection_filter = "All"

    def set_collection_filter(self, collection: str):
        self._collection_filter = collection
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        entry = model.get_entry(source_row)
        if not entry:
            return False

        # 1. Collection Filter
        if self._collection_filter != "All":
            if self._collection_filter not in entry.collections:
                return False

        # 2. Text Search Filter (multi-token AND)
        query = self.filterRegularExpression().pattern().lower()
        if not query:
            return True

        tokens = query.split()
        entry_text = (
            f"{entry.key} {entry.title} {entry.author} {entry.year} {' '.join(entry.tags)}".lower()
        )

        return all(token in entry_text for token in tokens)


class LiteratureModel(QAbstractListModel):
    """Efficient model for literature entries to handle large libraries."""

    def __init__(self, entries: list[LiteratureEntry] | None = None, parent=None):
        super().__init__(parent)
        self._entries = entries or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._entries)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None

        entry = self._entries[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            coll_str = f" [{', '.join(entry.collections)}]" if entry.collections else ""
            return f"@{entry.key}{coll_str}\n{entry.title[:55]}\n{entry.author[:35]} · {entry.year}"

        elif role == Qt.ItemDataRole.UserRole:
            return entry

        return None

    def set_entries(self, entries: list[LiteratureEntry]):
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def get_entry(self, row: int) -> LiteratureEntry | None:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None


# ── Dialog: Add Document ────────────────────────────────────────────────


class AddDocumentDialog(QDialog):
    """Dialog for adding a new document to the Papis library.
    Supports:
      - Auto-fetch via DOI or arXiv URL (fills form automatically)
      - Manual metadata entry + local PDF selection
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Document to Library")
        self.resize(500, 420)
        self._pdf_path: Path | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ── Auto-fetch ──────────────────────────────────────────
        fetch_box = QFrame()
        fetch_box.setStyleSheet(
            "QFrame { border: 1px solid palette(mid); border-radius: 4px;"
            " padding: 6px; background: palette(window); }"
        )
        fetch_layout = QVBoxLayout(fetch_box)
        fetch_layout.setSpacing(4)
        fetch_layout.addWidget(QLabel("<b>Auto-fetch from DOI or arXiv:</b>"))

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

        # ── Metadata (filled manually or automatically by fetch) ────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._title_input = QLineEdit()
        self._author_input = QLineEdit()
        self._author_input.setPlaceholderText("Newton, Isaac; Gauss, Carl")
        self._year_input = QLineEdit()
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
        self._tags_input = QLineEdit()
        self._tags_input.setPlaceholderText("physics, mechanics  (comma separated)")
        self._collections_input = QLineEdit()
        self._collections_input.setPlaceholderText("GIS, Land Cover  (comma separated)")

        # PDF picker
        pdf_row = QHBoxLayout()
        self._pdf_label = QLabel("(none selected)")
        self._pdf_label.setStyleSheet("color: gray;")
        pick_btn = QPushButton("Select PDF…")
        pick_btn.clicked.connect(self._pick_pdf)
        pdf_row.addWidget(self._pdf_label, 1)
        pdf_row.addWidget(pick_btn)

        form.addRow("Title:", self._title_input)
        form.addRow("Author:", self._author_input)
        form.addRow("Year:", self._year_input)
        form.addRow("Journal:", self._journal_input)
        form.addRow("Publisher:", self._publisher_input)
        form.addRow("DOI:", self._doi_input)
        form.addRow("ISBN:", self._isbn_input)
        form.addRow("Volume:", self._volume_input)
        form.addRow("Issue:", self._issue_input)
        form.addRow("Page:", self._page_input)
        form.addRow("Abstract:", self._abstract_input)
        form.addRow("Tags:", self._tags_input)
        form.addRow("Collections:", self._collections_input)
        form.addRow("PDF:", pdf_row)
        layout.addLayout(form)

        # ── Buttons ────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Fetch handlers ────────────────────────────────────────────────

    def _fetch_doi(self) -> None:
        doi = self._fetch_doi_input.text().strip()
        if not doi:
            return
        self._fetch_status.setText("Fetching data from Crossref…")
        self._fetch_status.setStyleSheet("color: gray; font-size: 11px;")
        QApplication.processEvents()

        from noteration.literature.doi_fetcher import fetch_doi

        meta = fetch_doi(doi)
        self._apply_metadata(meta, source="Crossref")

    def _fetch_arxiv(self) -> None:
        url = self._fetch_arxiv_input.text().strip()
        if not url:
            return
        self._fetch_status.setText("Fetching data from arXiv…")
        self._fetch_status.setStyleSheet("color: gray; font-size: 11px;")
        QApplication.processEvents()

        from noteration.literature.doi_fetcher import fetch_arxiv

        meta = fetch_arxiv(url)
        self._apply_metadata(meta, source="arXiv")

    def _fetch_isbn(self) -> None:
        isbn = self._fetch_isbn_input.text().strip()
        if not isbn:
            return
        self._fetch_status.setText("Fetching data from OpenLibrary…")
        self._fetch_status.setStyleSheet("color: gray; font-size: 11px;")
        QApplication.processEvents()

        from noteration.literature.doi_fetcher import fetch_isbn

        meta = fetch_isbn(isbn)
        self._apply_metadata(meta, source="OpenLibrary")

    def _apply_metadata(self, meta: dict | None, source: str) -> None:
        """Fill all form fields from metadata dict obtained from fetch."""
        if not meta:
            self._fetch_status.setText(
                f"✗ Failed to fetch data from {source}. Check connection or fill manually."
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

        self._fetch_status.setText(f"✓ Data successfully fetched from {source}.")
        self._fetch_status.setStyleSheet("color: green; font-size: 11px;")

    def _pick_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Files (*.pdf)")
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
        return [t.strip() for t in self._tags_input.text().split(",") if t.strip()]

    @property
    def collections(self) -> list[str]:
        return [c.strip() for c in self._collections_input.text().split(",") if c.strip()]

    @property
    def extra_fields(self) -> dict:
        return {}

    @property
    def pdf_path(self) -> Path | None:
        return self._pdf_path


# ── LiteratureTab ─────────────────────────────────────────────────────────


class LiteratureTab(QWidget):
    """Papis literature browser tab.
    Left: list of entries with filter (supports field:value).
    Right: detail view + actions (open PDF, copy key, create note,
           edit metadata, add/remove tag, attach file).
    """

    pdf_open_requested = Signal(Path, str)  # (pdf_path, papis_key)
    note_create_requested = Signal(str, str)  # (papis_key, title)
    library_changed = Signal()  # emitted after library is modified

    def __init__(self, vault: "VaultManager", parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.vault_path = vault.vault_path
        self.config = vault.config
        self._bridge = vault.papis
        self._current: LiteratureEntry | None = None
        self._pending_selection: str | None = None
        self._library = vault.library
        self.on_changed = lambda: self.vault.request_git_status()

        # Model/View Setup
        self._model = LiteratureModel()
        self._proxy = LiteratureFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._setup_ui()

        # Connect shared controller signals once
        self._library.entries_loaded.connect(self._on_entries_loaded)
        self._library.error_occurred.connect(self._on_load_error)

        QTimer.singleShot(0, self._load_entries)

    def shutdown(self) -> None:
        """Stop background threads handled by controllers."""
        pass

    def refresh(self) -> None:
        """Public method to refresh the list - called when tab becomes visible."""
        self._load_entries(force=True)

    def select_entry(self, papis_key: str) -> None:
        """Select entry in list based on papis_key."""
        found_row = -1
        for row in range(self._model.rowCount()):
            entry = self._model.get_entry(row)
            if entry and entry.key == papis_key:
                found_row = row
                break

        if found_row < 0:
            return

        source_index = self._model.index(found_row)
        proxy_index = self._proxy.mapFromSource(source_index)

        if proxy_index.isValid():
            self._entry_list.setCurrentIndex(proxy_index)
            self._entry_list.scrollTo(proxy_index)
            self._on_entry_selected(proxy_index)

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

        self._collection_combo = QComboBox()
        self._collection_combo.setFixedWidth(100)
        self._collection_combo.addItem("All")
        self._collection_combo.currentTextChanged.connect(self._on_collection_changed)
        s_layout.addWidget(self._collection_combo)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search… (instant filter)")
        self._search_input.textChanged.connect(self._on_search)
        s_layout.addWidget(self._search_input)

        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._on_add_document)
        s_layout.addWidget(add_btn)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(30)
        refresh_btn.clicked.connect(lambda: self._load_entries(force=True))
        s_layout.addWidget(refresh_btn)

        layout.addWidget(search_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._entry_list = QListView()
        self._entry_list.setModel(self._proxy)
        self._entry_list.setStyleSheet("font-size: 11px;")
        self._entry_list.selectionModel().currentChanged.connect(
            lambda curr, prev: self._on_entry_selected(curr)
        )

        self._entry_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._entry_list.customContextMenuRequested.connect(self._show_list_context_menu)

        splitter.addWidget(self._entry_list)

        self._detail_widget = self._build_detail_widget()
        splitter.addWidget(self._detail_widget)
        splitter.setSizes([320, 500])

        layout.addWidget(splitter)

    def _build_detail_widget(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self._detail_title = QLabel("Select an entry on the left.")
        self._detail_title.setWordWrap(True)
        self._detail_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._detail_title)

        self._detail_grid = QGridLayout()
        self._detail_grid.setColumnMinimumWidth(0, 80)
        layout.addLayout(self._detail_grid)

        self._field_labels = {}
        fields = [
            "Author",
            "Year",
            "Journal",
            "Publisher",
            "DOI",
            "ISBN",
            "Volume",
            "Issue",
            "Page",
            "PDF",
        ]
        for row, field_name in enumerate(fields):
            lbl = QLabel(field_name)
            lbl.setStyleSheet("color: gray; font-size: 11px;")
            val = QLabel("—")
            val.setWordWrap(True)
            val.setStyleSheet("font-size: 12px;")
            self._detail_grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignTop)
            self._detail_grid.addWidget(val, row, 1)
            self._field_labels[field_name] = val

        btn_row = QHBoxLayout()
        self._btn_open_pdf = QPushButton("Open PDF")
        self._btn_open_pdf.setEnabled(False)
        self._btn_open_pdf.clicked.connect(self._on_open_pdf)
        btn_row.addWidget(self._btn_open_pdf)

        self._btn_copy_key = QPushButton("Copy @key")
        self._btn_copy_key.setEnabled(False)
        self._btn_copy_key.clicked.connect(self._on_copy_key)
        btn_row.addWidget(self._btn_copy_key)

        self._btn_create_note = QPushButton("Create Note")
        self._btn_create_note.setEnabled(False)
        self._btn_create_note.clicked.connect(self._on_create_note)
        btn_row.addWidget(self._btn_create_note)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        edit_row = QHBoxLayout()
        self._btn_edit_title = QPushButton("Edit Title")
        self._btn_edit_title.setEnabled(False)
        self._btn_edit_title.clicked.connect(lambda: self._on_edit_field("title", "Title"))
        edit_row.addWidget(self._btn_edit_title)

        self._btn_edit_author = QPushButton("Edit Author")
        self._btn_edit_author.setEnabled(False)
        self._btn_edit_author.clicked.connect(lambda: self._on_edit_field("author", "Author"))
        edit_row.addWidget(self._btn_edit_author)

        self._btn_add_tag = QPushButton("+ Tag")
        self._btn_add_tag.setEnabled(False)
        self._btn_add_tag.clicked.connect(self._on_add_tag)
        edit_row.addWidget(self._btn_add_tag)

        self._btn_add_collection = QPushButton("+ Collection")
        self._btn_add_collection.setEnabled(False)
        self._btn_add_collection.clicked.connect(self._on_add_collection)
        edit_row.addWidget(self._btn_add_collection)

        self._btn_attach = QPushButton("Attach File")
        self._btn_attach.setEnabled(False)
        self._btn_attach.clicked.connect(self._on_attach_file)
        edit_row.addWidget(self._btn_attach)

        self._btn_delete = QPushButton("Delete Document")
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet("color: #c00;")
        self._btn_delete.clicked.connect(self._on_delete_document)
        edit_row.addWidget(self._btn_delete)

        edit_row.addStretch()
        layout.addLayout(edit_row)

        self._tag_label = QLabel("")
        self._tag_label.setWordWrap(True)
        self._tag_label.setStyleSheet("margin-top: 4px;")
        layout.addWidget(self._tag_label)

        self._collection_label = QLabel("")
        self._collection_label.setWordWrap(True)
        self._collection_label.setStyleSheet("margin-top: 4px;")
        layout.addWidget(self._collection_label)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _load_entries(self, force: bool = False) -> None:
        self._collection_combo.setEnabled(False)
        self._library.load_entries(force=force, fts_engine=self.vault.core.fts)

    def _on_entries_loaded(self, entries: list[LiteratureEntry]) -> None:
        self._model.set_entries(entries)
        self._collection_combo.setEnabled(True)

        all_collections = set()
        for e in entries:
            for col in e.collections:
                all_collections.add(col)

        current = self._collection_combo.currentText()
        self._collection_combo.blockSignals(True)
        self._collection_combo.clear()
        self._collection_combo.addItem("All")
        for col in sorted(all_collections):
            self._collection_combo.addItem(col)

        if current in all_collections:
            self._collection_combo.setCurrentText(current)
        self._collection_combo.blockSignals(False)

        if self._pending_selection:
            self.select_entry(self._pending_selection)
            self._pending_selection = None

    def _on_load_error(self, message: str) -> None:
        self._collection_combo.setEnabled(True)
        QMessageBox.critical(self, "Library Load Error", message)

    def _on_search(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)

    def _on_collection_changed(self, text: str) -> None:
        self._proxy.set_collection_filter(text)

    def _on_entry_selected(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        entry = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, LiteratureEntry):
            self._current = entry
            self._show_detail(entry)

    def _show_detail(self, e: LiteratureEntry) -> None:
        self._detail_title.setText(e.title or e.key)
        data_map = {
            "Author": e.author,
            "Year": e.year,
            "Journal": e.journal,
            "Publisher": e.publisher,
            "DOI": e.doi,
            "ISBN": e.isbn,
            "Volume": e.volume,
            "Issue": e.issue,
            "Page": e.page,
            "PDF": str(e.pdf_path) if e.pdf_path else "—",
        }
        for f, v in data_map.items():
            if f in self._field_labels:
                self._field_labels[f].setText(v or "—")

        self._refresh_tag_display(e)
        self._refresh_collection_display(e)

        has_pdf = bool(e.pdf_path and e.pdf_path.exists())
        self._btn_open_pdf.setEnabled(has_pdf)
        for btn in (
            self._btn_copy_key,
            self._btn_create_note,
            self._btn_edit_title,
            self._btn_edit_author,
            self._btn_add_tag,
            self._btn_add_collection,
            self._btn_attach,
            self._btn_delete,
        ):
            btn.setEnabled(True)

    def _refresh_tag_display(self, e: LiteratureEntry) -> None:
        tag_str = "  ".join(f"[{t}]" for t in e.tags) if e.tags else "—"
        self._tag_label.setText(f"Tags: {tag_str}")

    def _refresh_collection_display(self, e: LiteratureEntry) -> None:
        coll_str = "  ".join(f"[{c}]" for c in e.collections) if e.collections else "—"
        self._collection_label.setText(f"Collections: {coll_str}")

    def _refresh_list_item(self, entry: LiteratureEntry) -> None:
        idx = self._entry_list.currentIndex()
        if idx.isValid():
            # Emit dataChanged for the current index and its source index if using a proxy
            self._model.dataChanged.emit(self._proxy.mapToSource(idx), self._proxy.mapToSource(idx))
        else:
            self._model.layoutChanged.emit()

    def _on_open_pdf(self) -> None:
        if self._current and self._current.pdf_path:
            self.pdf_open_requested.emit(self._current.pdf_path, self._current.key)

    def _on_copy_key(self) -> None:
        if self._current:
            QApplication.clipboard().setText(f"@{self._current.key}")

    def _on_create_note(self) -> None:
        if self._current:
            self.note_create_requested.emit(self._current.key, self._current.title)

    def _on_add_document(self) -> None:
        dlg = AddDocumentDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        entry = self._bridge.add_document(
            pdf_path=dlg.pdf_path,
            title=dlg.title,
            author=dlg.author,
            year=dlg.year,
            journal=dlg.journal,
            publisher=dlg.publisher,
            doi=dlg.doi,
            isbn=dlg.isbn,
            volume=dlg.volume,
            issue=dlg.issue,
            page=dlg.page,
            abstract=dlg.abstract,
            tags=dlg.tags or None,
            collections=dlg.collections or None,
            from_doi=dlg.from_doi,
            from_arxiv=dlg.from_arxiv,
            from_isbn=dlg.from_isbn,
            fts_engine=self.vault.core.fts,
            track_changes_callback=self.vault.track_changes,
        )
        if entry:
            self._pending_selection = entry.key
            self._load_entries(force=True)
            self.library_changed.emit()
            self.on_changed()
            QMessageBox.information(self, "Success", f"Document added: @{entry.key}")
        else:
            QMessageBox.warning(self, "Failed", "Document could not be added.")

    def _on_edit_field(self, field_name: str, label: str) -> None:
        if not self._current:
            return
        val = getattr(self._current, field_name, "")
        new_val, ok = QInputDialog.getText(self, f"Edit {label}", f"{label}:", text=str(val))
        if ok and new_val.strip() != val:
            if self._bridge.update_field(
                self._current.key,
                field_name,
                new_val.strip(),
                fts_engine=self.vault.core.fts,
                track_changes_callback=self.vault.track_changes,
            ):
                self._show_detail(self._current)
                self._refresh_list_item(self._current)
                self.library_changed.emit()
                self.on_changed()

    def _on_add_tag(self) -> None:
        if not self._current:
            return
        tag, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")
        if ok and tag.strip():
            if self._bridge.append_tag(
                self._current.key,
                tag.strip(),
                fts_engine=self.vault.core.fts,
                track_changes_callback=self.vault.track_changes,
            ):
                self._refresh_tag_display(self._current)
                self.vault.tags_updated.emit()
                self.library_changed.emit()
                self.on_changed()

    def _on_remove_tag(self, tag: str) -> None:
        if not self._current:
            return
        if (
            QMessageBox.question(
                self, "Delete Tag", f'Delete tag "{tag}" from @{self._current.key}?'
            )
            == QMessageBox.StandardButton.Yes
        ):
            if self._bridge.remove_tag(
                self._current.key,
                tag,
                fts_engine=self.vault.core.fts,
                track_changes_callback=self.vault.track_changes,
            ):
                self._refresh_tag_display(self._current)
                self.vault.tags_updated.emit()
                self.library_changed.emit()
                self.on_changed()

    def _on_add_collection(self) -> None:
        if not self._current:
            return
        coll, ok = QInputDialog.getText(self, "Add Collection", "Collection name:")
        if ok and coll.strip():
            if self._bridge.append_collection(
                self._current.key, 
                coll.strip(),
                track_changes_callback=self.vault.track_changes
            ):
                self._refresh_collection_display(self._current)
                self._load_entries(force=True)
                self.library_changed.emit()
                self.on_changed()

    def _on_remove_collection(self, collection: str) -> None:
        if not self._current:
            return
        if (
            QMessageBox.question(
                self,
                "Delete Collection",
                f'Delete collection "{collection}" from @{self._current.key}?',
            )
            == QMessageBox.StandardButton.Yes
        ):
            if self._bridge.remove_collection(
                self._current.key, 
                collection,
                track_changes_callback=self.vault.track_changes
            ):
                self._refresh_collection_display(self._current)
                self._load_entries(force=True)
                self.library_changed.emit()
                self.on_changed()

    def _on_delete_document(self) -> None:
        if not self._current:
            return
        if (
            QMessageBox.question(self, "Delete Document", f"Delete document @{self._current.key}?")
            == QMessageBox.StandardButton.Yes
        ):
            key = self._current.key
            if self._bridge.delete_document(
                key, 
                fts_engine=self.vault.core.fts,
                track_changes_callback=lambda p: self.on_changed()
            ):
                self._current = None
                self._load_entries(force=True)
                self.on_changed()

    def _show_list_context_menu(self, pos) -> None:
        index = self._entry_list.indexAt(pos)
        if not index.isValid():
            return
        entry = index.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        if entry.tags:
            tag_menu = menu.addMenu("Delete Tag")
            for tag in entry.tags:
                tag_menu.addAction(tag).triggered.connect(lambda _, t=tag: self._on_remove_tag(t))
        if entry.collections:
            coll_menu = menu.addMenu("Delete Collection")
            for coll in entry.collections:
                coll_menu.addAction(coll).triggered.connect(
                    lambda _, c=coll: self._on_remove_collection(c)
                )
        menu.addSeparator()
        menu.addAction("Edit Title…").triggered.connect(
            lambda: self._on_edit_field("title", "Title")
        )
        menu.addAction("Edit Author…").triggered.connect(
            lambda: self._on_edit_field("author", "Author")
        )
        menu.exec(self._entry_list.mapToGlobal(pos))

    def _on_attach_file(self) -> None:
        if not self._current:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*)")
        if not path:
            return

        if self._bridge.attach_file(self._current.key, Path(path)):
            # Update UI state first
            self._refresh_list_item(self._current)
            self._show_detail(self._current)
            
            # Notify user
            QMessageBox.information(self, "Success", "File successfully attached.")
            
            # Trigger background tasks after dialog is closed to avoid race conditions
            self.on_changed()
            self.library_changed.emit()
