"""Markdown editor tab with syntax highlighting, citation autocomplete, and wiki-link support.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPalette,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from noteration.config import NoterationConfig
from noteration.editor.find_replace import FindReplaceDialog
from noteration.editor.syntax_highlighter import MarkdownHighlighter
from noteration.editor.wiki_links import (
    extract_headings,
    parse_citations,
    parse_wiki_links,
)
from noteration.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from noteration.vault_manager import VaultManager

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

try:
    import markdown as _markdown_lib  # type: ignore[import-untyped]

    _HAS_MARKDOWN = True
except ImportError:
    _HAS_MARKDOWN = False


class VimMode(Enum):
    NORMAL = "NORMAL"
    INSERT = "INSERT"
    VISUAL = "VISUAL"
    LINE_VISUAL = "LINE_VISUAL"
    COMMAND = "COMMAND"


# =========================================================================
# VimCommandField
# =========================================================================


class VimCommandField(QLineEdit):
    """Small command field for Vim-like commands (e.g., :w, :q)."""

    command_entered = Signal(str)
    esc_pressed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Enter command (e.g., :w, :q)...")
        self.setStyleSheet(
            "QLineEdit { border: 1px solid palette(mid); padding: 4px; "
            " font-family: monospace; background: palette(base); }"
        )
        self.hide()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.command_entered.emit(self.text())
            self.clear()
            self.hide()
        elif event.key() == Qt.Key.Key_Escape:
            self.clear()
            self.hide()
            self.esc_pressed.emit()
        else:
            super().keyPressEvent(event)


# =========================================================================
# LineNumberArea
# =========================================================================


class LineNumberArea(QWidget):
    """Small side panel for displaying line numbers in the editor."""

    def __init__(self, editor: "MarkdownEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        self._editor.line_number_area_paint_event(event)


# =========================================================================
# MarkdownEditor
# =========================================================================


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

    def __init__(self, config: NoterationConfig, parent=None) -> None:
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

    def keyPressEvent(self, event: QKeyEvent) -> None:
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
            cursor.movePosition(self.textCursor().MoveOperation.Start)
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
        cursor.movePosition(cursor.MoveOperation.Start)
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


# =========================================================================
# MarkdownPreview
# =========================================================================

# Default CSS for the rendered HTML view
_PREVIEW_CSS = """
:root {
  --bg:      #ffffff;
  --text:    #24292e;
  --muted:   #6a737d;
  --border:  #e1e4e8;
  --code-bg: #f6f8fa;
  --link:    #0366d6;
  --bq-border: #dfe2e5;
  --bq-bg:   #f9f9f9;
  --hl-bg:   #fff3cd;
  --wiki-bg: #EEEDFE;
  --wiki-fg: #534AB7;
  --cite-bg: #E1F5EE;
  --cite-fg: #0F6E56;
}
* { box-sizing: border-box; }
html { font-size: 16px; background: var(--bg); }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
               Helvetica, Arial, sans-serif;
  font-size: 1rem;
  line-height: 1.7;
  color: var(--text);
  background: var(--bg);
  max-width: 780px;
  margin: 0 auto;
  padding: 2rem 2.5rem 4rem;
}
/* Headings */
h1,h2,h3,h4,h5,h6 {
  font-weight: 600;
  line-height: 1.25;
  margin-top: 1.5em;
  margin-bottom: .5em;
}
h1 { font-size: 2em;   border-bottom: 1px solid var(--border); padding-bottom:.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid var(--border); padding-bottom:.3em; }
h3 { font-size: 1.25em; }
h4 { font-size: 1em; }
h5 { font-size: .875em; }
h6 { font-size: .85em;  color: var(--muted); }
p { margin: 0 0 1em; }
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
strong { font-weight: 600; }
blockquote {
  margin: 1em 0;
  padding: .5em 1em;
  color: var(--muted);
  background: var(--bq-bg);
  border-left: .25em solid var(--bq-border);
  border-radius: 0 4px 4px 0;
}
blockquote p { margin: 0; }
ul, ol { padding-left: 2em; margin: 0 0 1em; }
li + li { margin-top: .25em; }
code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: .9em;
  background: var(--code-bg);
  padding: .1em .35em;
  border-radius: 3px;
  border: 1px solid var(--border);
}
pre {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1em 1.25em;
  overflow-x: auto;
  line-height: 1.5;
  margin: 0 0 1em;
}
pre code {
  background: transparent;
  border: none;
  padding: 0;
  font-size: .875em;
}
hr {
  border: none;
  border-top: 2px solid var(--border);
  margin: 1.5em 0;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 1em;
  font-size: .9em;
}
th, td {
  border: 1px solid var(--border);
  padding: .5em .75em;
  text-align: left;
}
th { background: var(--code-bg); font-weight: 600; }
tr:nth-child(even) { background: var(--bq-bg); }
img { max-width: 100%; height: auto; border-radius: 4px; }
a.wikilink {
  background: var(--wiki-bg);
  color: var(--wiki-fg);
  padding: .05em .35em;
  border-radius: 3px;
  font-size: .9em;
  text-decoration: none;
  border: 1px solid var(--border);
  cursor: pointer;
}
a.wikilink:hover {
  opacity: 0.8;
}
.citation {
  background: var(--cite-bg);
  color: var(--cite-fg);
  padding: .05em .3em;
  border-radius: 3px;
  font-size: .9em;
  font-family: monospace;
}
"""

_MARKDOWN_EXTENSIONS = [
    "pymdownx.arithmatex",  # Better LaTeX support
    "pymdownx.superfences",  # Support for nested fences and better code blocks
    "pymdownx.tasklist",  # - [ ] Checklists
    "pymdownx.tilde",  # ~~strikethrough~~
    "pymdownx.caret",  # ^^superscript^^
    "pymdownx.mark",  # ==highlight==
    "extra",  # tables, footnotes, attr_list, def_list, abbr
    "sane_lists",  # correct list behavior
    "toc",  # heading anchors
]


def _md_to_html(
    text: str, base_url: str = "", theme: str = "light", vault: "VaultManager" | None = None
) -> str:
    """Convert Markdown content to a self-contained HTML document.
    Handles wiki-links, citations, and theme-specific syntax coloring.
    """
    import re

    from noteration.editor.wiki_links import parse_citations
    from noteration.ui.theme import (
        _DARK_COLORS,
        _LIGHT_COLORS,
        ThemeMode,
        get_effective_mode,
        get_syntax_palette,
    )

    mode = get_effective_mode(theme)
    palette = get_syntax_palette(mode)
    base_colors = _DARK_COLORS if mode == ThemeMode.DARK else _LIGHT_COLORS

    def get_hex(role):
        return base_colors.get(role, "#000000")

    css_vars = f"""
    :root {{
      --bg:      {get_hex(QPalette.ColorRole.Base)};
      --text:    {get_hex(QPalette.ColorRole.Text)};
      --muted:   {get_hex(QPalette.ColorRole.PlaceholderText)};
      --border:  {get_hex(QPalette.ColorRole.Mid)};
      --code-bg: {palette.get("code_block", ("", "#f6f8fa"))[1]};
      --link:    {get_hex(QPalette.ColorRole.Link)};
      --bq-border: {get_hex(QPalette.ColorRole.Highlight)};
      --bq-bg:   {palette.get("quote", ("", "#f9f9f9"))[1]};
      --wiki-bg: {palette.get("wiki", ("", "#EEEDFE"))[1]};
      --wiki-fg: {palette.get("wiki", ("#534AB7", ""))[0]};
      --cite-bg: {palette.get("cite", ("", "#E1F5EE"))[1]};
      --cite-fg: {palette.get("cite", ("#0F6E56", ""))[0]};
    }}
    """

    # Locate local MathJax library
    import noteration

    assets_js = Path(noteration.__file__).parent / "assets" / "js"
    mathjax_url = (assets_js / "tex-mml-chtml.js").as_uri()

    if _HAS_MARKDOWN:
        try:
            body = _markdown_lib.markdown(
                text,
                extensions=_MARKDOWN_EXTENSIONS,
                extension_configs={
                    "pymdownx.arithmatex": {
                        "generic": True,
                    }
                },
            )
        except (ImportError, ModuleNotFoundError) as e:
            logger.error(f"Failed to render Markdown with extensions: {e}")
            # Try again with only standard extensions if a specific extension failed to load
            try:
                # Filter out extensions that might be causing the failure (dynamic loading)
                # If it's a ModuleNotFoundError for 'pymdownx', we remove all pymdownx extensions
                safe_extensions = [
                    ext for ext in _MARKDOWN_EXTENSIONS if not ext.startswith("pymdownx")
                ]
                body = _markdown_lib.markdown(text, extensions=safe_extensions)
                logger.info("Successfully rendered Markdown using fallback extensions.")
            except Exception as e2:
                logger.error(f"Fallback Markdown rendering failed: {e2}")
                import html as _html
                body = f"<pre>{_html.escape(text)}</pre>"
    else:
        import html as _html

        body = f"<pre>{_html.escape(text)}</pre>"

    # Preparation for CSL rendering
    citation_map = {}
    if vault and vault.csl.is_available():
        # Parse all citations in the text
        raw_citations = parse_citations(text)
        # Collect unique (key, locator) pairs
        citations_to_render = list(set((c.key, c.locator) for c in raw_citations))
        
        # Look up unique entries in Papis
        unique_keys = list(set(c.key for c in raw_citations))
        entries = []
        for k in unique_keys:
            entry = vault.papis.get(k)
            if entry:
                entries.append(entry)

        # Render them as a batch
        if entries:
            citation_map = vault.csl.render_citations(citations_to_render, entries)

    def _safe_replace(html: str) -> str:
        """Inject wiki-link badges and citations without breaking code blocks."""
        parts = re.split(r"(<code.*?>.*?</code>|<pre.*?>.*?</pre>)", html, flags=re.DOTALL)

        def _wikilink_sub(m: re.Match) -> str:
            target = m.group(1).strip()
            href = "noteration://wiki/" + target.replace(" ", "%20")
            return f'<a class="wikilink" href="{href}" title="Note: {target}">[[{target}]]</a>'

        new_parts = []
        for p in parts:
            if p.startswith(("<code", "<pre")):
                new_parts.append(p)
            else:
                p = re.sub(r"\[\[([^\]]+)\]\]", _wikilink_sub, p)

                # Replace citations with rendered versions if available
                def _cite_sub(m: re.Match) -> str:
                    key = m.group(1)
                    locator = m.group(2)
                    display = citation_map.get((key, locator), m.group(0))
                    return f'<span class="citation" title="Source: {key}">{display}</span>'

                # Match @key or @key[locator]
                p = re.sub(r"@([A-Za-z][A-Za-z0-9_:\-]+)(?:\[([^\]]+)\])?", _cite_sub, p)
                new_parts.append(p)
        return "".join(new_parts)

    body = _safe_replace(body)

    base_tag = '<base href="{}">'.format(base_url) if base_url else ""
    html_template = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  %BASE_TAG%
  <style>
    %STYLE%
    %CSS_VARS%
    /* Disable MathJax context menu by ignoring mouse events */
    .MathJax { pointer-events: none !important; }
  </style>
  <script>
    window.MathJax = {
      tex: {
        inlineMath: [['$', '$'], ['\\(', '\\)']],
        displayMath: [['$$', '$$'], ['\\[', '\\]']],
        processEscapes: true
      },
      options: {
        processHtmlClass: 'arithmatex'
      },
      menuSettings: {
        context: 'None'
      }
    };
  </script>
  <script src="%MATHJAX_URL%"></script>
</head>
<body>
<div class="markdown-body">
%BODY%
</div>
</body>
</html>"""
    return (
        html_template.replace("%BASE_TAG%", base_tag)
        .replace("%STYLE%", _PREVIEW_CSS)
        .replace("%CSS_VARS%", css_vars)
        .replace("%MATHJAX_URL%", mathjax_url)
        .replace("%BODY%", body)
    )


