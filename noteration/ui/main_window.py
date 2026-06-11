"""Noteration main window.
"""

from __future__ import annotations

import contextlib
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, cast

if TYPE_CHECKING:
    from noteration.sync.git_engine import RepoStatus

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QToolBar,
    QWidget,
)

from noteration import __version__
from noteration.core.events import LiteratureSelectedEvent, NoteOpenedEvent, VaultChangedEvent
from noteration.dialogs.encryption_dialog import EncryptionDialog
from noteration.logger import get_logger
from noteration.search.search_dialog import SearchDialog
from noteration.sync.updater import (
    CheckUpdateThread,
    get_latest_binary_url,
    is_frozen,
    run_update_process,
)
from noteration.ui.backlink_panel import BacklinkPanel
from noteration.ui.editor_tab import EditorTab
from noteration.ui.graph_view import GraphView
from noteration.ui.literature_tab import LiteratureTab
from noteration.ui.pdf_viewer_tab import PdfViewerTab
from noteration.ui.sidebar import SidebarWidget
from noteration.ui.sync_tab import SyncTab
from noteration.vault_manager import VaultManager

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    # Forwarded to app.py → apply_theme(app, mode)
    theme_change_requested = Signal(str)

    def __init__(
        self,
        vault_path: Path,
        storage_path: Optional[Path] = None,
        secret_key: Optional[str] = None,
        session_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        # Initialize VaultManager (Business logic orchestrator)
        self.vault = VaultManager(
            vault_path,
            storage_path=storage_path,
            secret_key=secret_key,
            session_path=session_path,
            parent=self,
        )

        # Shortcuts for MainWindow accessibility
        self.vault_path = self.vault.vault_path
        self.storage_path = self.vault.storage_path
        self.config = self.vault.config
        self._pdf_index = self.vault.pdf_index
        self._graph = self.vault.graph

        self._focus_mode_active = False
        self._focus_listener_connected = False
        self._update_thread: Optional[CheckUpdateThread] = None

        # Navigation history
        self._history: deque[Path] = deque(maxlen=50)
        self._forward_stack: List[Path] = []
        self._is_navigating = False

        # Graph view components
        self._graph_view: GraphView | None = None
        self._graph_dock: QDockWidget | None = None
        self._graph_view_action = None

        self.setWindowTitle(f"Noteration v{__version__} — {vault_path.name}")
        self.resize(1360, 840)
        self.setMinimumSize(900, 560)

        self._setup_statusbar()
        self._setup_actions()
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_autosave()

        # Connect signals from VaultManager to UI components
        self.vault.status_message.connect(self.statusBar().showMessage)
        self.vault.git_status_updated.connect(self._on_git_status_updated)
        self.vault.graph_updated.connect(lambda _: self._backlink_panel.refresh_all())
        self.vault.graph_updated.connect(
            lambda _: self._graph_view.refresh() if self._graph_view else None
        )
        self.vault.indexing_finished.connect(self._on_indexing_finished)
        self.vault.tags_updated.connect(lambda: self.sidebar.update_tags(self.vault.get_all_tags()))

        # Trigger background initialization tasks sequentially via signals
        self.vault.git_status_updated.connect(self._on_first_git_status)
        self.vault.indexing_finished.connect(self._on_first_indexing_finished)
        self.vault.graph_updated.connect(self._on_first_graph_updated)

        # Connect to EventBus
        self.vault.core.events.subscribe(NoteOpenedEvent, self._on_note_opened_event)
        self.vault.core.events.subscribe(
            LiteratureSelectedEvent, self._on_literature_selected_event
        )
        self.vault.core.events.subscribe(
            VaultChangedEvent, lambda _: self.vault.request_git_status()
        )

        # Start the chain
        self.vault.request_git_status()

    def _on_first_git_status(self) -> None:
        """Step 1 of init chain finished. Start Step 2."""
        # Disconnect so this only runs once
        with contextlib.suppress(Exception):
            self.vault.git_status_updated.disconnect(self._on_first_git_status)

        if self._is_alive():
            self.vault.scan_pdfs()

    def _on_first_indexing_finished(self) -> None:
        """Step 2 of init chain finished. Start Step 3."""
        with contextlib.suppress(Exception):
            self.vault.indexing_finished.disconnect(self._on_first_indexing_finished)

        if self._is_alive():
            self.vault.build_graph()

    def _on_first_graph_updated(self) -> None:
        """Step 3 of init chain finished. Finalize UI."""
        with contextlib.suppress(Exception):
            self.vault.graph_updated.disconnect(self._on_first_graph_updated)

        if self._is_alive():
            # Update tags as the final step
            self.sidebar.update_tags(self.vault.get_all_tags())
            # Notify manager that init is fully done
            self.vault.initialization_finished.emit()

    def _is_alive(self) -> bool:
        """Check if the C++ object is still alive."""
        try:
            return self.isVisible() or self.isVisible() is False
        except RuntimeError:
            return False

    # ── UI construction ───────────────────────────────────────────────

    def _setup_actions(self) -> None:
        """Initialize shared actions for menu, toolbar, and shortcuts."""
        self._act_new = QAction("New Note", self)
        self._act_new.setShortcut(QKeySequence.StandardKey.New)
        self._act_new.triggered.connect(self._new_note)
        self.addAction(self._act_new)  # Ensure shortcut works even when menu is hidden

        self._act_save = QAction("Save", self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._save_current)
        self.addAction(self._act_save)

        self._act_back = QAction("Back", self)
        self._act_back.setShortcut(QKeySequence("Alt+Left"))
        self._act_back.triggered.connect(self._navigate_back)
        self.addAction(self._act_back)

        self._act_forward = QAction("Forward", self)
        self._act_forward.setShortcut(QKeySequence("Alt+Right"))
        self._act_forward.triggered.connect(self._navigate_forward)
        self.addAction(self._act_forward)

    def _setup_ui(self) -> None:
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(lambda idx: self._close_tab_from_widget(self.tabs, idx))
        self.tabs.currentChanged.connect(
            lambda idx: self._on_tab_changed_for_widget(self.tabs, idx)
        )

        self.tabs_split = QTabWidget()
        self.tabs_split.setTabsClosable(True)
        self.tabs_split.setMovable(True)
        self.tabs_split.tabCloseRequested.connect(
            lambda idx: self._close_tab_from_widget(self.tabs_split, idx)
        )
        self.tabs_split.currentChanged.connect(
            lambda idx: self._on_tab_changed_for_widget(self.tabs_split, idx)
        )
        self.tabs_split.hide()

        # Setup context menu on both tab bars
        bar_main = self.tabs.tabBar()
        bar_main.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar_main.customContextMenuRequested.connect(
            lambda pos: self._show_tab_context_menu(self.tabs, pos)
        )
        bar_split = self.tabs_split.tabBar()
        bar_split.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar_split.customContextMenuRequested.connect(
            lambda pos: self._show_tab_context_menu(self.tabs_split, pos)
        )

        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.tabs_split)
        self.setCentralWidget(self.splitter)

        # Default active tab widget
        self._active_tab_widget = self.tabs

        # Setup global focus listener to track active pane
        self._connect_focus_listener()

        # Left dock: Navigator (sidebar)
        self.sidebar = SidebarWidget(self.vault_path, self.config)
        self.sidebar.note_selected.connect(self._open_note)
        self.sidebar.pdf_selected.connect(self._open_pdf)
        self.sidebar.heading_clicked.connect(self._go_to_heading)
        self.sidebar.citation_clicked.connect(self._go_to_citation)
        self.sidebar.open_literature_requested.connect(self._open_literature_by_key)
        self.sidebar.tag_clicked.connect(self._on_tag_clicked)
        self.sidebar.item_moved.connect(self._on_note_moved)

        self._sidebar_dock = QDockWidget("Navigator", self)
        self._sidebar_dock.setWidget(self.sidebar)
        self._sidebar_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._sidebar_dock.setMinimumWidth(200)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._sidebar_dock)

        # Apply sidebar visibility from configuration
        show_sidebar = self.config.get("ui", "sidebar_visible", True)
        if not show_sidebar:
            self._sidebar_dock.hide()

        # Right dock: Tabbed (Backlinks + Graph)
        self._backlink_panel = BacklinkPanel(self._graph)
        self._backlink_panel.note_requested.connect(self._follow_wiki_link)
        self._backlink_panel.rebuild_requested.connect(self._build_link_graph)
        # 3. Graph View
        self._graph_view = GraphView(self.vault)
        self._graph_view.node_clicked.connect(self._follow_wiki_link)

        self._right_tabs = QTabWidget()
        self._right_tabs.addTab(self._backlink_panel, "Backlinks")
        self._right_tabs.addTab(self._graph_view, "Graph")

        self._right_dock = QDockWidget("Link Graph", self)
        self._right_dock.setWidget(self._right_tabs)
        self._right_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._right_dock.setMinimumWidth(250)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._right_dock)

        # Apply sidebar visibility to the right dock as well
        if not show_sidebar:
            self._right_dock.hide()

    def _setup_menu(self) -> None:
        mb = self.menuBar()

        # File Menu
        fm = mb.addMenu("&File")
        fm.addAction(self._act_new)
        fm.addAction("Open Vault…", self._open_vault_dialog)
        fm.addSeparator()
        fm.addAction(self._act_save)

        exm = fm.addMenu("Export Note as…")
        exm.addAction("HTML", lambda: self._export_current_note("html"))
        exm.addAction("PDF", lambda: self._export_current_note("pdf"))
        exm.addAction("DOCX", lambda: self._export_current_note("docx"))
        exm.addAction("ODT", lambda: self._export_current_note("odt"))
        exm.addAction("LaTeX", lambda: self._export_current_note("latex"))
        exm.addAction("Plain Text (TXT)", lambda: self._export_current_note("txt"))

        fm.addSeparator()
        fm.addAction("Exit", self.close, QKeySequence.StandardKey.Quit)

        # View Menu
        vm = mb.addMenu("&View")
        vm.addAction(self._sidebar_dock.toggleViewAction())
        vm.addAction(self._right_dock.toggleViewAction())
        vm.addSeparator()
        self._act_focus = QAction("Focus Mode", self)
        self._act_focus.setShortcut("F11")
        self._act_focus.setCheckable(True)
        self._act_focus.triggered.connect(self._toggle_focus_mode)
        vm.addAction(self._act_focus)
        vm.addSeparator()
        vm.addAction("Literature", self._open_literature_tab)
        vm.addAction("Synchronization", self._open_sync_tab)

        # Search Action
        search_action = QAction("&Search", self)
        search_action.triggered.connect(self._open_search_dialog)
        search_action.setShortcut(QKeySequence.StandardKey.Find)
        mb.addAction(search_action)

        # Tools Menu
        tm = mb.addMenu("&Tools")
        tm.addAction("Sync Now", self._sync, "Ctrl+Shift+S")
        tm.addSeparator()
        tm.addAction("Export BibTeX (all)…", self._export_bibtex_all)
        tm.addAction("Export BibTeX (this note)…", self._export_bibtex_note)
        tm.addSeparator()
        tm.addAction("Rebuild Backlink Graph", self._build_link_graph)
        tm.addAction("Scan PDF Index", self._scan_pdf_index)
        tm.addSeparator()

        is_encrypted = self.config.get("security", "encryption_enabled", False)
        act_encrypt = tm.addAction("Encrypt Vault (age)…", self._open_encryption_dialog)
        if is_encrypted:
            act_encrypt.setEnabled(False)
            act_encrypt.setToolTip("This vault is already encrypted.")

        tm.addSeparator()
        tm.addAction("Settings…", self._open_settings, QKeySequence.StandardKey.Preferences)

        hm = mb.addMenu("&Help")
        hm.addAction("Check for Updates", lambda: self._check_for_updates(silent=False))
        hm.addAction("Guide", self._open_guide, QKeySequence.StandardKey.HelpContents)
        hm.addAction("CLI Guide", self._open_cli_guide)
        hm.addAction("REST API Guide", self._open_api_guide)
        hm.addAction("Research and Writing", self._open_research_writing, "F2")
        hm.addSeparator()
        hm.addAction("About Noteration", self._about)

    def _setup_toolbar(self) -> None:
        self._main_toolbar = QToolBar("Main Toolbar", self)
        self._main_toolbar.setMovable(False)
        self._main_toolbar.setFloatable(False)
        self.addToolBar(self._main_toolbar)

        self._main_toolbar.addAction(self._act_new)
        self._main_toolbar.addSeparator()
        self._main_toolbar.addAction(self._act_save)
        self._main_toolbar.addAction("Literature", self._open_literature_tab)
        self._main_toolbar.addAction("Sync", self._sync)
        self._main_toolbar.addSeparator()
        self._main_toolbar.addAction("Navigator", self._sidebar_dock.toggleViewAction().trigger)
        self._main_toolbar.addAction("Link Graph", self._right_dock.toggleViewAction().trigger)

        sp = QWidget()
        sp.setMinimumWidth(8)
        self._main_toolbar.addWidget(sp)

        self._sync_badge = QLabel("Git: offline")
        self._sync_badge.setStyleSheet(
            "padding:2px 8px;border-radius:8px;background:#F5F5F5;color:#616161;font-size:11px;"
        )
        self._main_toolbar.addWidget(self._sync_badge)

    def _setup_statusbar(self) -> None:
        sb = self.statusBar()
        self._st_file = QLabel(f"Noteration v{__version__}")
        self._st_pos = QLabel("Ln 1, Col 1")
        self._st_words = QLabel("0 words")
        self._st_git = QLabel("○ offline")
        self._st_git.setStyleSheet("color:gray;")
        self._st_vault = QLabel(self.vault_path.name)
        self._st_vault.setStyleSheet("color:gray;")

        sb.addWidget(self._st_file)
        sb.addWidget(QLabel("|"))
        sb.addWidget(self._st_pos)
        sb.addWidget(QLabel("|"))
        sb.addWidget(self._st_words)
        sb.addPermanentWidget(self._st_git)
        sb.addPermanentWidget(self._st_vault)

    def _setup_autosave(self) -> None:
        interval = self.config.get("general", "autosave_interval", 30)
        if self.config.get("general", "autosave", True):
            self._autosave_timer = QTimer(self)
            self._autosave_timer.setInterval(int(interval) * 1000)
            self._autosave_timer.timeout.connect(self._save_current)
            self._autosave_timer.start()

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_note_id(self, path: Path) -> str:
        """Map absolute path -> relative ID (e.g., folder/note)."""
        try:
            rel = path.relative_to(self.vault_path / "notes")
            return str(rel.with_suffix(""))
        except ValueError:
            return path.stem

    # ── Tab management ────────────────────────────────────────────────

    def _on_note_opened_event(self, event: NoteOpenedEvent) -> None:
        """Handler for NoteOpenedEvent from EventBus."""
        self._open_note(event.note_path)
        heading = event.heading
        if heading:
            # Trigger heading jump immediately
            self._go_to_heading(heading)

    def _on_literature_selected_event(self, event: LiteratureSelectedEvent) -> None:
        """Handler for LiteratureSelectedEvent."""
        self._open_literature_by_key(event.papis_key)

    def _open_note(self, path: Path) -> None:
        # Avoid opening the same note twice across both panes
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if isinstance(w, EditorTab) and w.file_path == path:
                    pane.setCurrentIndex(i)
                    self._active_tab_widget = pane

                    # History tracking for existing tab
                    if not self._is_navigating:
                        current_w = self._active_tab_widget.currentWidget()
                        if isinstance(current_w, EditorTab) and current_w.file_path != path:
                            self._history.append(current_w.file_path)
                            self._forward_stack.clear()
                    return

        # History tracking for new tab
        if not self._is_navigating:
            current_w = self._active_tab_widget.currentWidget()
            if isinstance(current_w, EditorTab):
                self._history.append(current_w.file_path)
                self._forward_stack.clear()

        tab = EditorTab(path, self.vault)
        tab.cursor_moved.connect(self._on_cursor_moved)
        tab.content_changed.connect(lambda: self._mark_modified(tab))
        tab.wiki_link_clicked.connect(self._follow_wiki_link)
        tab.headings_changed.connect(self.sidebar.update_outline)
        tab.citations_changed.connect(self.sidebar.update_citations)
        tab.citations_changed.connect(self.sidebar.update_cited_pdfs)
        tab.word_count_changed.connect(self._on_word_count)
        tab.save_requested.connect(self._save_current)
        tab.focus_mode_exit_requested.connect(lambda: self._toggle_focus_mode(False))
        tab.view_mode_requested.connect(tab.set_view_mode)
        tab.export_requested.connect(self._execute_export)

        active_pane = self._active_tab_widget
        idx = active_pane.addTab(tab, path.name)
        active_pane.setCurrentIndex(idx)
        self._st_file.setText(path.name)

        # Apply focus mode if active
        if self._focus_mode_active:
            tab.set_focus_mode(True)

        # Initialize sidebar content from the newly opened note
        self.sidebar.update_outline(tab.headings())
        cited_keys = tab.citation_keys()
        self.sidebar.update_citations(cited_keys)
        self.sidebar.update_cited_pdfs(cited_keys)

        note_id = self._get_note_id(path)
        self._backlink_panel.set_current_note(note_id)
        if self._graph_view:
            self._graph_view.set_current_note(note_id)

    def _open_pdf(self, pdf_path: str | Path, papis_key: str = "") -> None:
        if isinstance(pdf_path, str):
            pdf_path = Path(pdf_path)
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if isinstance(w, PdfViewerTab) and w.pdf_path == pdf_path:
                    pane.setCurrentIndex(i)
                    self._active_tab_widget = pane
                    return

        tab = PdfViewerTab(pdf_path, papis_key, self.vault)
        tab.insert_quote_requested.connect(self._insert_quote_to_editor)
        tab.insert_image_requested.connect(self._insert_image_to_editor)
        tab.extract_requested.connect(lambda: self._on_extract_annotations(tab))
        tab.note_requested.connect(self._follow_wiki_link)

        # Use literature title if available, otherwise filename
        display_title = ""
        if papis_key and self.vault.papis:
            entry = self.vault.papis.get(papis_key)
            if entry and entry.title:
                display_title = entry.title

        if not display_title:
            display_title = pdf_path.name

        # Truncate title for tab display
        max_len = 30
        if len(display_title) > max_len:
            display_title = display_title[: max_len - 3] + "..."

        active_pane = self._active_tab_widget
        idx = active_pane.addTab(tab, display_title)
        active_pane.setCurrentIndex(idx)

    def _open_literature_tab(self) -> None:
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if isinstance(w, LiteratureTab):
                    pane.setCurrentIndex(i)
                    self._active_tab_widget = pane
                    w.refresh()
                    return
        tab = LiteratureTab(self.vault)
        tab.pdf_open_requested.connect(self._open_pdf)
        tab.note_create_requested.connect(self._new_note_from_lit)
        # Refresh UI when the library changes
        tab.library_changed.connect(self._refresh_all_citation_completers)
        tab.library_changed.connect(self.sidebar.refresh)

        active_pane = self._active_tab_widget
        idx = active_pane.addTab(tab, "Literature")
        active_pane.setCurrentIndex(idx)

    def _refresh_all_citation_completers(self) -> None:
        """Update citation completion data in all open EditorTabs."""
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if (
                    isinstance(w, EditorTab)
                    and hasattr(w, "_completer")
                    and w._completer is not None
                ):
                    w._completer.refresh_keys()

    def _on_extract_annotations(self, tab: PdfViewerTab) -> None:
        """Create a new Markdown note from all annotations in the PDF."""
        content = tab._doc_ann.compile_to_markdown(self.vault_path)
        if not content:
            QMessageBox.information(
                self, "No Annotations", "There are no annotations to extract from this PDF."
            )
            return

        # Propose a filename
        base_name = f"Annotations_{tab.papis_key}"
        dest_path = self.vault_path / "notes" / f"{base_name}.md"

        # Handle collision
        counter = 1
        while dest_path.exists():
            dest_path = self.vault_path / "notes" / f"{base_name}_{counter}.md"
            counter += 1

        try:
            dest_path.write_text(content, encoding="utf-8")
            self.statusBar().showMessage(f"Extracted annotations to {dest_path.name}", 3000)
            self.sidebar.add_note(dest_path)
            self._open_note(dest_path)
        except Exception as e:
            QMessageBox.critical(self, "Extraction Failed", f"Failed to save extracted note: {e}")

    def _open_sync_tab(self) -> None:
        if self.vault.git_repo is None:
            QMessageBox.information(
                self,
                "Git Active",
                "This vault has not been initialized as a Git repository.\n\n"
                "You can view its status or initialize it in the Synchronization tab.",
            )

        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                if isinstance(pane.widget(i), SyncTab):
                    pane.setCurrentIndex(i)
                    self._active_tab_widget = pane
                    return
        tab = SyncTab(self.vault)
        active_pane = self._active_tab_widget
        idx = active_pane.addTab(tab, "Synchronization")
        active_pane.setCurrentIndex(idx)

    def _close_tab_from_widget(self, tab_widget: QTabWidget, index: int) -> None:
        w = tab_widget.widget(index)
        if isinstance(w, EditorTab) and w.is_modified:
            w.save()
            self.vault.update_note_in_graph(w.file_path)
        tab_widget.removeTab(index)
        self._adjust_splitters()

    def _close_tab(self, index: int) -> None:
        self._close_tab_from_widget(self.tabs, index)

    def _on_tab_changed_for_widget(self, tab_widget: QTabWidget, index: int) -> None:
        if index < 0:
            return
        self._active_tab_widget = tab_widget
        w = tab_widget.widget(index)
        if isinstance(w, EditorTab):
            self._st_file.setText(w.file_path.name)
            note_id = self._get_note_id(w.file_path)
            self._backlink_panel.set_current_note(note_id)
            if self._graph_view:
                self._graph_view.set_current_note(note_id)

            # Update sidebar content to match the focused note
            self.sidebar.update_outline(w.headings())
            cited_keys = w.citation_keys()
            self.sidebar.update_citations(cited_keys)
            self.sidebar.update_cited_pdfs(cited_keys)

    def _on_tab_changed(self, index: int) -> None:
        self._on_tab_changed_for_widget(self.tabs, index)

    def _navigate_back(self) -> None:
        """Navigate back in history."""
        if not self._history:
            return

        current_w = self._active_tab_widget.currentWidget()
        if isinstance(current_w, EditorTab):
            self._forward_stack.append(current_w.file_path)

        prev_path = self._history.pop()
        self._is_navigating = True
        try:
            self._open_note(prev_path)
        finally:
            self._is_navigating = False

    def _navigate_forward(self) -> None:
        """Navigate forward in history."""
        if not self._forward_stack:
            return

        current_w = self._active_tab_widget.currentWidget()
        if isinstance(current_w, EditorTab):
            self._history.append(current_w.file_path)

        next_path = self._forward_stack.pop()
        self._is_navigating = True
        try:
            self._open_note(next_path)
        finally:
            self._is_navigating = False

    # ── Actions ───────────────────────────────────────────────────────

    def _open_search_dialog(self) -> None:
        """Open the global vault search dialog."""
        current = self.tabs.currentWidget()

        dlg = SearchDialog(
            self.vault_path,
            self.vault.papis,
            self.vault.core.fts,
            events=self.vault.core.events,
            parent=self,
        )
        # Annotation requested is still handled via signal for now as it's more specific to PDF viewer
        dlg.annotation_requested.connect(self._open_pdf_by_key)
        # Pre-fill query with current editor selection if available
        if isinstance(current, EditorTab):
            cursor = current._editor.textCursor()
            if cursor.hasSelection():
                selected = cursor.selectedText()
                if selected:
                    dlg.set_initial_query(selected)
        dlg.exec()

    def _open_literature_by_key(self, papis_key: str) -> None:
        """Open the literature tab and focus on a specific entry."""
        self._open_literature_tab()
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if isinstance(w, LiteratureTab):
                    w.select_entry(papis_key)
                    break

    def _open_pdf_by_key(self, papis_key: str, page: int) -> None:
        """Open the PDF viewer at a specific page."""
        if not self.vault.papis:
            return
        entry = self.vault.papis.get(papis_key)
        if entry and entry.pdf_path and entry.pdf_path.exists():
            self._open_pdf(entry.pdf_path, papis_key)
            # Navigate to the target page (page parameter is 1-indexed)
            for pane in (self.tabs, self.tabs_split):
                for i in range(pane.count()):
                    w = pane.widget(i)
                    if isinstance(w, PdfViewerTab) and w.pdf_path == entry.pdf_path:
                        w._set_page(page - 1)
                        break

    def _new_note(self) -> None:
        from noteration.dialogs.new_note import NewNoteDialog

        dlg = NewNoteDialog(self.vault_path, self)
        if dlg.exec():
            path = dlg.result_path()
            self._open_note(path)
            self.sidebar.add_note(path)

    def _save_current(self) -> None:
        active_pane = self._active_tab_widget
        w = active_pane.currentWidget()
        if isinstance(w, EditorTab) and w.is_modified:
            w.save()
            # Perform incremental graph update via the manager
            self.vault.update_note_in_graph(w.file_path)
            # Reset modified marker in tab title
            idx = active_pane.currentIndex()
            name = w.file_path.name
            if active_pane.tabText(idx).endswith(" *"):
                active_pane.setTabText(idx, name)
            self.vault.request_git_status()

    def _sync(self) -> None:
        self._open_sync_tab()

    def _follow_wiki_link(self, target: str) -> None:
        from noteration.editor.wiki_links import resolve_link

        path = resolve_link(target, self.vault_path)
        if path:
            self._open_note(path)
        else:
            reply = QMessageBox.question(
                self,
                "Note Not Found",
                f"The note '[[{target}]]' does not exist yet.\nCreate a new note?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                new_path = self.vault_path / "notes" / f"{target}.md"
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_path.write_text(f"# {target}\n\n", encoding="utf-8")
                self._open_note(new_path)
                self.sidebar.add_note(new_path)

    def _insert_quote_to_editor(self, text: str, citation_key: str, locator: str = "") -> None:
        # Prefer the currently active editor tab
        current = self._active_tab_widget.currentWidget()
        if isinstance(current, EditorTab):
            current.insert_quote(text, citation_key, locator)
            return
        # Fallback: find the most recently opened editor tab across both panes
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count() - 1, -1, -1):
                w = pane.widget(i)
                if isinstance(w, EditorTab):
                    w.insert_quote(text, citation_key, locator)
                    pane.setCurrentIndex(i)
                    self._active_tab_widget = pane
                    return

    def _insert_image_to_editor(self, image_path: str, citation_key: str, locator: str = "") -> None:
        from pathlib import Path

        img_path = Path(image_path)
        if not img_path.exists():
            return
        rel_path = img_path.relative_to(self.vault_path)
        md = f"![]({rel_path})\n\n"
        current = self._active_tab_widget.currentWidget()
        if isinstance(current, EditorTab):
            current.insert_quote(md, citation_key, locator)
            return
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count() - 1, -1, -1):
                w = pane.widget(i)
                if isinstance(w, EditorTab):
                    w.insert_quote(md, citation_key, locator)
                    pane.setCurrentIndex(i)
                    self._active_tab_widget = pane
                    return

    def _new_note_from_lit(self, papis_key: str, title: str) -> None:
        note_path = self.vault_path / "notes" / f"{papis_key}.md"
        if not note_path.exists():
            note_path.write_text(
                f"# {title}\n\nSource: @{papis_key}\n\n"
                "## Summary\n\n\n"
                "## Important Notes\n\n\n"
                "## Quotes\n\n",
                encoding="utf-8",
            )
        self._open_note(note_path)
        self.sidebar.add_note(note_path)

    def _go_to_heading(self, heading: str) -> None:
        current = self._active_tab_widget.currentWidget()
        if isinstance(current, EditorTab):
            current.go_to_heading(heading)
            return
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count() - 1, -1, -1):
                w = pane.widget(i)
                if isinstance(w, EditorTab):
                    w.go_to_heading(heading)
                    pane.setCurrentIndex(i)
                    self._active_tab_widget = pane
                    return

    def _go_to_citation(self, key: str) -> None:
        current = self._active_tab_widget.currentWidget()
        if isinstance(current, EditorTab):
            current.go_to_citation(key)
            return
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count() - 1, -1, -1):
                w = pane.widget(i)
                if isinstance(w, EditorTab):
                    w.go_to_citation(key)
                    pane.setCurrentIndex(i)
                    self._active_tab_widget = pane
                    return

    def _open_vault_dialog(self) -> None:
        from noteration.dialogs.vault_picker import VaultPickerDialog

        dlg = VaultPickerDialog(self)
        if dlg.exec():
            MainWindow(dlg.selected_vault()).show()

    def _open_settings(self) -> None:
        from noteration.dialogs.settings_dialog import SettingsDialog

        dlg = SettingsDialog(self.config, self)
        # Enable live theme preview
        dlg.theme_changed.connect(lambda t: self.theme_change_requested.emit(t))
        # Update UI without closing on 'Apply'
        dlg.settings_applied.connect(self._apply_settings_ui)

        def on_decrypt():
            from PySide6.QtWidgets import QMessageBox

            res = QMessageBox.question(
                dlg,
                "Decrypt Vault",
                "Are you sure you want to PERMANENTLY decrypt this vault?\n\n"
                "This will make all your files plaintext on disk after you close the app.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                if self.vault.permanently_decrypt():
                    # Close the vault properly
                    self.vault.shutdown()

                    # Perform the actual file decryption now
                    from noteration.core.session import VaultSession

                    session = VaultSession(self.vault.vault_path)
                    session.secret_key = self.vault.secret_key
                    # We need to decrypt files before they are 'gone'
                    session.decrypt_vault()

                    QMessageBox.information(
                        dlg,
                        "Success",
                        "Vault has been decrypted. The application will now restart "
                        "in plaintext mode.",
                    )
                    dlg.accept()

                    # Restart logic
                    import sys

                    from PySide6.QtCore import QProcess

                    QProcess.startDetached(sys.executable, sys.argv)
                    self.close()
                else:
                    QMessageBox.warning(dlg, "Error", "Failed to disable encryption.")

        dlg.decrypt_requested.connect(on_decrypt)

        if dlg.exec():
            self._apply_settings_ui()
            self.theme_change_requested.emit(dlg.selected_theme)
            self._restart_autosave()
        else:
            # Revert to original theme on cancel
            saved = self.config.get("ui", "theme", "system")
            self.theme_change_requested.emit(saved)

    def _apply_settings_ui(self) -> None:
        # Refresh configuration visibility across editor tabs
        self.vault.refresh_csl_renderer()
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if isinstance(w, EditorTab):
                    w.set_line_numbers_visible(self.config.get("editor", "show_line_numbers", True))
                    w._refresh_preview()

    def _open_encryption_dialog(self) -> None:
        """Open the vault encryption management dialog."""
        self.vault.save_all()
        dlg = EncryptionDialog(self.vault_path, self.vault.config, self)
        if dlg.exec():
            # If encryption was successful, the current files are gone/encrypted.
            # We MUST restart to start an encrypted session.
            QMessageBox.information(
                self,
                "Encryption Complete",
                "Your vault is now encrypted. The application will now restart "
                "to initialize your secure session.",
            )
            # Restart logic
            import sys

            from PySide6.QtCore import QProcess

            QProcess.startDetached(sys.executable, sys.argv)
            self.close()

    def _check_for_updates(self, silent: bool = False) -> None:
        if self._update_thread and self._update_thread.isRunning():
            return

        self._update_silent = silent
        if not silent:
            self.statusBar().showMessage("Checking for updates...")

        self._update_thread = CheckUpdateThread(self)
        self._update_thread.finished.connect(self._on_update_check_finished)
        self._update_thread.error.connect(self._on_update_check_error)
        self._update_thread.start()

    def _clear_update_thread(self) -> None:
        pass

    def _on_update_check_finished(self, available: bool, version: str) -> None:
        if available:
            # If running as binary (frozen), we point to the website/installer
            if is_frozen():
                res = QMessageBox.question(
                    self,
                    "Update Available",
                    f"A new version of Noteration (v{version}) is available.\n"
                    f"Current version is v{__version__}.\n\n"
                    "Since you are using a standalone version, would you like to "
                    "download the latest installer from our website?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if res == QMessageBox.StandardButton.Yes:
                    import webbrowser

                    url = get_latest_binary_url()
                    webbrowser.open(url)
                    QMessageBox.information(
                        self,
                        "Download Started",
                        "The latest installer has been opened in your browser.\n\n"
                        "Please close Noteration before running the installer.",
                    )
                return

            # Standard pip update for source/dev installs
            res = QMessageBox.question(
                self,
                "Update Available",
                f"A new version of Noteration (v{version}) is available.\n"
                f"Current version is v{__version__}.\n\n"
                "Would you like to update now?\n"
                "(The application will restart after the update)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                if run_update_process():
                    self.close()
                else:
                    QMessageBox.warning(
                        self, "Update Failed", "Could not initiate the update process."
                    )
        elif not self._update_silent:
            QMessageBox.information(
                self, "No Updates", f"You are using the latest version (v{__version__})."
            )

    def _on_update_check_error(self, message: str) -> None:
        if not self._update_silent:
            QMessageBox.critical(self, "Update Error", f"Failed to check for updates:\n{message}")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About Noteration",
            f"Noteration v{__version__}\n\n"
            "Research note-taking:\n"
            "Markdown · PDF + Annotations · Papis · GitHub sync\n"
            "Backlink graph · Dark mode · Citation autocomplete\n\n"
            "PySide6 · PyMuPDF · GitPython · NetworkX",
        )

    def _open_guide(self) -> None:
        from noteration.dialogs.help_dialog import HelpDialog

        dlg = HelpDialog("Noteration User Guide", "user_guide.md", self)
        dlg.exec()

    def _open_cli_guide(self) -> None:
        from noteration.dialogs.help_dialog import HelpDialog

        dlg = HelpDialog("CLI User Guide", "user_guide_cli.md", self)
        dlg.exec()

    def _open_api_guide(self) -> None:
        from noteration.dialogs.help_dialog import HelpDialog

        dlg = HelpDialog("REST API User Guide", "user_guide_api.md", self)
        dlg.exec()

    def _open_research_writing(self) -> None:
        from noteration.dialogs.help_dialog import HelpDialog

        dlg = HelpDialog("Research and Writing", "research_writing.md", self)
        dlg.exec()

    def _toggle_focus_mode(self, enabled: bool) -> None:
        self._focus_mode_active = enabled
        self._act_focus.setChecked(enabled)

        if enabled:
            self.showFullScreen()
            self.menuBar().hide()
            self.statusBar().hide()
            self._main_toolbar.hide()
            self._sidebar_dock.hide()
            self._right_dock.hide()
        else:
            self.showNormal()
            self.menuBar().show()
            self.statusBar().show()
            self._main_toolbar.show()
            self._sidebar_dock.show()
            self._right_dock.show()

        # Update all EditorTabs
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if isinstance(w, EditorTab):
                    w.set_focus_mode(enabled)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle global keys, like Esc to exit Focus Mode when no editor is focused."""
        if event.key() == Qt.Key.Key_Escape and self._focus_mode_active:
            # If no tab is open or the current tab is not an editor (so it didn't catch the key)
            current = self._active_tab_widget.currentWidget()
            total_tabs = self.tabs.count() + self.tabs_split.count()
            if total_tabs == 0 or not isinstance(current, EditorTab):
                self._toggle_focus_mode(False)
                return
        super().keyPressEvent(event)

    # ── Settings reload helpers ───────────────────────────────────────

    def _restart_autosave(self) -> None:
        if hasattr(self, "_autosave_timer"):
            self._autosave_timer.stop()
        self._setup_autosave()

    # ── BibTeX export ─────────────────────────────────────────────────

    def _export_bibtex_all(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export BibTeX",
            str(self.vault_path / "references.bib"),
            "BibTeX Files (*.bib)",
        )
        if path:
            from noteration.literature.bibtex_export import BibtexExporter

            n = BibtexExporter(self.vault.papis).export_all(Path(path))
            QMessageBox.information(self, "Export Finished", f"{n} entries → {path}")

    def _export_bibtex_note(self) -> None:
        w = self._active_tab_widget.currentWidget()
        if not isinstance(w, EditorTab):
            QMessageBox.warning(self, "No Active Editor", "Please open a Markdown note first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export BibTeX",
            str(self.vault_path / f"{w.file_path.stem}.bib"),
            "BibTeX Files (*.bib)",
        )
        if path:
            from noteration.literature.bibtex_export import BibtexExporter

            n = BibtexExporter(self.vault.papis).export_from_note(w.file_path, Path(path))
            QMessageBox.information(
                self, "Export Finished", f"{n} entries referenced in this note → {path}"
            )

    def _execute_export(self, fmt: str) -> None:
        """Perform actual export without triggering further signals."""
        w = self._active_tab_widget.currentWidget()
        if isinstance(w, EditorTab):
            # This direct call to Pandoc/Exporter avoids the recursive signal flow
            w.export_as(fmt)

    def _export_current_note_with_fmt(self, fmt: str) -> None:
        """Export the currently active note to the specified format."""
        self._export_current_note(fmt)

    def _export_current_note(self, fmt: str) -> None:
        """Export the currently active note to the specified format."""
        w = self._active_tab_widget.currentWidget()
        if isinstance(w, EditorTab):
            w.export_as(fmt)
        else:
            QMessageBox.warning(self, "No Active Editor", "Please open a Markdown note first.")

    # ── PDF + Graph background tasks ──────────────────────────────────

    def _scan_pdf_index(self) -> None:
        self.vault.scan_pdfs()

    def _build_link_graph(self) -> None:
        self.vault.build_graph(force=True)

    def _toggle_graph_view(self) -> None:
        # Navigate to the Graph tab in the right panel
        if self._graph_view:
            self._right_tabs.setCurrentIndex(1)

    # ── Status bar updates ────────────────────────────────────────────

    def _on_cursor_moved(self, line: int, col: int) -> None:
        self._st_pos.setText(f"Ln {line}, Col {col}")

    def _on_word_count(self, count: int) -> None:
        self._st_words.setText(f"{count:,} words")

    def _on_tag_clicked(self, tag: str) -> None:
        """Trigger global search for a specific tag."""
        dlg = SearchDialog(
            self.vault_path,
            self.vault.papis,
            self.vault.core.fts,
            events=self.vault.core.events,
            parent=self,
        )
        dlg.annotation_requested.connect(self._open_pdf_by_key)

        # Pre-fill query with tag
        dlg.set_initial_query(f"#{tag}")
        dlg.exec()

    def _on_indexing_finished(self, count: int) -> None:
        """Refresh UI components that depend on the search index."""
        # Update sidebar tag list
        self.sidebar.update_tags(self.vault.get_all_tags())

    def _on_note_moved(self, src: Path, dest: Path) -> None:
        """Update open tabs when a note is moved via the sidebar."""
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if isinstance(w, EditorTab):
                    try:
                        if w.file_path == src or w.file_path.is_relative_to(src):
                            rel = w.file_path.relative_to(src)
                            new_path = dest / rel
                            w.file_path = new_path
                            if w.file_path == dest:
                                pane.setTabText(i, dest.name + (" *" if w.is_modified else ""))

                            if pane == self._active_tab_widget and i == pane.currentIndex():
                                note_id = self._get_note_id(new_path)
                                self._backlink_panel.set_current_note(note_id)
                                if self._graph_view:
                                    self._graph_view.set_current_note(note_id)
                    except (ValueError, AttributeError):
                        if str(w.file_path).startswith(str(src)):
                            rel_str = str(w.file_path)[len(str(src)) :]
                            if rel_str.startswith("/"):
                                rel_str = rel_str[1:]
                            new_path = dest / rel_str
                            w.file_path = new_path
                            if pane == self._active_tab_widget and i == pane.currentIndex():
                                note_id = self._get_note_id(new_path)
                                self._backlink_panel.set_current_note(note_id)

    def _mark_modified(self, tab: EditorTab) -> None:
        for pane in (self.tabs, self.tabs_split):
            idx = pane.indexOf(tab)
            if idx >= 0:
                if not pane.tabText(idx).endswith(" *"):
                    pane.setTabText(idx, tab.file_path.name + " *")
                break

    def _on_git_status_updated(self, st: object | None) -> None:
        """Update Git status indicators based on RepoStatus from VaultManager."""
        if not hasattr(self, "vault"):
            return

        if st is None:
            self._sync_badge.setText("Git: offline")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#F5F5F5;color:#616161;font-size:11px;"
            )
            self._st_git.setText("○ offline")
            self._st_git.setStyleSheet("color:gray;")
            return

        st = cast("RepoStatus", st)
        if st.is_dirty or st.untracked:
            self._sync_badge.setText("Git: modified")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#FFF3E0;color:#E65100;font-size:11px;"
            )
            self._st_git.setText("● modified")
            self._st_git.setStyleSheet("color:#FF9800;")
        elif not st.remotes:
            self._sync_badge.setText("Git: local only")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#F5F5F5;color:#616161;font-size:11px;"
            )
            self._st_git.setText("○ local")
            self._st_git.setStyleSheet("color:gray;")
        elif st.ahead > 0 or st.behind > 0:
            status_text = f"Git: ↑{st.ahead} ↓{st.behind}"
            self._sync_badge.setText(status_text)
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#E3F2FD;color:#1565C0;font-size:11px;"
            )
            self._st_git.setText(f"● {st.ahead}↑ {st.behind}↓")
            self._st_git.setStyleSheet("color:#2196F3;")
        else:
            self._sync_badge.setText("Git: synced")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#E1F5EE;color:#0F6E56;font-size:11px;"
            )
            self._st_git.setText("● synced")
            self._st_git.setStyleSheet("color:#1D9E75;")

    # ── Split View Helpers ────────────────────────────────────────────

    def _show_tab_context_menu(self, tab_widget: QTabWidget, pos: QPoint) -> None:
        tab_bar = tab_widget.tabBar()
        index = tab_bar.tabAt(pos)
        if index < 0:
            return

        menu = QMenu(self)

        if tab_widget == self.tabs:
            act_split = QAction(
                "Open Split View" if not self.tabs_split.isVisible() else "Move to Split View", self
            )
            act_split.triggered.connect(lambda: self._move_tab(self.tabs, self.tabs_split, index))
        else:
            act_split = QAction("Move to Main View", self)
            act_split.triggered.connect(lambda: self._move_tab(self.tabs_split, self.tabs, index))

        menu.addAction(act_split)

        act_close = QAction("Close Tab", self)
        act_close.triggered.connect(lambda: self._close_tab_from_widget(tab_widget, index))
        menu.addAction(act_close)

        menu.exec(tab_bar.mapToGlobal(pos))

    def _move_tab(self, src: QTabWidget, dest: QTabWidget, index: int) -> None:
        widget = src.widget(index)
        if not widget:
            return
        title = src.tabText(index)
        icon = src.tabIcon(index)

        # Remove from source QTabWidget
        src.removeTab(index)

        # Add to destination QTabWidget
        new_idx = dest.addTab(widget, icon, title)
        dest.setCurrentIndex(new_idx)

        # Ensure destination is visible and active
        dest.show()
        self._active_tab_widget = dest

        # Adjust layouts / visibility of both split panes
        self._adjust_splitters()

        # Trigger post-move updates
        self._on_tab_changed_for_widget(dest, new_idx)

    def _adjust_splitters(self) -> None:
        # If right pane has no tabs, hide it
        if self.tabs_split.count() == 0:
            self.tabs_split.hide()
            self._active_tab_widget = self.tabs
        # If left pane (primary) has no tabs, but right pane does:
        # Move all tabs from right pane to left pane, then hide right pane.
        elif self.tabs.count() == 0 and self.tabs_split.count() > 0:
            while self.tabs_split.count() > 0:
                widget = self.tabs_split.widget(0)
                if widget is not None:
                    title = self.tabs_split.tabText(0)
                    icon = self.tabs_split.tabIcon(0)
                    self.tabs_split.removeTab(0)
                    self.tabs.addTab(widget, icon, title)
                else:
                    self.tabs_split.removeTab(0)
            self.tabs_split.hide()
            self._active_tab_widget = self.tabs

    def _connect_focus_listener(self) -> None:
        """Connect global focus changed signal (called via QTimer)."""
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.focusChanged.connect(self._on_focus_changed)
            self._focus_listener_connected = True

    def _on_focus_changed(self, old: QWidget | None, new: QWidget | None) -> None:

        # Ensure 'new' is actually a QWidget; sometimes Qt signals can pass
        # internal objects that aren't full QWidgets during complex layout changes.
        if not isinstance(new, QWidget):
            return

        p: QWidget | None = new
        while p and isinstance(p, QWidget):
            if p == self.tabs:
                self._active_tab_widget = self.tabs
                break
            elif p == self.tabs_split:
                self._active_tab_widget = self.tabs_split
                break
            p = p.parentWidget()

    # ── Close ─────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """Ensure all resources are cleaned up before closing."""
        logger.info("Main window closing...")

        # 0. Disconnect global focus listener
        if self._focus_listener_connected:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if isinstance(app, QApplication):
                try:
                    app.focusChanged.disconnect(self._on_focus_changed)
                except (TypeError, RuntimeError):
                    pass
            self._focus_listener_connected = False

        # 1. Stop update thread if running
        if self._update_thread and self._update_thread.isRunning():
            self._update_thread.quit()
            if not self._update_thread.wait(1000):
                self._update_thread.terminate()
            self._update_thread = None

        # 2. Stop tab threads (e.g., Literature loading) and save modified notes
        for pane in (self.tabs, self.tabs_split):
            for i in range(pane.count()):
                w = pane.widget(i)
                if w is not None:
                    # First save if it's an editor tab
                    from noteration.ui.editor_tab import EditorTab

                    if isinstance(w, EditorTab) and w.is_modified:
                        w.save()

                    # Then call shutdown if available
                    if hasattr(w, "shutdown"):
                        w.shutdown()

        # 3. Shutdown vault manager (stops background threads + performs final save_all)
        self.vault.shutdown()

        super().closeEvent(event)
