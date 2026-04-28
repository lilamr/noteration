"""
noteration/search/search_dialog.py
Dialog pencarian global vault.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
    QCheckBox, QGroupBox, QRadioButton,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut

from noteration.search.vault_search import VaultSearch, SearchResult


class SearchDialog(QDialog):
    """Dialog untuk pencarian global vault."""

    # Signal yang dipancarkan saat hasil di-klik
    note_requested = Signal(Path)           # Buka note
    literature_requested = Signal(str)       # Buka literatur by papis_key
    annotation_requested = Signal(str, int) # Buka PDF di page tertentu

    def __init__(
        self,
        vault_path: Path,
        papis_bridge=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        self._searcher = VaultSearch(vault_path, papis_bridge)
        self._results: list[SearchResult] = []
        self._current_index = -1

        self.setWindowTitle("Cari di Vault")
        self.setMinimumSize(700, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._setup_ui()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Search input row
        input_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Ketik kata kunci pencarian...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_text_changed)
        self._search_input.returnPressed.connect(self._on_return_pressed)
        input_row.addWidget(self._search_input, 1)

        self._case_cb = QCheckBox("Aa")
        self._case_cb.setToolTip("Case sensitive")
        self._case_cb.toggled.connect(self._perform_search)
        input_row.addWidget(self._case_cb)

        self._regex_cb = QCheckBox(".*")
        self._regex_cb.setToolTip("Gunakan regex")
        self._regex_cb.toggled.connect(self._perform_search)
        input_row.addWidget(self._regex_cb)

        layout.addLayout(input_row)

        # Filter scope
        scope_group = QGroupBox("Cari di:")
        scope_layout = QHBoxLayout(scope_group)
        scope_layout.setContentsMargins(8, 4, 8, 4)

        self._scope_all = QRadioButton("Semua")
        self._scope_all.setChecked(True)
        self._scope_all.toggled.connect(self._perform_search)

        self._scope_notes = QRadioButton("Notes")
        self._scope_notes.toggled.connect(self._perform_search)

        self._scope_lit = QRadioButton("Literatur")
        self._scope_lit.toggled.connect(self._perform_search)

        self._scope_ann = QRadioButton("Anotasi")
        self._scope_ann.toggled.connect(self._perform_search)

        scope_layout.addWidget(self._scope_all)
        scope_layout.addWidget(self._scope_notes)
        scope_layout.addWidget(self._scope_lit)
        scope_layout.addWidget(self._scope_ann)
        scope_layout.addStretch()

        layout.addWidget(scope_group)

        # Results tree
        self._results_tree = QTreeWidget()
        self._results_tree.setHeaderLabels(["Jenis", "Judul / Info", "Snippet"])
        self._results_tree.setColumnWidth(0, 100)
        self._results_tree.setColumnWidth(1, 250)
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.itemActivated.connect(self._on_item_activated)
        self._results_tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._results_tree, 1)

        # Status bar
        status_row = QHBoxLayout()
        self._status_label = QLabel("Ketik untuk mulai mencari")
        status_row.addWidget(self._status_label, 1)

        self._prev_btn = QPushButton("↑ Sebelumnya")
        self._prev_btn.setEnabled(False)
        self._prev_btn.clicked.connect(self._go_prev)
        status_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton("↓ Berikutnya")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._go_next)
        status_row.addWidget(self._next_btn)

        self._close_btn = QPushButton("Tutup")
        self._close_btn.clicked.connect(self.close)
        status_row.addWidget(self._close_btn)

        layout.addLayout(status_row)

        # Debounce timer untuk live search
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._perform_search)

        # Set focus
        self._search_input.setFocus()

    def _setup_shortcuts(self) -> None:
        # Ctrl+F: Focus ke search input
        shortcut_find = QShortcut(QKeySequence.StandardKey.Find, self)
        shortcut_find.activated.connect(self._focus_input)

        # F3 / Ctrl+G: Next result
        shortcut_next = QShortcut(QKeySequence("F3"), self)
        shortcut_next.activated.connect(self._go_next)

        # Shift+F3 / Shift+Ctrl+G: Previous result
        shortcut_prev = QShortcut(QKeySequence("Shift+F3"), self)
        shortcut_prev.activated.connect(self._go_prev)

        # Escape: close
        shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        shortcut_esc.activated.connect(self.close)

    def _focus_input(self) -> None:
        self._search_input.selectAll()
        self._search_input.setFocus()

    def _get_scope(self) -> str:
        if self._scope_notes.isChecked():
            return "notes"
        elif self._scope_lit.isChecked():
            return "literature"
        elif self._scope_ann.isChecked():
            return "annotations"
        return "all"

    def _on_text_changed(self, text: str) -> None:
        self._debounce_timer.stop()
        if len(text) >= 2:
            self._debounce_timer.start()
        elif len(text) == 0:
            self._results_tree.clear()
            self._status_label.setText("Ketik minimal 2 karakter untuk mencari")
            self._update_nav_buttons()

    def _on_return_pressed(self) -> None:
        self._debounce_timer.stop()
        self._perform_search()

    def _perform_search(self) -> None:
        query = self._search_input.text().strip()
        if len(query) < 2:
            self._results_tree.clear()
            self._status_label.setText("Ketik minimal 2 karakter untuk mencari")
            self._update_nav_buttons()
            return

        case_sensitive = self._case_cb.isChecked()
        use_regex = self._regex_cb.isChecked()
        scope = self._get_scope()

        # Untuk scope tertentu, filter hasil
        all_results = self._searcher.search(query, case_sensitive, use_regex)

        # Filter berdasarkan scope jika bukan "all"
        if scope != "all":
            type_map = {"notes": "note", "literature": "literature", "annotations": "annotation"}
            target_type = type_map.get(scope)
            if target_type:
                all_results = [r for r in all_results if r.type == target_type]

        self._results = all_results
        self._current_index = -1
        self._populate_tree(all_results)

    def _populate_tree(self, results: list[SearchResult]) -> None:
        self._results_tree.clear()

        # Group by type
        notes = [r for r in results if r.type == "note"]
        literature = [r for r in results if r.type == "literature"]
        annotations = [r for r in results if r.type == "annotation"]

        total = len(results)
        self._status_label.setText(f"{total} hasil ditemukan")

        # Notes group
        if notes:
            group = QTreeWidgetItem(self._results_tree)
            group.setText(0, f"📝 Notes ({len(notes)})")
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for r in notes:
                item = QTreeWidgetItem(group)
                item.setText(0, "Note")
                item.setText(1, r.title)
                item.setText(2, r.snippet)
                item.setData(0, Qt.ItemDataRole.UserRole, r)
            group.setExpanded(True)

        # Literature group
        if literature:
            group = QTreeWidgetItem(self._results_tree)
            group.setText(0, f"📚 Literatur ({len(literature)})")
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for r in literature:
                item = QTreeWidgetItem(group)
                item.setText(0, "Lit")
                item.setText(1, r.title)
                item.setText(2, r.snippet)
                item.setData(0, Qt.ItemDataRole.UserRole, r)
            group.setExpanded(True)

        # Annotations group
        if annotations:
            group = QTreeWidgetItem(self._results_tree)
            group.setText(0, f"📌 Anotasi ({len(annotations)})")
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for r in annotations:
                item = QTreeWidgetItem(group)
                item.setText(0, "Ann")
                item.setText(1, r.title)
                item.setText(2, r.snippet)
                item.setData(0, Qt.ItemDataRole.UserRole, r)
            group.setExpanded(True)

        self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        has_results = len(self._results) > 0
        self._prev_btn.setEnabled(has_results)
        self._next_btn.setEnabled(has_results)

    def _on_item_activated(self, item: QTreeWidgetItem, column: int) -> None:
        self._navigate_to_item(item)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        # Track current selection
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self._current_index = next(
                (i for i, r in enumerate(self._results) if r == data), -1
            )

    def _navigate_to_item(self, item: QTreeWidgetItem) -> None:
        data: Optional[SearchResult] = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data.type == "note" and data.path:
            self.note_requested.emit(data.path)
            self.close()
        elif data.type == "literature" and data.papis_key:
            self.literature_requested.emit(data.papis_key)
            self.close()
        elif data.type == "annotation" and data.papis_key:
            page = data.page if data.page is not None else 0
            self.annotation_requested.emit(data.papis_key, page + 1)  # 1-indexed
            self.close()

    def _go_next(self) -> None:
        if not self._results:
            return
        self._current_index = (self._current_index + 1) % len(self._results)
        self._select_result(self._current_index)

    def _go_prev(self) -> None:
        if not self._results:
            return
        self._current_index = (self._current_index - 1) % len(self._results)
        self._select_result(self._current_index)

    def _select_result(self, index: int) -> None:
        if index < 0 or index >= len(self._results):
            return
        result = self._results[index]
        # Find and select the corresponding tree item
        for i in range(self._results_tree.topLevelItemCount()):
            group = self._results_tree.topLevelItem(i)
            if group:
                for j in range(group.childCount()):
                    child = group.child(j)
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if data == result:
                    self._results_tree.setCurrentItem(child)
                    self._results_tree.scrollToItem(child)
                    return

    def set_initial_query(self, text: str) -> None:
        """Set query awal dan langsung cari."""
        self._search_input.setText(text)
        self._perform_search()