if _HAS_WEBENGINE:

    class _NoterationPage(QWebEnginePage):
        """Intercept navigation requests to handle wiki-links and external URLs.
        """

        link_clicked = Signal(str)

        def acceptNavigationRequest(
            self,
            url: QUrl | str,
            nav_type: QWebEnginePage.NavigationType,
            is_main_frame: bool,
        ) -> bool:
            from PySide6.QtCore import QUrl as QUrlClass

            if isinstance(url, str):
                url = QUrlClass(url)
            scheme = url.scheme()
            url_str = url.toString()

            if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                return True

            if scheme == "noteration":
                if url.host() == "wiki":
                    target = url.path().lstrip("/")
                    self.link_clicked.emit(target)
                return False

            if scheme in ("http", "https", "ftp"):
                import shutil
                import subprocess

                xdg_open = shutil.which("xdg-open")
                if xdg_open:
                    subprocess.Popen([xdg_open, url_str])  # nosec S603
                return False

            return False


class MarkdownPreview(QWidget):
    """Preview component for rendered Markdown.
    Uses QWebEngineView for rich rendering or QTextBrowser as a fallback.
    """

    link_clicked = Signal(str)
    export_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Allow forced fallback for compatibility
        force_text = os.environ.get("NOTERATION_USE_TEXT_BROWSER") == "1"

        if _HAS_WEBENGINE and not force_text:
            self._view = QWebEngineView()
            self._page = _NoterationPage(self)
            self._page.link_clicked.connect(self.link_clicked)

            # Security: Allow local content to access local file URLs for MathJax and images
            settings = self._page.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )  # Required for MathJax

            self._view.setPage(self._page)
            self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._view.customContextMenuRequested.connect(self._handle_context_menu)
            self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self._view)
            self._use_webengine = True
        else:
            from PySide6.QtWidgets import QTextBrowser

            self._tb = QTextBrowser()
            self._tb.setOpenExternalLinks(False)
            self._tb.setOpenLinks(False)
            self._tb.anchorClicked.connect(self._on_tb_anchor)
            self._tb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._tb.customContextMenuRequested.connect(self._handle_context_menu)
            self._tb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self._tb)
            self._use_webengine = False

    def _handle_context_menu(self, pos) -> None:
        """View-mode context menu with export options."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)

        copy = menu.addAction("Copy")
        menu.addSeparator()

        export_menu = menu.addMenu("📥 Export")
        export_html = export_menu.addAction("HTML")
        export_pdf = export_menu.addAction("PDF")
        export_docx = export_menu.addAction("DOCX")
        export_odt = export_menu.addAction("ODT")
        export_latex = export_menu.addAction("LaTeX")
        export_txt = export_menu.addAction("Plain Text (TXT)")

        sender_obj = self.sender()
        sender = (
            sender_obj
            if isinstance(sender_obj, QWidget)
            else (self._view if self._use_webengine else self._tb)
        )

        chosen = menu.exec(sender.mapToGlobal(pos))
        if not chosen:
            return

        if chosen == copy:
            if self._use_webengine:
                self._view.triggerPageAction(QWebEnginePage.WebAction.Copy)
            else:
                self._tb.copy()
        elif chosen in [export_html, export_pdf, export_txt, export_docx, export_odt, export_latex]:
            if chosen == export_html:
                fmt = "html"
            elif chosen == export_pdf:
                fmt = "pdf"
            elif chosen == export_txt:
                fmt = "txt"
            elif chosen == export_docx:
                fmt = "docx"
            elif chosen == export_odt:
                fmt = "odt"
            else:
                fmt = "latex"

            self.export_requested.emit(fmt)

    def _on_tb_anchor(self, url: QUrl) -> None:
        """Handle link clicks in the fallback text browser."""
        scheme = url.scheme()
        if scheme == "noteration" and url.host() == "wiki":
            self.link_clicked.emit(url.path().lstrip("/"))
        elif scheme in ("http", "https"):
            import shutil
            import subprocess

            xdg_open = shutil.which("xdg-open")
            if xdg_open:
                subprocess.Popen([xdg_open, url.toString()])  # nosec S603

    def shutdown(self) -> None:
        """Explicitly cleanup WebEngine resources to avoid profile release warnings."""
        if self._use_webengine:
            # 0. Ensure Qt application is still active before GUI cleanup.
            from PySide6.QtWidgets import QApplication
            if not QApplication.instance():
                return

            # 1. Detach and hide the view
            if hasattr(self, "_view") and self._view:
                self._view.hide()
                self._view.setPage(None)  # type: ignore[arg-type]

            # 2. Forcefully delete the page first
            if hasattr(self, "_page") and self._page:
                self._page.setParent(None)
                try:
                    self._page.deleteLater()
                except Exception as e:
                    logger.debug(f"Shiboken delete _page failed: {e}")
                self._page = None  # type: ignore

            # 3. Forcefully delete the view
            if hasattr(self, "_view") and self._view:
                self._view.setParent(None)
                try:
                    self._view.deleteLater()
                except Exception as e:
                    logger.debug(f"Shiboken delete _view failed: {e}")
                self._view = None  # type: ignore

    def set_content(
        self,
        markdown_text: str,
        base_path: Optional[Path] = None,
        theme: str = "light",
        vault: Optional["VaultManager"] = None,
    ) -> None:
        """Update the displayed content."""
        base_url = QUrl()
        if base_path and base_path.exists():
            base_dir = str(base_path) if base_path.is_dir() else str(base_path.parent)
            if not base_dir.endswith("/"):
                base_dir += "/"
            base_url = QUrl.fromLocalFile(base_dir)

        html = _md_to_html(markdown_text, base_url.toString(), theme=theme, vault=vault)

        if self._use_webengine:
            self._page.setHtml(html, base_url)
        else:
            self._tb.setHtml(html)


# =========================================================================
# EditorTab
# =========================================================================


class EditorTab(QWidget):
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

    def save(self) -> None:
        text = self._editor.toPlainText()
        self.file_path.write_text(text, encoding="utf-8")
        self.is_modified = False
        self._update_focus_status()

        # Explicitly index the updated tags for this note upon save
        if self.vault.core.fts:
            # Calculate note_id locally since _get_note_id belongs to MainWindow
            try:
                rel = self.file_path.relative_to(self.vault_path / "notes")
                note_id = str(rel.with_suffix(""))
            except ValueError:
                note_id = self.file_path.stem

            tags = set(re.findall(r"(?:^|\s)#([\w-]+)", text))
            try:
                self.vault.core.fts.index_tags(note_id, list(tags), "note")
                self.vault.tags_updated.emit()
            except Exception as e:
                logger.error(f"Failed to index tags for note {note_id}: {e}")

        # Ensure the file is tracked by Git
        if self.vault.core.git_repo:
            self.vault.request_git_status()

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._editor.set_line_numbers_visible(visible)

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

    def shutdown(self) -> None:
        """Stop timers and cleanup resources."""
        if hasattr(self, "_debounce") and self._debounce:
            self._debounce.stop()
        if hasattr(self, "_preview") and self._preview:
            self._preview.shutdown()

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

    # ── Find / Replace integration ────────────────────────────────────

    def _on_find_next(self, query: str, case: bool, whole: bool, regex: bool) -> None:
        doc = self._editor.document()
        cursor = self._editor.textCursor()
        start_pos = cursor.position()
        flags = QTextDocument.FindFlag(0)
        if case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole:
            flags |= QTextDocument.FindFlag.FindWholeWords

        new_cursor = doc.find(query, start_pos, flags)
        if new_cursor.isNull():
            new_cursor = doc.find(query, 0, flags)
        if not new_cursor.isNull():
            self._editor.setTextCursor(new_cursor)
            self._editor.setFocus()

    def _on_replace(
        self, query: str, replace_text: str, case: bool, whole: bool, regex: bool
    ) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            import re as _re

            flags = 0 if case else _re.IGNORECASE
            if whole:
                query = r"\b" + query + r"\b"
            if regex or _re.search(query, selected, flags):
                cursor.insertText(replace_text)
        self._on_find_next(query, case, whole, regex)

    def _on_replace_all(
        self, query: str, replace_text: str, case: bool, whole: bool, regex: bool
    ) -> None:
        doc = self._editor.document()
        cursor = QTextCursor(doc)
        flags = QTextDocument.FindFlag(0)
        if case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole:
            flags |= QTextDocument.FindFlag.FindWholeWords
        count = 0
        while True:
            found = doc.find(query, cursor, flags)
            if found.isNull():
                break
            cursor = found
            cursor.insertText(replace_text)
            count += 1
        if count > 0:
            self.content_changed.emit()

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
        # Perform the actual export logic here
        import shutil
        import subprocess

        pandoc = shutil.which("pandoc")
        if not pandoc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Pandoc Not Found", "Pandoc is required for export.")
            return

        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export to {fmt.upper()}",
            str(self.vault_path / f"{self.file_path.stem}.{fmt}"),
            f"{fmt.upper()} Files (*.{fmt})",
        )
        if path:
            result = subprocess.run(
                [pandoc, str(self.file_path), "--resource-path", str(self.vault_path), "-o", path],
                capture_output=True,
                text=True,
            )
            from PySide6.QtWidgets import QMessageBox

            if result.returncode == 0:
                QMessageBox.information(self, "Export Finished", f"Exported to {path}")
            else:
                QMessageBox.critical(self, "Export Failed", f"Export failed:\n{result.stderr}")

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
