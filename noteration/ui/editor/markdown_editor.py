"""noteration/ui/editor/markdown_editor.py

Core Markdown text editor component.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QMouseEvent,
    QPainter,
    QPalette,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit

from noteration.editor.syntax_highlighter import MarkdownHighlighter
from noteration.editor.wiki_links import parse_wiki_links
from noteration.ui.editor.line_number_area import LineNumberArea
from noteration.ui.editor.vim import VimMode

if TYPE_CHECKING:
    from noteration.config import NoterationConfig


class MarkdownEditor(QPlainTextEdit):
    """Core Markdown text editor component.
    Includes syntax highlighting, line numbers, active line highlighting,
    and wiki-link navigation via Ctrl+Click.
    """

    wiki_link_activated = Signal(str)
    image_dropped = Signal(str)  # Relative path to dropped image
    image_pasted = Signal(object)  # QImage from clipboard
    vim_mode_changed = Signal(VimMode)
    vim_command_requested = Signal()
    vim_exit_requested = Signal()
    view_mode_requested = Signal(bool)
    export_requested = Signal(str)

    def __init__(self, config: "NoterationConfig", parent=None) -> None:
        super().__init__(parent)
        self.config = config

        self._vim_enabled = False
        self._vim_mode = VimMode.NORMAL
        self._visual_anchor = -1

        font = QFont(config.font_family, config.font_size)
        font.setFixedPitch(True)
        self.setFont(font)

        self._highlighter = MarkdownHighlighter(self.document())

        self._lnum_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.update_line_number_area_width(0)
        self._highlight_current_line()

        # Apply visibility preference from configuration
        if not config.get("editor", "show_line_numbers", True):
            self._lnum_area.hide()

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabStopDistance(config.font_size * config.get("editor", "tab_width", 2))

        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._handle_context_menu)

        self._read_only = False

    # ── Vim Logic ─────────────────────────────────────────────────────

    def set_vim_enabled(self, enabled: bool) -> None:
        self._vim_enabled = enabled
        if enabled:
            self._set_vim_mode(VimMode.NORMAL)
        else:
            self.setReadOnly(self._read_only)
            # Clear any selection
            cursor = self.textCursor()
            cursor.clearSelection()
            self.setTextCursor(cursor)

    def _set_vim_mode(self, mode: VimMode) -> None:
        self._vim_mode = mode
        # In Normal, Visual, and Command modes, the editor is effectively read-only for standard input
        self.setReadOnly(self._read_only or mode != VimMode.INSERT)

        if mode in (VimMode.VISUAL, VimMode.LINE_VISUAL):
            if self._visual_anchor == -1:
                self._visual_anchor = self.textCursor().position()
        else:
            self._visual_anchor = -1

        self.vim_mode_changed.emit(mode)
        self._highlight_current_line()

    # ── Line numbers ──────────────────────────────────────────────────

    def set_line_numbers_visible(self, visible: bool) -> None:
        if visible:
            self._lnum_area.show()
        else:
            self._lnum_area.hide()
        self.update_line_number_area_width()

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 8 + self.fontMetrics().horizontalAdvance("9") * digits + 8

    def update_line_number_area_width(self, _=0) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._lnum_area.scroll(0, dy)
        else:
            self._lnum_area.update(0, rect.y(), self._lnum_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._lnum_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self._lnum_area)
        painter.fillRect(
            event.rect(),
            self.palette().color(QPalette.ColorRole.Window),
        )
        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                color = QColor("#444") if block_num == current else QColor("#bbb")
                painter.setPen(color)
                painter.drawText(
                    0,
                    top,
                    self._lnum_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(block_num + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_num += 1

    # ── Current line highlight ─────────────────────────────────────────

    def _highlight_current_line(self) -> None:
        extras: list[QTextEdit.ExtraSelection] = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            bg_color = self.palette().color(QPalette.ColorRole.Base)
            is_dark = bg_color.lightness() < 128
            if is_dark:
                sel.format.setBackground(QColor("#3A3A3A"))
            else:
                sel.format.setBackground(QColor("#F5F5FF"))
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            extras.append(sel)
        self.setExtraSelections(extras)

    # ── Mouse handling ────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            cursor = self.cursorForPosition(event.position().toPoint())
            pos = cursor.position()
            for link in parse_wiki_links(self.toPlainText()):
                if link.start <= pos <= link.end:
                    self.wiki_link_activated.emit(link.target)
                    return
        super().mousePressEvent(event)

    # ── Keyboard handling ──────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        if not self._vim_enabled:
            if event.key() == Qt.Key.Key_Tab:
                self.insertPlainText(" " * self.config.get("editor", "tab_width", 2))
                return
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_V:
                    clipboard = QApplication.clipboard()
                    image = clipboard.image()
                    if not image.isNull():
                        self.image_pasted.emit(image)
                        return
                    mime = clipboard.mimeData()
                    if mime.hasUrls():
                        for url in mime.urls():
                            if url.isLocalFile():
                                path = url.toLocalFile()
                                ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
                                if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
                                    self.image_dropped.emit(path)
                                    return
                elif event.key() == Qt.Key.Key_Y:
                    self.redo()
                    return
            super().keyPressEvent(event)
            return

        # Vim handling
        key = event.key()
        text = event.text()

        if key == Qt.Key.Key_Escape:
            if self._vim_mode == VimMode.NORMAL:
                self.vim_exit_requested.emit()

            self._set_vim_mode(VimMode.NORMAL)
            cursor = self.textCursor()
            cursor.clearSelection()
            self.setTextCursor(cursor)
            return

        if self._vim_mode == VimMode.INSERT:
            super().keyPressEvent(event)
            return

        # NORMAL / VISUAL / LINE_VISUAL handling
        cursor = self.textCursor()
        move_mode = QTextCursor.MoveMode.MoveAnchor
        if self._vim_mode in (VimMode.VISUAL, VimMode.LINE_VISUAL):
            move_mode = QTextCursor.MoveMode.KeepAnchor

        # Allow standard shortcuts (Ctrl+S, Ctrl+C, etc.) even in Normal mode
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            super().keyPressEvent(event)
            return

        # Movement keys
        if key == Qt.Key.Key_H:
            cursor.movePosition(QTextCursor.MoveOperation.Left, move_mode)
        elif key == Qt.Key.Key_L:
            cursor.movePosition(QTextCursor.MoveOperation.Right, move_mode)
        elif key == Qt.Key.Key_J:
            cursor.movePosition(QTextCursor.MoveOperation.Down, move_mode)
        elif key == Qt.Key.Key_K:
            cursor.movePosition(QTextCursor.MoveOperation.Up, move_mode)
        elif key == Qt.Key.Key_W:
            cursor.movePosition(QTextCursor.MoveOperation.NextWord, move_mode)
        elif key == Qt.Key.Key_B:
            cursor.movePosition(QTextCursor.MoveOperation.PreviousWord, move_mode)
        elif key == Qt.Key.Key_0:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, move_mode)
        elif key == Qt.Key.Key_Dollar:
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, move_mode)
        elif key == Qt.Key.Key_G:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                cursor.movePosition(QTextCursor.MoveOperation.End, move_mode)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.Start, move_mode)

        # State transitions
        elif self._vim_mode == VimMode.NORMAL:
            if text == "i":
                self._set_vim_mode(VimMode.INSERT)
            elif text == "a":
                cursor.movePosition(QTextCursor.MoveOperation.Right)
                self._set_vim_mode(VimMode.INSERT)
            elif text == "o":
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                cursor.insertText("\n")
                self._set_vim_mode(VimMode.INSERT)
            elif text == "v":
                self._set_vim_mode(VimMode.VISUAL)
            elif text == "V":
                self._set_vim_mode(VimMode.LINE_VISUAL)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                self._visual_anchor = cursor.position()
                cursor.movePosition(
                    QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor
                )
            elif text == ":":
                self.vim_command_requested.emit()
            elif text == "u":
                self.undo()
            elif text == "x":
                cursor.deleteChar()
            elif text == "p":
                self.paste()
            else:
                # If no Vim command matches, allow standard processing
                super().keyPressEvent(event)
                return

        elif self._vim_mode in (VimMode.VISUAL, VimMode.LINE_VISUAL):
            if text == "y":
                self.copy()
                self._set_vim_mode(VimMode.NORMAL)
            elif text in ("d", "x"):
                self.cut()
                self._set_vim_mode(VimMode.NORMAL)
            elif text == "c":
                self.cut()
                self._set_vim_mode(VimMode.INSERT)
            else:
                super().keyPressEvent(event)
                return

        self.setTextCursor(cursor)

    # ── Drag & Drop support ───────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = url.toLocalFile().lower().split(".")[-1]
                    if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
                        event.accept()
                        return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    ext = path.lower().split(".")[-1]
                    if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
                        self.image_dropped.emit(path)
                        event.accept()
                        return
        super().dropEvent(event)

    # ── Context Menu ─────────────────────────────────────────────────

    def _handle_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        clipboard = QApplication.clipboard()
        image = clipboard.image()
        mime = clipboard.mimeData()

        image_paste = False
        if not image.isNull():
            image_paste = True
        elif mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
                    if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
                        image_paste = True
                        break

        menu = QMenu(self)
        undo = redo = cut = copy = paste = select_all = find_replace = None
        export_html = export_pdf = export_txt = None

        if self._read_only:
            copy = menu.addAction("Copy")
            select_all = menu.addAction("Select All")
            menu.addSeparator()
            export_menu = menu.addMenu("📥 Export")
            export_html = export_menu.addAction("Export to HTML")
            export_pdf = export_menu.addAction("Export to PDF")
            export_txt = export_menu.addAction("Export to TXT")
        else:
            undo = menu.addAction("Undo")
            redo = menu.addAction("Redo")
            menu.addSeparator()
            cut = menu.addAction("Cut")
            copy = menu.addAction("Copy")
            paste = menu.addAction("Paste" + (" Image" if image_paste else ""))
            select_all = menu.addAction("Select All")
            menu.addSeparator()
            find_replace = menu.addAction("🔍 Find and Replace")

        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is None:
            return

        if chosen == undo:
            self.undo()
        elif chosen == redo:
            self.redo()
        elif chosen == cut:
            self.cut()
        elif chosen == copy:
            self.copy()
        elif chosen == export_html:
            self._request_export("html")
        elif chosen == export_pdf:
            self._request_export("pdf")
        elif chosen == export_txt:
            self._request_export("txt")
        elif chosen == paste:
            if image_paste:
                if not image.isNull():
                    self.image_pasted.emit(image)
                else:
                    for url in mime.urls():
                        if url.isLocalFile():
                            self.image_dropped.emit(url.toLocalFile())
                            break
            else:
                self.paste()
        elif chosen == select_all:
            self.selectAll()
        elif chosen == find_replace:
            self._open_find_replace()

    def _open_find_replace(self) -> None:
        """Open the find/replace dialog and initialize with selection."""
        from noteration.editor.find_replace import FindReplaceDialog
        dlg = FindReplaceDialog(self)

        cursor = self.textCursor()
        if cursor.hasSelection():
            dlg.set_initial_text(cursor.selectedText())

        dlg.find_next_requested.connect(self._find_next)
        dlg.replace_requested.connect(self._replace)
        dlg.replace_all_requested.connect(self._replace_all)
        dlg.show()

    def _find_next(self, query: str, case: bool, whole: bool, regex: bool) -> bool:
        """Locate the next occurrence of text matching the search criteria."""
        flags = QTextDocument.FindFlag(0)
        if case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole:
            flags |= QTextDocument.FindFlag.FindWholeWords

        if regex:
            from PySide6.QtCore import QRegularExpression

            re_flags = QRegularExpression.PatternOption.NoPatternOption
            if not case:
                re_flags |= QRegularExpression.PatternOption.CaseInsensitiveOption

            rx = QRegularExpression(query, re_flags)
            found = self.find(rx, flags)
        else:
            found = self.find(query, flags)

        if not found:
            # Wrap around from the start of the document
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.setTextCursor(cursor)
            if regex:
                from PySide6.QtCore import QRegularExpression

                re_flags = QRegularExpression.PatternOption.NoPatternOption
                if not case:
                    re_flags |= QRegularExpression.PatternOption.CaseInsensitiveOption
                found = self.find(QRegularExpression(query, re_flags), flags)
            else:
                found = self.find(query, flags)
        return found

    def _replace(self, query: str, replace_text: str, case: bool, whole: bool, regex: bool) -> None:
        """Replace the current selection if it matches, otherwise find next."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            self._find_next(query, case, whole, regex)
            return

        selected = cursor.selectedText()
        match = False
        if regex:
            import re

            re_flags = 0 if case else re.IGNORECASE
            if re.fullmatch(query, selected, flags=re_flags):
                match = True
        else:
            if case:
                match = selected == query
            else:
                match = selected.lower() == query.lower()

        if match:
            cursor.insertText(replace_text)
            self._find_next(query, case, whole, regex)
        else:
            self._find_next(query, case, whole, regex)

    def _replace_all(
        self, query: str, replace_text: str, case: bool, whole: bool, regex: bool
    ) -> None:
        """Replace all occurrences in the entire document."""
        old_cursor = self.textCursor()

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)

        while self._find_next(query, case, whole, regex):
            self.textCursor().insertText(replace_text)

        self.setTextCursor(old_cursor)

    # ── Mode switching ────────────────────────────────────────────────

    def set_view_mode(self, enabled: bool) -> None:
        """Update internal editor state when switching between view and edit."""
        self._read_only = enabled
        self.setReadOnly(enabled)

    def _request_view_mode(self, enabled: bool) -> None:
        """Signal that view mode is requested."""
        self.view_mode_requested.emit(enabled)

    def _request_export(self, fmt: str) -> None:
        """Signal that export is requested."""
        self.export_requested.emit(fmt)
