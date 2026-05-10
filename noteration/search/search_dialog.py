"""
noteration/search/search_dialog.py
Global vault search dialog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import shiboken6
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
    QCheckBox, QGroupBox, QRadioButton, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
from PySide6.QtGui import QKeySequence, QShortcut

from noteration.search.vault_search import VaultSearch, SearchResult


class SearchWorker(QObject):
    """Worker to perform search in a background thread."""
    results_ready = Signal(list)
    finished = Signal()

    def __init__(
        self,
        searcher: VaultSearch,
        query: str,
        case_sensitive: bool,
        use_regex: bool,
        scope: str,
    ) -> None:
        super().__init__()
        self.searcher = searcher
        self.query = query
        self.case_sensitive = case_sensitive
        self.use_regex = use_regex
        self.scope = scope

    def run(self) -> None:
        try:
            all_results = self.searcher.search(
                self.query, self.case_sensitive, self.use_regex
            )

            # Filter based on scope if not "all"
            if self.scope != "all":
                type_map = {
                    "notes": "note",
                    "literature": "literature",
                    "annotations": "annotation"
                }
                target_type = type_map.get(self.scope)
                if target_type:
                    all_results = [r for r in all_results if r.type == target_type]
            
            self.results_ready.emit(all_results)
        except Exception as e:
            print(f"[SearchWorker] Error: {e}")
            self.results_ready.emit([])
        finally:
            self.finished.emit()


class SearchDialog(QDialog):
    """Dialog for global vault search."""

    # Signals emitted when a result is clicked
    note_requested = Signal(Path)           # Open note
    literature_requested = Signal(str)       # Open literature by papis_key
    annotation_requested = Signal(str, int) # Open PDF at specific page

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
        
        # Threading members
        self._search_thread: Optional[QThread] = None
        self._search_worker: Optional[SearchWorker] = None

        self.setWindowTitle("Search Vault")
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
        self._search_input.setPlaceholderText("Type search keywords...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_text_changed)
        self._search_input.returnPressed.connect(self._on_return_pressed)
        input_row.addWidget(self._search_input, 1)

        self._case_cb = QCheckBox("Aa")
        self._case_cb.setToolTip("Case sensitive")
        self._case_cb.toggled.connect(self._perform_search)
        input_row.addWidget(self._case_cb)

        self._regex_cb = QCheckBox(".*")
        self._regex_cb.setToolTip("Use regex")
        self._regex_cb.toggled.connect(self._perform_search)
        input_row.addWidget(self._regex_cb)

        layout.addLayout(input_row)

        # Filter scope
        scope_group = QGroupBox("Search in:")
        scope_layout = QHBoxLayout(scope_group)
        scope_layout.setContentsMargins(8, 4, 8, 4)

        self._scope_all = QRadioButton("All")
        self._scope_all.setChecked(True)
        self._scope_all.toggled.connect(self._perform_search)

        self._scope_notes = QRadioButton("Notes")
        self._scope_notes.toggled.connect(self._perform_search)

        self._scope_lit = QRadioButton("Literature")
        self._scope_lit.toggled.connect(self._perform_search)

        self._scope_ann = QRadioButton("Annotations")
        self._scope_ann.toggled.connect(self._perform_search)

        scope_layout.addWidget(self._scope_all)
        scope_layout.addWidget(self._scope_notes)
        scope_layout.addWidget(self._scope_lit)
        scope_layout.addWidget(self._scope_ann)
        scope_layout.addStretch()

        layout.addWidget(scope_group)

        # Progress bar (hidden by default)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0) # Indeterminate
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.hide()
        layout.addWidget(self._progress)

        # Results tree
        self._results_tree = QTreeWidget()
        self._results_tree.setHeaderLabels(["Type", "Title / Info", "Snippet"])
        self._results_tree.setColumnWidth(0, 100)
        self._results_tree.setColumnWidth(1, 250)
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.itemActivated.connect(self._on_item_activated)
        self._results_tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._results_tree, 1)

        # Status bar
        status_row = QHBoxLayout()
        self._status_label = QLabel("Type to start searching")
        status_row.addWidget(self._status_label, 1)

        self._prev_btn = QPushButton("↑ Previous")
        self._prev_btn.setEnabled(False)
        self._prev_btn.clicked.connect(self._go_prev)
        status_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton("↓ Next")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._go_next)
        status_row.addWidget(self._next_btn)

        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.close)
        status_row.addWidget(self._close_btn)

        layout.addLayout(status_row)

        # Debounce timer for live search
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._perform_search)

        # Set focus
        self._search_input.setFocus()

    def _setup_shortcuts(self) -> None:
        # Ctrl+F: Focus to search input
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
            self._abort_search()
            self._results_tree.clear()
            self._status_label.setText("Type at least 2 characters to search")
            self._update_nav_buttons()

    def _on_return_pressed(self) -> None:
        self._debounce_timer.stop()
        self._perform_search()

    def _abort_search(self) -> None:
        """Stop current background search if running."""
        if self._search_thread and shiboken6.isValid(self._search_thread):
            if self._search_thread.isRunning():
                self._search_thread.quit()
                self._search_thread.wait()
            self._search_thread.deleteLater()
            self._search_thread = None
        
        if self._search_worker and shiboken6.isValid(self._search_worker):
            self._search_worker.deleteLater()
            self._search_worker = None
            
        self._progress.hide()

    def _perform_search(self) -> None:
        query = self._search_input.text().strip()
        if len(query) < 2:
            self._abort_search()
            self._results_tree.clear()
            self._status_label.setText("Type at least 2 characters to search")
            self._update_nav_buttons()
            return

        self._abort_search()

        case_sensitive = self._case_cb.isChecked()
        use_regex = self._regex_cb.isChecked()
        scope = self._get_scope()

        self._status_label.setText("Searching...")
        self._progress.show()

        # Create worker and thread
        self._search_thread = QThread()
        self._search_worker = SearchWorker(
            self._searcher, query, case_sensitive, use_regex, scope
        )
        self._search_worker.moveToThread(self._search_thread)

        # Connect signals
        self._search_thread.started.connect(self._search_worker.run)
        self._search_worker.results_ready.connect(self._on_results_ready)
        self._search_worker.finished.connect(self._search_thread.quit)
        self._search_worker.finished.connect(self._clear_search_thread)
        self._search_thread.finished.connect(self._search_thread.deleteLater)
        self._search_thread.finished.connect(lambda: self._progress.hide())

        self._search_thread.start()

    def _clear_search_thread(self) -> None:
        self._search_thread = None
        self._search_worker = None

    def _on_results_ready(self, results: list[SearchResult]) -> None:
        self._results = results
        self._current_index = -1
        self._populate_tree(results)

    def _populate_tree(self, results: list[SearchResult]) -> None:
        self._results_tree.clear()

        # Group by type
        notes = [r for r in results if r.type == "note"]
        literature = [r for r in results if r.type == "literature"]
        annotations = [r for r in results if r.type == "annotation"]

        total = len(results)
        self._status_label.setText(f"{total} results found")

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
            group.setText(0, f"📚 Literature ({len(literature)})")
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
            group.setText(0, f"📌 Annotations ({len(annotations)})")
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
        """Set initial query and search immediately."""
        self._search_input.setText(text)
        self._perform_search()

    def closeEvent(self, event) -> None:
        self._abort_search()
        super().closeEvent(event)
