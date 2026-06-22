"""noteration/ui/editor_tab.py

Complete tab implementation for Markdown editing and previewing.
Orchestrates the editor, previewer, and metadata extraction.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from noteration.editor.wiki_links import (
    extract_headings,
    parse_citations,
)
from noteration.logger import get_logger
from noteration.ui.editor.markdown_editor import MarkdownEditor
from noteration.ui.editor.markdown_preview import MarkdownPreview
from noteration.ui.editor.vim import VimCommandField, VimMode
from noteration.ui.tab_base import NoterationTab

logger = get_logger(__name__)

if TYPE_CHECKING:
    from noteration.vault_manager import VaultManager


class EditorTab(NoterationTab):
    """Complete tab implementation for Markdown editing and previewing.
    Orchestrates the editor, previewer, and metadata extraction.
    """

    cursor_moved = Signal(int, int)
    content_changed = Signal()
    wiki_link_clicked = Signal(str)
    headings_changed = Signal(list)
    citations_changed = Signal(list)
    word_count_changed = Signal(int)
    save_requested = Signal()
    save_finished = Signal()
    focus_mode_exit_requested = Signal()
    view_mode_requested = Signal(bool)
    export_requested = Signal(str)

    def __init__(
        self,
        file_path: Path,
        vault: "VaultManager",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.vault = vault
        self.vault_path = vault.vault_path
        self.config = vault.config
        self.is_modified = False
        self._is_focus_mode = False
        self._save_thread: Optional[QThread] = None
        self._save_worker: Optional[Any] = None

        # Performance cache
        self._last_parsed_hash = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Per-tab toolbar ──────────────────────────────────────────
        self._tab_toolbar = QToolBar()
        self._tab_toolbar.setMovable(False)
        self._tab_toolbar.setContentsMargins(2, 0, 2, 0)
        self._tab_toolbar.setStyleSheet(
            "QToolBar { border-bottom: 1px solid palette(mid);"
            " background: palette(window); spacing: 2px; }"
            " QToolButton { padding: 2px 8px; border-radius: 3px; }"
            " QToolButton:checked { background: palette(highlight);"
            "   color: palette(highlighted-text); }"
        )

        from PySide6.QtGui import QActionGroup

        self._act_edit = self._tab_toolbar.addAction("✎  Edit")
        self._act_edit.setCheckable(True)
        self._act_edit.setChecked(True)
        self._act_edit.setToolTip("Edit mode — Ctrl+Shift+V")
        self._act_edit.triggered.connect(lambda: self.view_mode_requested.emit(False))

        self._act_view = self._tab_toolbar.addAction("👁  View")
        self._act_view.setCheckable(True)
        self._act_view.setChecked(False)
        self._act_view.setToolTip("Preview render mode — Ctrl+Shift+V")
        self._act_view.triggered.connect(lambda: self.view_mode_requested.emit(True))

        _grp = QActionGroup(self._tab_toolbar)
        _grp.setExclusive(True)
        _grp.addAction(self._act_edit)
        _grp.addAction(self._act_view)

        layout.addWidget(self._tab_toolbar)

        # Content stack: Standard (0), Preview (1), Focus (2)
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # 1. Standard Editor View
        self._editor_container = QWidget()
        self._editor_layout = QVBoxLayout(self._editor_container)
        self._editor_layout.setContentsMargins(0, 0, 0, 0)

        self._editor = MarkdownEditor(self.config)
        self._editor.wiki_link_activated.connect(self.wiki_link_clicked)
        self._editor.cursorPositionChanged.connect(self._on_cursor_moved)
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.image_dropped.connect(self._on_image_dropped)
        self._editor.image_pasted.connect(self._on_image_pasted)

        self._editor.vim_command_requested.connect(self._on_vim_command_requested)
        self._editor.vim_mode_changed.connect(self._on_vim_mode_changed)
        self._editor.vim_exit_requested.connect(self.focus_mode_exit_requested)

        self._editor.view_mode_requested.connect(self.set_view_mode)
        self._editor.export_requested.connect(self.export_as)

        self._editor_layout.addWidget(self._editor)
        self._stack.addWidget(self._editor_container)

        # 2. Preview
        self._preview = MarkdownPreview()
        self._preview.link_clicked.connect(self._on_preview_link)
        self._preview.export_requested.connect(self.export_as)
        self._stack.addWidget(self._preview)

        # 3. Focus View
        self._focus_view = QWidget()
        self._focus_layout = QVBoxLayout(self._focus_view)
        self._focus_layout.setContentsMargins(0, 40, 0, 20)

        self._centered_layout = QHBoxLayout()
        self._centered_layout.addStretch()
        # Editor will be reparented here in set_focus_mode
        self._centered_layout.addStretch()
        self._focus_layout.addLayout(self._centered_layout)

        self._vim_cmd_field = VimCommandField()
        self._vim_cmd_field.command_entered.connect(self._handle_vim_command)
        self._vim_cmd_field.esc_pressed.connect(lambda: self._editor.setFocus())
        self._focus_layout.addWidget(self._vim_cmd_field, 0, Qt.AlignmentFlag.AlignCenter)
        self._vim_cmd_field.setFixedWidth(1000)

        self._focus_status = QLabel()
        self._focus_status.setStyleSheet(
            "color: palette(window-text); font-size: 11px; margin-top: 10px;"
        )
        self._focus_layout.addWidget(self._focus_status, 0, Qt.AlignmentFlag.AlignCenter)

        self._stack.addWidget(self._focus_view)
        self._stack.setCurrentIndex(0)

        self._is_view_mode = False
        self._update_highlighter_theme()

        # Update parsed signals with a delay to improve performance
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit_parsed_signals)

        # Citation autocomplete integration
        self._completer = None
        if self.vault.papis:
            try:
                from noteration.editor.citation_completer import CitationCompleter

                self._completer = CitationCompleter(self._editor, self.vault.papis, self)
            except Exception as e:
                logger.warning(f"Citation completer initialization failed: {e}")
        # Global shortcut for mode toggling
        from PySide6.QtGui import QKeySequence, QShortcut

        _sc = QShortcut(QKeySequence("Ctrl+Shift+V"), self)
        _sc.activated.connect(lambda: self.set_view_mode(not self._is_view_mode))

        self._load_file()

    def _update_highlighter_theme(self) -> None:
        from noteration.ui.theme import get_effective_mode, get_syntax_palette

        mode = get_effective_mode(self.config.theme)
        palette = get_syntax_palette(mode)
        self._editor._highlighter.set_palette(palette)

    def changeEvent(self, event) -> None:
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Type.PaletteChange:
            self._update_highlighter_theme()
            if self._is_view_mode:
                self._refresh_preview()
        super().changeEvent(event)

    # ── Persistence ───────────────────────────────────────────────────

    def _load_file(self) -> None:
        if self.file_path.exists():
            text = self.file_path.read_text(encoding="utf-8")
            self._editor.setPlainText(text)
        self.is_modified = False
        self._emit_parsed_signals()

    def display_title(self) -> str:
        return self.file_path.name

    def session_state(self) -> dict[str, Any] | None:
        try:
            rel_path = self.file_path.relative_to(self.vault_path)
        except ValueError:
            logger.warning(f"EditorTab path is outside vault: {self.file_path}")
            return None
        return {"type": "editor", "path": str(rel_path)}

    def is_dirty(self) -> bool:
        return self.is_modified

    def save_if_dirty(self) -> None:
        if self.is_dirty():
            self.save()
            self.vault.update_note_in_graph(self.file_path)

    def can_close(self) -> bool:
        return True

    def save(self) -> None:
        if not self.is_modified:
            return

        # 1. Defensively check for existing save operation
        if getattr(self, "_is_saving", False):
            return

        if self._save_thread:
            try:
                if self._save_thread.isRunning():
                    return
            except RuntimeError:
                # C++ object was already deleted, nullify reference
                self._save_thread = None
                self._save_worker = None

        text = self._editor.toPlainText()
        # Reset modified flag immediately (optimistic UI)
        self.is_modified = False
        self._is_saving = True
        self._update_focus_status()

        # 2. Create background worker via manager
        self._save_thread = QThread()
        self._save_worker = self.vault.save_note(self.file_path, text)
        self._save_worker.moveToThread(self._save_thread)

        # 3. Connect signals
        self._save_worker.finished.connect(self._on_save_success)
        self._save_worker.error.connect(self._on_save_error)

        # 4. Standard Cleanup Pattern
        self._save_worker.finished.connect(self._save_thread.quit)
        self._save_thread.finished.connect(self._clear_save_worker)

        self._save_thread.started.connect(self._save_worker.run)
        self._save_thread.start()

        # Ensure the file is tracked by Git (status check is already async)
        if self.vault.core.git_repo:
            self.vault.request_git_status()

    def _on_save_success(self) -> None:
        """Handle successful save operation."""
        self._is_saving = False
        self.save_finished.emit()
        self.vault.tags_updated.emit()
        self.vault.graph_updated.emit(1)

    def _on_save_error(self, msg: str) -> None:
        """Handle failed save operation."""
        self._is_saving = False
        logger.error(f"Save failed for {self.file_path}: {msg}")
        # Restore modified flag on error so user can retry
        self.is_modified = True
        self._update_focus_status()

    def _clear_save_worker(self) -> None:
        """Safely delete and nullify the save worker and thread."""
        if self._save_worker:
            self._save_worker.deleteLater()
            self._save_worker = None
        if self._save_thread:
            self._save_thread.deleteLater()
            self._save_thread = None

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._editor.set_line_numbers_visible(visible)

    def shutdown(self) -> None:
        """Wait for background saving to finish if active and cleanup resources."""
        # 1. Stop background saving
        if self._save_thread:
            try:
                if self._save_thread.isRunning():
                    logger.info(f"EditorTab: Waiting for save to finish for {self.file_path}...")
                    if self._save_thread.wait(5000):
                        self._clear_save_worker()
                    else:
                        logger.error(f"EditorTab: Save thread for {self.file_path} timed out. Holding reference.")
                else:
                    self._clear_save_worker()
            except RuntimeError:
                # Already deleted, just clear references
                self._save_thread = None
                self._save_worker = None
        else:
            self._clear_save_worker()

        # 2. Cleanup other resources
        if hasattr(self, "_debounce") and self._debounce:
            self._debounce.stop()
        if hasattr(self, "_preview") and self._preview:
            self._preview.shutdown()

    # ── Focus Mode ───────────────────────────────────────────────────

    def set_focus_mode(self, enabled: bool) -> None:
        self._is_focus_mode = enabled
        self._tab_toolbar.setVisible(not enabled)

        if enabled:
            # Save the current mode before switching to Focus View
            is_preview = self._is_view_mode
            self._editor.set_vim_enabled(True)

            # Dynamic width calculation
            width = self.width() // 2 if self.width() > 100 else 800
            target_w = max(600, width)
            self._editor.setFixedWidth(target_w)
            self._preview.setFixedWidth(target_w)
            self._vim_cmd_field.setFixedWidth(target_w)
            self._focus_status.setFixedWidth(target_w)

            if is_preview:
                self._centered_layout.insertWidget(1, self._preview)
                self._editor.hide()
                self._preview.show()
            else:
                self._centered_layout.insertWidget(1, self._editor)
                self._preview.hide()
                self._editor.show()

            self._stack.setCurrentIndex(2)
            self._update_focus_status()
        else:
            self._editor.set_vim_enabled(False)
            self._editor.setMinimumWidth(0)
            self._editor.setMaximumWidth(16777215)
            self._preview.setMinimumWidth(0)
            self._preview.setMaximumWidth(16777215)

            # Reparent both back to their containers to be safe
            self._editor_layout.addWidget(self._editor)
            # Preview doesn't have a dedicated layout container in the stack,
            # so we just add it to the stack (it will be index 1)
            self._stack.insertWidget(1, self._preview)

            self._editor.show()
            self._preview.show()

            # Restore standard view (Edit or Preview)
            self._stack.setCurrentIndex(1 if self._is_view_mode else 0)
            self._vim_cmd_field.hide()

    def _update_focus_status(self) -> None:
        if not self._is_focus_mode:
            return

        cursor = self._editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        mode = self._editor._vim_mode.value

        status = f"VIM: {mode}  |  Ln {line}, Col {col}"
        if self.is_modified:
            status += "  [modified]"

        self._focus_status.setText(status)

    def resizeEvent(self, event) -> None:
        """Dynamically adjust editor width in focus mode on window resize."""
        super().resizeEvent(event)
        if self._is_focus_mode:
            width = self.width() // 2
            target_w = max(600, width)
            self._editor.setFixedWidth(target_w)
            self._preview.setFixedWidth(target_w)
            self._vim_cmd_field.setFixedWidth(target_w)

    def _on_vim_command_requested(self) -> None:
        self._vim_cmd_field.show()
        self._vim_cmd_field.setFocus()
        self._vim_cmd_field.setText(":")

    def _on_vim_mode_changed(self, mode: VimMode) -> None:
        self._update_focus_status()

    def _handle_vim_command(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            self._editor.setFocus()
            return

        if cmd == ":w":
            self.save_requested.emit()
            self._show_focus_message("File saved")
        elif cmd == ":q":
            self.focus_mode_exit_requested.emit()
        elif cmd == ":wq":
            self.save_requested.emit()
            self.focus_mode_exit_requested.emit()

        self._editor.setFocus()

    def _show_focus_message(self, msg: str) -> None:
        if self._is_focus_mode:
            original_text = self._focus_status.text()
            self._focus_status.setText(msg)
            self._focus_status.setStyleSheet(
                "color: palette(highlight); font-weight: bold; margin-top: 10px;"
            )
            QTimer.singleShot(2000, lambda: self._restore_focus_status(original_text))

    def _restore_focus_status(self, text: str) -> None:
        self._focus_status.setText(text)
        self._focus_status.setStyleSheet(
            "color: palette(window-text); font-size: 11px; margin-top: 10px;"
        )
        self._update_focus_status()

    # ── Mode switching ────────────────────────────────────────────────

    def set_view_mode(self, enabled: bool) -> None:
        """Toggle between raw editing and HTML preview."""
        from PySide6.QtWidgets import QApplication

        self._is_view_mode = enabled
        self._act_edit.setChecked(not enabled)
        self._act_view.setChecked(enabled)

        if enabled:
            self._refresh_preview()
            if self._is_focus_mode:
                # In focus mode, reparent preview to focus layout
                self._centered_layout.insertWidget(1, self._preview)
                self._editor.hide()
                self._preview.show()
                self._stack.setCurrentIndex(2)
            else:
                self._stack.setCurrentIndex(1)
            QApplication.processEvents()
        else:
            if self._is_focus_mode:
                # In focus mode, reparent editor back to focus layout
                self._centered_layout.insertWidget(1, self._editor)
                self._preview.hide()
                self._editor.show()
                self._stack.setCurrentIndex(2)
            else:
                self._stack.setCurrentIndex(0)
            self._editor.setFocus()

    def _refresh_preview(self) -> None:
        """Update the rendered preview with current content."""
        self._preview.set_content(
            self._editor.toPlainText(),
            base_path=self.vault_path,
            theme=self.config.theme,
            vault=self.vault,
        )

    def _on_preview_link(self, target: str) -> None:
        if target:
            self.wiki_link_clicked.emit(target)

    # ── Insertion utilities ───────────────────────────────────────────

    def insert_text(self, text: str) -> None:
        self._editor.insertPlainText(text)

    def insert_quote(self, text: str, citation_key: str, locator: str = "") -> None:
        """Format and insert a text block with a citation."""
        lines = text.strip().splitlines()
        bq = "\n".join(f"> {ln}" for ln in lines)
        cite = f"@{citation_key}[{locator}]" if locator else f"@{citation_key}"
        bq += f"\n> — {cite}\n\n"
        self._editor.insertPlainText(bq)

    def insert_image(self, rel_path: str) -> None:
        md = f"![]({rel_path})\n\n"
        self._editor.insertPlainText(md)

    def _on_image_dropped(self, source_path: str) -> None:
        import shutil
        from pathlib import Path

        src = Path(source_path)
        if not src.exists():
            return

        attachments_dir = self.vault_path / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:6]
        filename = f"{ts}_{uid}{src.suffix}"
        dest = attachments_dir / filename

        shutil.copy2(src, dest)
        self.insert_image(f"attachments/{filename}")

    def _on_image_pasted(self, image) -> None:
        from PySide6.QtGui import QImage

        if isinstance(image, QImage):
            self._paste_image_from_clipboard(image)

    def _paste_image_from_clipboard(self, image: "QImage") -> None:
        """Persist a clipboard image and insert it into the document."""
        attachments_dir = self.vault_path / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:6]
        filename = f"{ts}_{uid}.png"
        dest = attachments_dir / filename

        image.save(str(dest))
        self.insert_image(f"attachments/{filename}")

    # ── Navigation ────────────────────────────────────────────────────

    def go_to_heading(self, heading_text: str) -> None:
        text = self._editor.toPlainText()
        pattern = f"^#+\\s*{re.escape(heading_text)}$"
        for match in re.finditer(pattern, text, re.MULTILINE):
            cursor = self._editor.textCursor()
            cursor.setPosition(match.start())
            self._editor.setTextCursor(cursor)
            self._editor.setFocus()
            return

    def go_to_citation(self, key: str) -> None:
        text = self._editor.toPlainText()
        # Match @key optionally followed by [locator]
        pattern = f"@{re.escape(key)}(?:\\[[^\\]]+\\])?\\b"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            cursor = self._editor.textCursor()
            cursor.setPosition(match.start())
            self._editor.setTextCursor(cursor)
            self._editor.setFocus()

    # ── Metadata extraction ───────────────────────────────────────────

    def headings(self) -> list[tuple[int, str]]:
        return extract_headings(self._editor.toPlainText())

    def citation_keys(self) -> list[str]:
        return [c.key for c in parse_citations(self._editor.toPlainText())]

    def word_count(self) -> int:
        """Calculate word count, excluding YAML front-matter and code blocks."""
        text = self._editor.toPlainText()
        text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`[^`]+`", "", text)
        return len(re.findall(r"\b\w+\b", text))

    def export_as(self, fmt: str) -> None:
        """Export document content to external formats using Pandoc."""
        from noteration.utils.export import PandocExporter

        exporter = PandocExporter()
        if not exporter.is_available:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Pandoc Not Found", "Pandoc is required for export.")
            return

        from PySide6.QtWidgets import QFileDialog

        # Get the friendly name and extension for the format
        ext, filter_str = exporter.SUPPORTED_FORMATS.get(
            fmt, (f".{fmt}", f"{fmt.upper()} Files (*.{fmt})")
        )

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            f"Export to {fmt.upper()}",
            str(self.vault_path / f"{self.file_path.stem}{ext}"),
            filter_str,
        )
        if not path_str:
            return

        path = Path(path_str)
        content = self._editor.toPlainText()
        title = self.file_path.stem

        success, message = exporter.export(
            content, path, title=title, resource_path=self.vault_path
        )

        from PySide6.QtWidgets import QMessageBox

        if success:
            QMessageBox.information(self, "Export Finished", message)
        else:
            QMessageBox.critical(self, "Export Failed", message)

    def _request_export(self, fmt: str) -> None:
        """Emit signal that export is requested, used by context menu."""
        self.export_requested.emit(fmt)

    # ── Event handlers ────────────────────────────────────────────────

    def _on_cursor_moved(self) -> None:
        c = self._editor.textCursor()
        self.cursor_moved.emit(c.blockNumber() + 1, c.columnNumber() + 1)
        self._update_focus_status()

    def _on_text_changed(self) -> None:
        self.is_modified = True
        self.content_changed.emit()
        if hasattr(self, "_debounce") and self._debounce:
            self._debounce.start()
        self._update_focus_status()

    def _emit_parsed_signals(self) -> None:
        """Emit signals for sidebar and status bar updates with hash caching."""
        text = self._editor.toPlainText()
        current_hash = hash(text)

        if current_hash == self._last_parsed_hash:
            return

        self._last_parsed_hash = current_hash
        self.headings_changed.emit(self.headings())
        self.citations_changed.emit(self.citation_keys())
        self.word_count_changed.emit(self.word_count())

    def closeEvent(self, event) -> None:
        if hasattr(self, "_debounce") and self._debounce:
            self._debounce.stop()
        super().closeEvent(event)
