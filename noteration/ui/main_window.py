"""
Noteration main window.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast, TYPE_CHECKING, Optional

import shiboken6
if TYPE_CHECKING:
    from noteration.sync.git_engine import RepoStatus

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QDockWidget, QLabel, QWidget,
    QToolBar, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QAction, QKeyEvent

from noteration import __version__
from noteration.sync.updater import CheckUpdateThread, run_update_process
from noteration.ui.sidebar import SidebarWidget
from noteration.ui.editor_tab import EditorTab
from noteration.ui.pdf_viewer_tab import PdfViewerTab
from noteration.ui.literature_tab import LiteratureTab
from noteration.ui.sync_tab import SyncTab
from noteration.ui.backlink_panel import BacklinkPanel
from noteration.ui.graph_view import GraphView
from noteration.search.search_dialog import SearchDialog

from noteration.vault_manager import VaultManager


class MainWindow(QMainWindow):

    # Forwarded to app.py → apply_theme(app, mode)
    theme_change_requested = Signal(str)

    def __init__(self, vault_path: Path) -> None:
        super().__init__()
        # Initialize VaultManager (Business logic orchestrator)
        self.vault = VaultManager(vault_path, parent=self)
        
        # Shortcuts for MainWindow accessibility
        self.vault_path = self.vault.vault_path
        self.config     = self.vault.config
        self._papis     = self.vault.papis
        self._pdf_index = self.vault.pdf_index
        self._graph     = self.vault.graph
        self._git_repo  = self.vault.git_repo

        self._focus_mode_active = False
        self._update_thread: Optional[CheckUpdateThread] = None

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
        self.vault.graph_updated.connect(lambda _: self._graph_view.refresh() if self._graph_view else None)

        # Trigger background initialization tasks
        QTimer.singleShot(100,  self.vault.request_git_status)
        QTimer.singleShot(400,  self.vault.scan_pdfs)
        QTimer.singleShot(800,  self.vault.build_graph)

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

    def _setup_ui(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        # Left dock: Navigator (sidebar)
        self.sidebar = SidebarWidget(self.vault_path, self.config)
        self.sidebar.note_selected.connect(self._open_note)
        self.sidebar.pdf_selected.connect(self._open_pdf)
        self.sidebar.heading_clicked.connect(self._go_to_heading)
        self.sidebar.citation_clicked.connect(self._go_to_citation)
        self.sidebar.item_moved.connect(self._on_note_moved)

        self._sidebar_dock = QDockWidget("Navigator", self)
        self._sidebar_dock.setWidget(self.sidebar)
        self._sidebar_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._sidebar_dock.setMinimumWidth(200)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,
                           self._sidebar_dock)

        # Apply sidebar visibility from configuration
        show_sidebar = self.config.get("ui", "sidebar_visible", True)
        if not show_sidebar:
            self._sidebar_dock.hide()

        # Right dock: Tabbed (Backlinks + Graph)
        self._backlink_panel = BacklinkPanel(self._graph)
        self._backlink_panel.note_requested.connect(self._follow_wiki_link)
        self._backlink_panel.rebuild_requested.connect(self._build_link_graph)

        self._graph_view = GraphView(self._graph, self.vault_path)
        self._graph_view.node_clicked.connect(self._follow_wiki_link)

        self._right_tabs = QTabWidget()
        self._right_tabs.addTab(self._backlink_panel, "Backlinks")
        self._right_tabs.addTab(self._graph_view, "Graph")

        self._right_dock = QDockWidget("Link Graph", self)
        self._right_dock.setWidget(self._right_tabs)
        self._right_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._right_dock.setMinimumWidth(250)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self._right_dock)
        
        # Apply sidebar visibility to the right dock as well
        if not show_sidebar:
            self._right_dock.hide()

    def _setup_menu(self) -> None:
        mb = self.menuBar()

        # File Menu
        fm = mb.addMenu("&File")
        fm.addAction(self._act_new)
        fm.addAction("Open Vault…",   self._open_vault_dialog)
        fm.addSeparator()
        fm.addAction(self._act_save)
        fm.addSeparator()
        fm.addAction("Exit",        self.close,
                     QKeySequence.StandardKey.Quit)

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
        vm.addAction("Literature",     self._open_literature_tab)
        vm.addAction("Synchronization",  self._open_sync_tab)

        # Search Action
        search_action = QAction("&Search", self)
        search_action.triggered.connect(self._open_search_dialog)
        search_action.setShortcut(QKeySequence.StandardKey.Find)
        mb.addAction(search_action)

        # Tools Menu
        tm = mb.addMenu("&Tools")
        tm.addAction("Sync Now", self._sync, "Ctrl+Shift+S")
        tm.addSeparator()
        tm.addAction("Export BibTeX (all)…",    self._export_bibtex_all)
        tm.addAction("Export BibTeX (this note)…", self._export_bibtex_note)
        tm.addSeparator()
        tm.addAction("Rebuild Backlink Graph", self._build_link_graph)
        tm.addAction("Scan PDF Index",             self._scan_pdf_index)
        tm.addSeparator()
        tm.addAction("Settings…",               self._open_settings,
                     QKeySequence.StandardKey.Preferences)

        hm = mb.addMenu("&Help")
        hm.addAction("Check for Updates", lambda: self._check_for_updates(silent=False))
        hm.addAction("Guide", self._open_guide, QKeySequence.StandardKey.HelpContents)
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
        self._main_toolbar.addAction("Literature",  self._open_literature_tab)
        self._main_toolbar.addAction("Sync",       self._sync)
        self._main_toolbar.addSeparator()
        self._main_toolbar.addAction("Navigator",  self._sidebar_dock.toggleViewAction().trigger)
        self._main_toolbar.addAction("Link Graph",  self._right_dock.toggleViewAction().trigger)

        sp = QWidget()
        sp.setMinimumWidth(8)
        self._main_toolbar.addWidget(sp)

        self._sync_badge = QLabel("Git: offline")
        self._sync_badge.setStyleSheet(
            "padding:2px 8px;border-radius:8px;"
            "background:#F5F5F5;color:#616161;font-size:11px;")
        self._main_toolbar.addWidget(self._sync_badge)

    def _setup_statusbar(self) -> None:
        sb = self.statusBar()
        self._st_file  = QLabel(f"Noteration v{__version__}")
        self._st_pos   = QLabel("Ln 1, Col 1")
        self._st_words = QLabel("0 words")
        self._st_git   = QLabel("○ offline")
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

    def _open_note(self, path: Path) -> None:
        # Avoid opening the same note twice
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab) and w.file_path == path:
                self.tabs.setCurrentIndex(i)
                return

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

        idx = self.tabs.addTab(tab, path.name)
        self.tabs.setCurrentIndex(idx)
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
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, PdfViewerTab) and w.pdf_path == pdf_path:
                self.tabs.setCurrentIndex(i)
                return

        tab = PdfViewerTab(pdf_path, papis_key, self.vault)
        tab.insert_quote_requested.connect(self._insert_quote_to_editor)
        tab.insert_image_requested.connect(self._insert_image_to_editor)
        title = pdf_path.name[:40] + "..." if len(pdf_path.name) > 40 else pdf_path.name
        idx = self.tabs.addTab(tab, title)
        self.tabs.setCurrentIndex(idx)

    def _open_literature_tab(self) -> None:
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, LiteratureTab):
                self.tabs.setCurrentIndex(i)
                w.refresh()
                return
        tab = LiteratureTab(self.vault)
        tab.pdf_open_requested.connect(self._open_pdf)
        tab.note_create_requested.connect(self._new_note_from_lit)
        # Refresh UI when the library changes
        tab.library_changed.connect(self._refresh_all_citation_completers)
        tab.library_changed.connect(self.sidebar.refresh)
        idx = self.tabs.addTab(tab, "Literature")
        self.tabs.setCurrentIndex(idx)

    def _refresh_all_citation_completers(self) -> None:
        """Update citation completion data in all open EditorTabs."""
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab) and hasattr(w, "_completer") \
                    and w._completer is not None:
                w._completer.refresh_keys()

    def _open_sync_tab(self) -> None:
        if self.vault.git_repo is None:
            QMessageBox.information(
                self, "Git Inactive",
                "This vault has not been initialized as a Git repository.\n\n"
                "You can view its status or initialize it in the Synchronization tab."
            )

        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), SyncTab):
                self.tabs.setCurrentIndex(i)
                return
        tab = SyncTab(self.vault)
        idx = self.tabs.addTab(tab, "Synchronization")
        self.tabs.setCurrentIndex(idx)

    def _open_pdf_view_tab(self) -> None:
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), PdfViewerTab):
                self.tabs.setCurrentIndex(i)
                return
        lit_dir = self.config.papis_library
        if not lit_dir.exists():
            return
        pdf_files = list(lit_dir.glob("*.pdf"))
        if pdf_files:
            self._open_pdf(pdf_files[0], papis_key="")

    def _close_tab(self, index: int) -> None:
        w = self.tabs.widget(index)
        if isinstance(w, EditorTab) and w.is_modified:
            w.save()
            self.vault.update_note_in_graph(w.file_path)
        self.tabs.removeTab(index)

    def _on_tab_changed(self, index: int) -> None:
        """Synchronize sidebar and backlink panels with the active tab."""
        w = self.tabs.widget(index)
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

    # ── Actions ───────────────────────────────────────────────────────

    def _open_search_dialog(self) -> None:
        """Open the global vault search dialog."""
        current = self.tabs.currentWidget()

        dlg = SearchDialog(self.vault_path, self._papis, self)
        dlg.note_requested.connect(self._open_note)
        dlg.literature_requested.connect(self._open_literature_by_key)
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
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, LiteratureTab):
                w.select_entry(papis_key)
                break

    def _open_pdf_by_key(self, papis_key: str, page: int) -> None:
        """Open the PDF viewer at a specific page."""
        if not self._papis:
            return
        entry = self._papis.get(papis_key)
        if entry and entry.pdf_path and entry.pdf_path.exists():
            self._open_pdf(entry.pdf_path, papis_key)
            # Navigate to the target page (page parameter is 1-indexed)
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
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
        w = self.tabs.currentWidget()
        if isinstance(w, EditorTab):
            w.save()
            # Perform incremental graph update via the manager
            self.vault.update_note_in_graph(w.file_path)
            # Reset modified marker in tab title
            idx = self.tabs.currentIndex()
            name = w.file_path.name
            if self.tabs.tabText(idx).endswith(" *"):
                self.tabs.setTabText(idx, name)
            self.vault.request_git_status()

    def _sync(self) -> None:
        if self.vault.git_repo is None:
            self._open_sync_tab()
            return

        self._open_sync_tab()
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, SyncTab):
                w.start_sync()
                break

    def _follow_wiki_link(self, target: str) -> None:
        from noteration.editor.wiki_links import resolve_link
        path = resolve_link(target, self.vault_path)
        if path:
            self._open_note(path)
        else:
            reply = QMessageBox.question(
                self, "Note Not Found",
                f"The note '[[{target}]]' does not exist yet.\nCreate a new note?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                new_path = self.vault_path / "notes" / f"{target}.md"
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_path.write_text(f"# {target}\n\n", encoding="utf-8")
                self._open_note(new_path)
                self.sidebar.add_note(new_path)

    def _insert_quote_to_editor(self, text: str, citation_key: str) -> None:
        # Prefer the currently active editor tab
        current = self.tabs.currentWidget()
        if isinstance(current, EditorTab):
            current.insert_quote(text, citation_key)
            return
        # Fallback: find the most recently opened editor tab
        for i in range(self.tabs.count() - 1, -1, -1):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                w.insert_quote(text, citation_key)
                self.tabs.setCurrentIndex(i)
                return

    def _insert_image_to_editor(self, image_path: str, citation_key: str) -> None:
        from pathlib import Path
        img_path = Path(image_path)
        if not img_path.exists():
            return
        rel_path = img_path.relative_to(self.vault_path)
        md = f"![]({rel_path})\n\n"
        current = self.tabs.currentWidget()
        if isinstance(current, EditorTab):
            current.insert_quote(md, citation_key)
            return
        for i in range(self.tabs.count() - 1, -1, -1):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                w.insert_quote(md, citation_key)
                self.tabs.setCurrentIndex(i)
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
        current = self.tabs.currentWidget()
        if isinstance(current, EditorTab):
            current.go_to_heading(heading)
            return
        for i in range(self.tabs.count() - 1, -1, -1):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                w.go_to_heading(heading)
                self.tabs.setCurrentIndex(i)
                return

    def _go_to_citation(self, key: str) -> None:
        current = self.tabs.currentWidget()
        if isinstance(current, EditorTab):
            current.go_to_citation(key)
            return
        for i in range(self.tabs.count() - 1, -1, -1):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                w.go_to_citation(key)
                self.tabs.setCurrentIndex(i)
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
        dlg.theme_changed.connect(
            lambda t: self.theme_change_requested.emit(t))
        # Update UI without closing on 'Apply'
        dlg.settings_applied.connect(self._apply_settings_ui)
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
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                w.set_line_numbers_visible(
                    self.config.get("editor", "show_line_numbers", True))

    def _check_for_updates(self, silent: bool = False) -> None:
        if self._update_thread and shiboken6.isValid(self._update_thread) and self._update_thread.isRunning():
            return

        self._update_silent = silent
        if not silent:
            self.statusBar().showMessage("Checking for updates...")

        self._update_thread = CheckUpdateThread(self)
        self._update_thread.finished.connect(self._on_update_check_finished)
        self._update_thread.error.connect(self._on_update_check_error)
        self._update_thread.finished.connect(self._clear_update_thread)
        self._update_thread.start()

    def _clear_update_thread(self) -> None:
        self._update_thread = None

    def _on_update_check_finished(self, available: bool, version: str) -> None:
        if available:
            res = QMessageBox.question(
                self, "Update Available",
                f"A new version of Noteration (v{version}) is available.\n"
                f"Current version is v{__version__}.\n\n"
                "Would you like to update now?\n"
                "(The application will restart after the update)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if res == QMessageBox.StandardButton.Yes:
                if run_update_process():
                    QTimer.singleShot(500, self.close)
                else:
                    QMessageBox.warning(self, "Update Failed", "Could not initiate the update process.")
        elif not self._update_silent:
            QMessageBox.information(self, "No Updates", f"You are using the latest version (v{__version__}).")

    def _on_update_check_error(self, message: str) -> None:
        if not self._update_silent:
            QMessageBox.critical(self, "Update Error", f"Failed to check for updates:\n{message}")

    def _about(self) -> None:
        QMessageBox.about(
            self, "About Noteration",
            f"Noteration v{__version__}\n\n"
            "Research note-taking:\n"
            "Markdown · PDF + Annotations · Papis · GitHub sync\n"
            "Backlink graph · Dark mode · Citation autocomplete\n\n"
            "PySide6 · PyMuPDF · GitPython · NetworkX"
        )

    def _open_guide(self) -> None:
        from noteration.dialogs.help_dialog import HelpDialog
        dlg = HelpDialog("Noteration User Guide", "user_guide.md", self)
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
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                w.set_focus_mode(enabled)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle global keys, like Esc to exit Focus Mode when no editor is focused."""
        if event.key() == Qt.Key.Key_Escape and self._focus_mode_active:
            # If no tab is open or the current tab is not an editor (so it didn't catch the key)
            if self.tabs.count() == 0 or not isinstance(self.tabs.currentWidget(), EditorTab):
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
            self, "Export BibTeX",
            str(self.vault_path / "references.bib"),
            "BibTeX Files (*.bib)",
        )
        if path:
            from noteration.literature.bibtex_export import BibtexExporter
            n = BibtexExporter(self._papis).export_all(Path(path))
            QMessageBox.information(
                self, "Export Finished", f"{n} entries → {path}")

    def _export_bibtex_note(self) -> None:
        w = self.tabs.currentWidget()
        if not isinstance(w, EditorTab):
            QMessageBox.warning(self, "No Active Editor",
                                "Please open a Markdown note first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export BibTeX",
            str(self.vault_path / f"{w.file_path.stem}.bib"),
            "BibTeX Files (*.bib)",
        )
        if path:
            from noteration.literature.bibtex_export import BibtexExporter
            n = BibtexExporter(self._papis).export_from_note(
                w.file_path, Path(path))
            QMessageBox.information(
                self, "Export Finished",
                f"{n} entries referenced in this note → {path}")

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

    def _on_note_moved(self, src: Path, dest: Path) -> None:
        """Update open tabs when a note is moved via the sidebar."""
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                try:
                    if w.file_path == src or w.file_path.is_relative_to(src):
                        rel = w.file_path.relative_to(src)
                        new_path = dest / rel
                        w.file_path = new_path
                        if w.file_path == dest:
                            self.tabs.setTabText(i, dest.name + (" *" if w.is_modified else ""))
                        
                        if i == self.tabs.currentIndex():
                            note_id = self._get_note_id(new_path)
                            self._backlink_panel.set_current_note(note_id)
                            if self._graph_view:
                                self._graph_view.set_current_note(note_id)
                except (ValueError, AttributeError):
                    if str(w.file_path).startswith(str(src)):
                        rel_str = str(w.file_path)[len(str(src)):]
                        if rel_str.startswith("/"):
                            rel_str = rel_str[1:]
                        new_path = dest / rel_str
                        w.file_path = new_path
                        if i == self.tabs.currentIndex():
                            note_id = self._get_note_id(new_path)
                            self._backlink_panel.set_current_note(note_id)

    def _mark_modified(self, tab: EditorTab) -> None:
        idx = self.tabs.indexOf(tab)
        if idx >= 0 and not self.tabs.tabText(idx).endswith(" *"):
            self.tabs.setTabText(idx, tab.file_path.name + " *")
        self.vault.request_git_status()

    def _on_git_status_updated(self, st: object | None) -> None:
        """Update Git status indicators based on RepoStatus from VaultManager."""
        if st is None:
            self._sync_badge.setText("Git: offline")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#F5F5F5;color:#616161;font-size:11px;")
            self._st_git.setText("○ offline")
            self._st_git.setStyleSheet("color:gray;")
            return

        st = cast("RepoStatus", st)
        if st.is_dirty or st.untracked:
            self._sync_badge.setText("Git: modified")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#FFF3E0;color:#E65100;font-size:11px;")
            self._st_git.setText("● modified")
            self._st_git.setStyleSheet("color:#FF9800;")
        elif not st.remotes:
            self._sync_badge.setText("Git: local only")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#F5F5F5;color:#616161;font-size:11px;")
            self._st_git.setText("○ local")
            self._st_git.setStyleSheet("color:gray;")
        elif st.ahead > 0 or st.behind > 0:
            status_text = f"Git: ↑{st.ahead} ↓{st.behind}"
            self._sync_badge.setText(status_text)
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#E3F2FD;color:#1565C0;font-size:11px;")
            self._st_git.setText(f"● {st.ahead}↑ {st.behind}↓")
            self._st_git.setStyleSheet("color:#2196F3;")
        else:
            self._sync_badge.setText("Git: synced")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#E1F5EE;color:#0F6E56;font-size:11px;")
            self._st_git.setText("● synced")
            self._st_git.setStyleSheet("color:#1D9E75;")

    # ── Close ─────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        # Ensure all unsaved changes are committed
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab) and w.is_modified:
                w.save()
        # Persist engine state via the manager
        self.vault.save_all()
        super().closeEvent(event)
