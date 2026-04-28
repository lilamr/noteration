"""
Noteration main window.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QDockWidget, QLabel, QWidget,
    QToolBar, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QAction

from noteration.config import NoterationConfig
from noteration.ui.sidebar import SidebarWidget
from noteration.ui.editor_tab import EditorTab
from noteration.ui.pdf_viewer_tab import PdfViewerTab
from noteration.ui.literature_tab import LiteratureTab
from noteration.ui.sync_tab import SyncTab
from noteration.ui.backlink_panel import BacklinkPanel
from noteration.ui.graph_view import GraphView
from noteration.literature.papis_bridge import PapisBridge
from noteration.pdf.pdf_index import PdfIndex
from noteration.db.link_graph import LinkGraph
from noteration.sync.git_engine import GitRepo
from noteration.search.search_dialog import SearchDialog


class MainWindow(QMainWindow):

    # Diteruskan ke app.py → apply_theme(app, mode)
    theme_change_requested = Signal(str)

    def __init__(self, vault_path: Path) -> None:
        super().__init__()
        self.vault_path = vault_path
        self.config     = NoterationConfig(vault_path)
        self._papis     = PapisBridge(self.config.papis_library)
        self._pdf_index = PdfIndex(vault_path)
        self._graph     = LinkGraph(vault_path)
        self._git_repo  = GitRepo(vault_path) if (vault_path / ".git").exists() else None

        # Graph view (created after graph loads)
        self._graph_view: GraphView | None = None
        self._graph_dock: QDockWidget | None = None
        self._graph_view_action = None

        self.setWindowTitle(f"Noteration v1.0.0 — {vault_path.name}")
        self.resize(1360, 840)
        self.setMinimumSize(900, 560)

        self._setup_statusbar()
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_autosave()
        self._setup_auto_sync()

        # Background tasks after UI ready
        QTimer.singleShot(100,  self._update_git_status)
        QTimer.singleShot(400,  self._scan_pdf_index)
        QTimer.singleShot(800,  self._build_link_graph_initial)

    # ── UI construction ───────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        # Left dock: Navigator (sidebar) - must create before opening note
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

        # Apply sidebar visibility from config
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
        # Apply sidebar visibility from config to right dock too
        if not show_sidebar:
            self._right_dock.hide()

    def _setup_menu(self) -> None:
        mb = self.menuBar()

        # File
        fm = mb.addMenu("&File")
        fm.addAction("Catatan Baru",  self._new_note,
                     QKeySequence.StandardKey.New)
        fm.addAction("Buka Vault…",   self._open_vault_dialog)
        fm.addSeparator()
        fm.addAction("Simpan",        self._save_current,
                     QKeySequence.StandardKey.Save)
        fm.addSeparator()
        fm.addAction("Keluar",        self.close,
                     QKeySequence.StandardKey.Quit)

        # View
        vm = mb.addMenu("&View")
        vm.addAction(self._sidebar_dock.toggleViewAction())
        vm.addAction(self._right_dock.toggleViewAction())
        vm.addSeparator()
        vm.addAction("Literatur",     self._open_literature_tab)
        vm.addAction("Sinkronisasi",  self._open_sync_tab)

        # Cari (Search)
        search_action = QAction("&Cari", self)
        search_action.triggered.connect(self._open_search_dialog)
        search_action.setShortcut(QKeySequence.StandardKey.Find)
        mb.addAction(search_action)

        # Tools
        tm = mb.addMenu("&Tools")
        tm.addAction("Sinkronisasi Sekarang", self._sync, "Ctrl+Shift+S")
        tm.addSeparator()
        tm.addAction("Export BibTeX (semua)…",    self._export_bibtex_all)
        tm.addAction("Export BibTeX (note ini)…", self._export_bibtex_note)
        tm.addSeparator()
        tm.addAction("Bangun Ulang Graf Backlink", self._build_link_graph)
        tm.addAction("Scan PDF Index",             self._scan_pdf_index)
        tm.addSeparator()
        tm.addAction("Pengaturan…",               self._open_settings,
                     QKeySequence.StandardKey.Preferences)

        # Help
        hm = mb.addMenu("&Help")
        hm.addAction("Panduan", self._open_guide, QKeySequence.StandardKey.HelpContents)
        hm.addSeparator()
        hm.addAction("Tentang Noteration", self._about)

    def _setup_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(tb)

        tb.addAction("+ Catatan",  self._new_note)
        tb.addSeparator()
        tb.addAction("Simpan",     self._save_current)
        tb.addAction("Literatur",  self._open_literature_tab)
        tb.addAction("Sync",       self._sync)
        tb.addSeparator()
        tb.addAction("Navigator",  self._sidebar_dock.toggleViewAction().trigger)
        tb.addAction("Link Graph",  self._right_dock.toggleViewAction().trigger)

        sp = QWidget()
        sp.setMinimumWidth(8)
        tb.addWidget(sp)

        self._sync_badge = QLabel("Git: offline")
        self._sync_badge.setStyleSheet(
            "padding:2px 8px;border-radius:8px;"
            "background:#F5F5F5;color:#616161;font-size:11px;")
        tb.addWidget(self._sync_badge)

    def _setup_statusbar(self) -> None:
        sb = self.statusBar()
        self._st_file  = QLabel("Noteration v1.0.0")
        self._st_pos   = QLabel("Bln 1, Kol 1")
        self._st_words = QLabel("0 kata")
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

    def _setup_auto_sync(self) -> None:
        if not self.config.get("sync", "auto_sync", True):
            return
        interval = int(self.config.get("sync", "sync_interval", 300))
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(interval * 1000)
        self._sync_timer.timeout.connect(self._background_sync)
        self._sync_timer.start()

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_note_id(self, path: Path) -> str:
        """Absolute path -> relative ID (e.g. folder/note)."""
        try:
            rel = path.relative_to(self.vault_path / "notes")
            return str(rel.with_suffix(""))
        except ValueError:
            return path.stem

    # ── Tab management ────────────────────────────────────────────────

    def _open_note(self, path: Path) -> None:
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab) and w.file_path == path:
                self.tabs.setCurrentIndex(i)
                return

        tab = EditorTab(path, self.vault_path, self.config,
                        papis_bridge=self._papis)
        tab.cursor_moved.connect(self._on_cursor_moved)
        tab.content_changed.connect(lambda: self._mark_modified(tab))
        tab.wiki_link_clicked.connect(self._follow_wiki_link)
        tab.headings_changed.connect(self.sidebar.update_outline)
        tab.citations_changed.connect(self.sidebar.update_citations)
        tab.citations_changed.connect(self.sidebar.update_cited_pdfs)
        tab.word_count_changed.connect(self._on_word_count)

        idx = self.tabs.addTab(tab, path.name)
        self.tabs.setCurrentIndex(idx)
        self._st_file.setText(path.name)
        
        # Inisialisasi data sidebar dari note yang baru dibuka
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

        tab = PdfViewerTab(pdf_path, papis_key,
                           self.vault_path, self.config)
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
        tab = LiteratureTab(self.vault_path, self.config)
        tab.pdf_open_requested.connect(self._open_pdf)
        tab.note_create_requested.connect(self._new_note_from_lit)
        # Saat dokumen baru ditambahkan atau metadata berubah, refresh UI
        tab.library_changed.connect(self._refresh_all_citation_completers)
        tab.library_changed.connect(self.sidebar.refresh)
        idx = self.tabs.addTab(tab, "Literatur")
        self.tabs.setCurrentIndex(idx)

    def _refresh_all_citation_completers(self) -> None:
        """Refresh CitationCompleter di setiap EditorTab yang terbuka."""
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab) and hasattr(w, "_completer") \
                    and w._completer is not None:
                w._completer.refresh_keys()

    def _open_sync_tab(self) -> None:
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), SyncTab):
                self.tabs.setCurrentIndex(i)
                return
        tab = SyncTab(self.vault_path, self.config)
        idx = self.tabs.addTab(tab, "Sinkronisasi")
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
            self._graph.update_note(w.file_path)
        self.tabs.removeTab(index)

    def _on_tab_changed(self, index: int) -> None:
        """Update sidebar dan backlink panel saat tab aktif berubah."""
        w = self.tabs.widget(index)
        if isinstance(w, EditorTab):
            self._st_file.setText(w.file_path.name)
            note_id = self._get_note_id(w.file_path)
            self._backlink_panel.set_current_note(note_id)
            if self._graph_view:
                self._graph_view.set_current_note(note_id)
            
            # Update data di sidebar agar sinkron dengan note yang baru difokus
            self.sidebar.update_outline(w.headings())
            cited_keys = w.citation_keys()
            self.sidebar.update_citations(cited_keys)
            self.sidebar.update_cited_pdfs(cited_keys)

    # ── Actions ───────────────────────────────────────────────────────

    def _open_search_dialog(self) -> None:
        """Buka dialog pencarian global."""
        current = self.tabs.currentWidget()

        dlg = SearchDialog(self.vault_path, self._papis, self)
        dlg.note_requested.connect(self._open_note)
        dlg.literature_requested.connect(self._open_literature_by_key)
        dlg.annotation_requested.connect(self._open_pdf_by_key)
        # Pre-fill dengan teks terpilih di editor (jika ada)
        if isinstance(current, EditorTab):
            cursor = current._editor.textCursor()
            if cursor.hasSelection():
                selected = cursor.selectedText()
                if selected:
                    dlg.set_initial_query(selected)
        dlg.exec()

    def _open_literature_by_key(self, papis_key: str) -> None:
        """Buka tab literatur dan pilih entry dengan key tertentu."""
        self._open_literature_tab()
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, LiteratureTab):
                w.select_entry(papis_key)
                break

    def _open_pdf_by_key(self, papis_key: str, page: int) -> None:
        """Buka PDF viewer di halaman tertentu."""
        if not self._papis:
            return
        entry = self._papis.get(papis_key)
        if entry and entry.pdf_path and entry.pdf_path.exists():
            self._open_pdf(entry.pdf_path, papis_key)
            # Navigasi ke halaman (0-indexed)
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if isinstance(w, PdfViewerTab) and w.pdf_path == entry.pdf_path:
                    w._set_page(page - 1)  # page parameter is 1-indexed
                    break

    def _new_note(self) -> None:
        from noteration.dialogs.new_note import NewNoteDialog
        dlg = NewNoteDialog(self.vault_path, self)
        if dlg.exec():
            path = dlg.result_path()
            self._open_note(path)
            self.sidebar.refresh()

    def _save_current(self) -> None:
        w = self.tabs.currentWidget()
        if isinstance(w, EditorTab):
            w.save()
            # Update graf incremental
            self._graph.update_note(w.file_path)
            self._backlink_panel.refresh_all()
            # Clear modified marker
            idx = self.tabs.currentIndex()
            name = w.file_path.name
            if self.tabs.tabText(idx).endswith(" *"):
                self.tabs.setTabText(idx, name)
            self._update_git_status()

    def _sync(self) -> None:
        self._open_sync_tab()
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, SyncTab):
                w.start_sync()
                break

    def _background_sync(self) -> None:
        """Sync otomatis tanpa membuka tab sync."""
        from noteration.sync.git_engine import GitRepo
        repo = GitRepo(self.vault_path)
        if not repo.is_valid:
            return
        st = repo.status()
        if not st.is_dirty or not st.remotes:
            return
        # Jalankan di background thread tanpa UI
        from PySide6.QtCore import QThread, QObject
        class _QuietWorker(QObject):
            done = Signal()
            def run(self) -> None:
                repo.sync(log_callback=lambda _: None)
                self.done.emit()

        self._bg_thread = QThread()
        self._bg_worker = _QuietWorker()
        self._bg_worker.moveToThread(self._bg_thread)
        self._bg_worker.done.connect(lambda: self._bg_thread.quit())
        self._bg_worker.done.connect(lambda: self._sync_badge.setText("Git: synced"))
        self._bg_thread.started.connect(self._bg_worker.run)
        self._sync_badge.setText("Git: syncing…")
        self._bg_thread.start()

    def _follow_wiki_link(self, target: str) -> None:
        from noteration.editor.wiki_links import resolve_link
        path = resolve_link(target, self.vault_path)
        if path:
            self._open_note(path)
        else:
            reply = QMessageBox.question(
                self, "Note Tidak Ditemukan",
                f"Note '[[{target}]]' belum ada.\nBuat catatan baru?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                new_path = self.vault_path / "notes" / f"{target}.md"
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_path.write_text(f"# {target}\n\n", encoding="utf-8")
                self._open_note(new_path)
                self.sidebar.refresh()

    def _insert_quote_to_editor(self, text: str, citation_key: str) -> None:
        # Prioritaskan tab editor yang sedang aktif
        current = self.tabs.currentWidget()
        if isinstance(current, EditorTab):
            current.insert_quote(text, citation_key)
            return
        # Fallback: editor tab paling kanan (paling baru dibuka)
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
                f"# {title}\n\nSumber: @{papis_key}\n\n"
                "## Ringkasan\n\n\n"
                "## Catatan Penting\n\n\n"
                "## Kutipan\n\n",
                encoding="utf-8",
            )
        self._open_note(note_path)

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
        # Live theme preview saat user mengubah combo
        dlg.theme_changed.connect(
            lambda t: self.theme_change_requested.emit(t))
        # Apply button: apply settings without closing dialog
        dlg.settings_applied.connect(self._apply_settings_ui)
        if dlg.exec():
            # OK clicked — apply settings
            self._apply_settings_ui()
            self.theme_change_requested.emit(dlg.selected_theme)
            self._restart_autosave()
            self._restart_auto_sync()
        else:
            # User cancel: kembalikan ke tema yang disimpan
            saved = self.config.get("ui", "theme", "system")
            self.theme_change_requested.emit(saved)

    def _apply_settings_ui(self) -> None:
        # Refresh line numbers visibility on all editor tabs
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                w.set_line_numbers_visible(
                    self.config.get("editor", "show_line_numbers", True))

    def _about(self) -> None:
        QMessageBox.about(
            self, "Tentang Noteration",
            "Noteration v1.0.0\n\n"
            "Research note-taking:\n"
            "Markdown · PDF + Anotasi · Papis · GitHub sync\n"
            "Backlink graph · Dark mode · Citation autocomplete\n\n"
            "PySide6 · PyMuPDF · GitPython · NetworkX"
        )

    def _open_guide(self) -> None:
        from noteration.dialogs.help_dialog import HelpDialog
        dlg = HelpDialog(self)
        dlg.exec()

    # ── Settings reload helpers ───────────────────────────────────────

    def _restart_autosave(self) -> None:
        if hasattr(self, "_autosave_timer"):
            self._autosave_timer.stop()
        self._setup_autosave()

    def _restart_auto_sync(self) -> None:
        if hasattr(self, "_sync_timer"):
            self._sync_timer.stop()
        self._setup_auto_sync()

    # ── BibTeX export ─────────────────────────────────────────────────

    def _export_bibtex_all(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export BibTeX",
            str(self.vault_path / "references.bib"),
            "BibTeX Files (*.bib)",
        )
        if path:
            from noteration.literature.bibtex_export import BibTeXExporter
            n = BibTeXExporter(self._papis).export_all(Path(path))
            QMessageBox.information(
                self, "Export Selesai", f"{n} entri → {path}")

    def _export_bibtex_note(self) -> None:
        w = self.tabs.currentWidget()
        if not isinstance(w, EditorTab):
            QMessageBox.warning(self, "Tidak Ada Editor",
                                "Buka note Markdown terlebih dahulu.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export BibTeX",
            str(self.vault_path / f"{w.file_path.stem}.bib"),
            "BibTeX Files (*.bib)",
        )
        if path:
            from noteration.literature.bibtex_export import BibTeXExporter
            n = BibTeXExporter(self._papis).export_from_note(
                w.file_path, Path(path))
            QMessageBox.information(
                self, "Export Selesai",
                f"{n} entri yang direferensi di note ini → {path}")

    # ── PDF + Graph background tasks ──────────────────────────────────

    def _scan_pdf_index(self) -> None:
        count = self._pdf_index.scan_vault(self.config.papis_library)
        if count:
            self.statusBar().showMessage(
                f"PDF index: {count} file baru terindeks.", 3000)

    def _build_link_graph_initial(self) -> None:
        # Initial load - use cache if available
        if not self._graph.load():
            count = self._graph.build_from_vault()
            self.statusBar().showMessage(
                f"Graf backlink: {count} link ditemukan.", 3000)
        self._backlink_panel.refresh_all()
        if self._graph_view:
            self._graph_view.refresh()

    def _build_link_graph(self) -> None:
        # Always rebuild from vault (force rebuild)
        count = self._graph.build_from_vault()
        self.statusBar().showMessage(
            f"Graf backlink: {count} link ditemukan.", 3000)
        self._backlink_panel.refresh_all()

        # Refresh graph view
        if self._graph_view:
            self._graph_view.refresh()

    def _toggle_graph_view(self) -> None:
        # Switch to Graph tab in right panel
        if self._graph_view:
            self._right_tabs.setCurrentIndex(1)

    # ── Status bar updates ────────────────────────────────────────────

    def _on_cursor_moved(self, line: int, col: int) -> None:
        self._st_pos.setText(f"Bln {line}, Kol {col}")

    def _on_word_count(self, count: int) -> None:
        self._st_words.setText(f"{count:,} kata")

    def _on_note_moved(self, src: Path, dest: Path) -> None:
        """Dipanggil saat note dipindahkan via drag-drop di sidebar."""
        # Jika file yang dipindahkan sedang dibuka di tab, perbarui path-nya
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab):
                # Periksa apakah file ini atau berada di dalam folder yang dipindahkan
                try:
                    if w.file_path == src or w.file_path.is_relative_to(src):
                        # Hitung path baru
                        rel = w.file_path.relative_to(src)
                        new_path = dest / rel
                        w.file_path = new_path
                        # Update judul tab jika perlu
                        if w.file_path == dest:
                            self.tabs.setTabText(i, dest.name + (" *" if w.is_modified else ""))
                        
                        # Update note_id di panel jika ini tab aktif
                        if i == self.tabs.currentIndex():
                            note_id = self._get_note_id(new_path)
                            self._backlink_panel.set_current_note(note_id)
                            if self._graph_view:
                                self._graph_view.set_current_note(note_id)
                except (ValueError, AttributeError):
                    # is_relative_to fallback or if not related
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
        self._update_git_status()

    def _update_git_status(self) -> None:
        if not self._git_repo or not self._git_repo.is_valid:
            self._sync_badge.setText("Git: offline")
            self._sync_badge.setStyleSheet(
                "padding:2px 8px;border-radius:8px;background:#F5F5F5;color:#616161;font-size:11px;")
            self._st_git.setText("○ offline")
            self._st_git.setStyleSheet("color:gray;")
            return
        st = self._git_repo.status()
        
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
        # Simpan semua editor yang belum tersimpan
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab) and w.is_modified:
                w.save()
        # Simpan graf
        self._graph.save()
        super().closeEvent(event)
