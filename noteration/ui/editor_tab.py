"""
Markdown editor tab with syntax highlighting, citation autocomplete, and wiki-link support.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPlainTextEdit, QTextEdit,
    QApplication, QStackedWidget, QToolBar, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRect, QSize, QTimer, QUrl
from PySide6.QtGui import (
    QFont, QPainter, QColor, QTextFormat, QTextDocument, QTextCursor,
    QPalette, QMouseEvent, QKeyEvent, QDragEnterEvent, QDropEvent, QImage,
)
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

from noteration.editor.find_replace import FindReplaceDialog

try:
    import markdown as _markdown_lib  # type: ignore[import-untyped]
    _HAS_MARKDOWN = True
except ImportError:
    _HAS_MARKDOWN = False

from noteration.config import NoterationConfig
from noteration.editor.syntax_highlighter import MarkdownHighlighter
from noteration.editor.wiki_links import (
    parse_wiki_links, parse_citations, extract_headings,
)


# =========================================================================
# LineNumberArea
# =========================================================================

class LineNumberArea(QWidget):
    def __init__(self, editor: "MarkdownEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:          # type: ignore[override]
        self._editor.line_number_area_paint_event(event)


# =========================================================================
# MarkdownEditor
# =========================================================================

class MarkdownEditor(QPlainTextEdit):
    """
    QPlainTextEdit dengan syntax highlighting, nomor baris,
    highlight baris aktif, dan navigasi wiki-link via Ctrl+Klik.
    """

    wiki_link_activated = Signal(str)
    image_dropped = Signal(str)  # path ke gambar yang di-drop
    image_pasted = Signal(object)  # QImage dari clipboard

    def __init__(self, config: NoterationConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config

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

        # Apply line numbers visibility from config
        if not config.get("editor", "show_line_numbers", True):
            self._lnum_area.hide()

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabStopDistance(
            config.font_size * config.get("editor", "tab_width", 2)
        )

        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._handle_context_menu)

        self._read_only = False

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
            self._lnum_area.update(
                0, rect.y(), self._lnum_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()

    def resizeEvent(self, event) -> None:          # type: ignore[override]
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._lnum_area.setGeometry(
            QRect(cr.left(), cr.top(),
                  self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self._lnum_area)
        painter.fillRect(
            event.rect(),
            self.palette().color(QPalette.ColorRole.Window),
        )
        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = round(
            self.blockBoundingGeometry(block)
            .translated(self.contentOffset()).top()
        )
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                color = QColor("#444") if block_num == current else QColor("#bbb")
                painter.setPen(color)
                painter.drawText(
                    0, top,
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
            sel.format.setProperty(
                QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            extras.append(sel)
        self.setExtraSelections(extras)

    # ── Mouse ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            cursor = self.cursorForPosition(event.pos())
            pos = cursor.position()
            for link in parse_wiki_links(self.toPlainText()):
                if link.start <= pos <= link.end:
                    self.wiki_link_activated.emit(link.target)
                    return
        super().mousePressEvent(event)

    # ── Keyboard ──────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Tab:
            self.insertPlainText(
                " " * self.config.get("editor", "tab_width", 2))
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

    # ── Drag & Drop ─────────────────────────────────────────────────

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

        if self._read_only:
            # View Mode - show Edit Mode option
            edit_mode = menu.addAction("✏ Edit Mode")
        else:
            # Edit Mode - show Edit menu + View Mode option
            edit_menu = menu.addMenu("📝 Edit")
            undo = edit_menu.addAction("Undo")
            redo = edit_menu.addAction("Redo")
            cut = edit_menu.addAction("Cut")
            copy = edit_menu.addAction("Copy")
            paste = edit_menu.addAction("Paste" + (" Image" if image_paste else ""))
            select_all = edit_menu.addAction("Select All")
            edit_menu.addSeparator()
            find_replace = edit_menu.addAction("🔍 Find and Replace")

            view_mode = menu.addAction("👁 View Mode")

        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is None:
            return

        if self._read_only:
            if chosen == edit_mode:
                self._request_view_mode(False)
        else:
            if chosen == view_mode:
                self._request_view_mode(True)
            elif chosen == undo:
                self.undo()
            elif chosen == redo:
                self.redo()
            elif chosen == cut:
                self.cut()
            elif chosen == copy:
                self.copy()
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
        from noteration.editor.find_replace import FindReplaceDialog
        dlg = FindReplaceDialog(self)
        
        # Set initial text from selection if any
        cursor = self.textCursor()
        if cursor.hasSelection():
            dlg.set_initial_text(cursor.selectedText())
            
        dlg.find_next_requested.connect(self._find_next)
        dlg.replace_requested.connect(self._replace)
        dlg.replace_all_requested.connect(self._replace_all)
        dlg.show()  # Non-modal is better for find/replace

    def _find_next(self, query: str, case: bool, whole: bool, regex: bool) -> bool:
        flags = QTextDocument.FindFlag(0)
        if case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole:
            flags |= QTextDocument.FindFlag.FindWholeWords
            
        if regex:
            # For regex, we use the overload that takes QRegularExpression if available,
            # but QPlainTextEdit.find with QRegularExpression is PySide6/Qt6 feature.
            from PySide6.QtCore import QRegularExpression
            re_flags = QRegularExpression.PatternOption.NoPatternOption
            if not case:
                re_flags |= QRegularExpression.PatternOption.CaseInsensitiveOption
            
            rx = QRegularExpression(query, re_flags)
            found = self.find(rx, flags)
        else:
            found = self.find(query, flags)
            
        if not found:
            # Wrap around
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
        cursor = self.textCursor()
        if not cursor.hasSelection():
            self._find_next(query, case, whole, regex)
            return

        # Check if selection matches query
        selected = cursor.selectedText()
        match = False
        if regex:
            import re
            re_flags = 0 if case else re.IGNORECASE
            if re.fullmatch(query, selected, flags=re_flags):
                match = True
        else:
            if case:
                match = (selected == query)
            else:
                match = (selected.lower() == query.lower())
                
        if match:
            cursor.insertText(replace_text)
            self._find_next(query, case, whole, regex)
        else:
            self._find_next(query, case, whole, regex)

    def _replace_all(self, query: str, replace_text: str, case: bool, whole: bool, regex: bool) -> None:
        # Save current position
        old_cursor = self.textCursor()
        
        # Start from beginning
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        
        count = 0
        while self._find_next(query, case, whole, regex):
            self.textCursor().insertText(replace_text)
            count += 1
            
        # Restore cursor if possible
        self.setTextCursor(old_cursor)

    # ── View Mode ─────────────────────────────────────────────────

    def set_view_mode(self, enabled: bool) -> None:
        """Update state internal editor (dipanggil dari EditorTab)."""
        self._read_only = enabled
        self.setReadOnly(enabled)

    def _request_view_mode(self, enabled: bool) -> None:
        """
        Minta parent EditorTab untuk toggle view/edit mode.
        Jika parent bukan EditorTab (mis. test), fallback ke self.set_view_mode.
        """
        parent = self.parent()
        # Naik terus sampai menemukan EditorTab atau None
        while parent is not None:
            if hasattr(parent, "set_view_mode") and hasattr(parent, "_stack"):
                parent.set_view_mode(enabled)
                return
            parent = parent.parent() if hasattr(parent, "parent") else None
        # Fallback
        self.set_view_mode(enabled)

    def _has_image_in_clipboard(self) -> bool:
        clipboard = QApplication.clipboard()
        if not clipboard.image().isNull():
            return True
        mime = clipboard.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    ext = url.toLocalFile().lower().rsplit(".", 1)[-1]
                    if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
                        return True
        return False




# =========================================================================
# MarkdownPreview
# =========================================================================

# CSS bawaan untuk tampilan preview yang rapi
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
/* Paragraphs */
p { margin: 0 0 1em; }
/* Links */
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
/* Bold / Italic */
strong { font-weight: 600; }
/* Blockquote */
blockquote {
  margin: 1em 0;
  padding: .5em 1em;
  color: var(--muted);
  background: var(--bq-bg);
  border-left: .25em solid var(--bq-border);
  border-radius: 0 4px 4px 0;
}
blockquote p { margin: 0; }
/* Lists */
ul, ol { padding-left: 2em; margin: 0 0 1em; }
li + li { margin-top: .25em; }
/* Inline code */
code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: .9em;
  background: var(--code-bg);
  padding: .1em .35em;
  border-radius: 3px;
  border: 1px solid var(--border);
}
/* Code block */
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
/* Horizontal rule */
hr {
  border: none;
  border-top: 2px solid var(--border);
  margin: 1.5em 0;
}
/* Tables */
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
/* Image */
img { max-width: 100%; height: auto; border-radius: 4px; }
/* Wiki-link [[...]] → badge link */
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
  text-decoration: none;
}
/* Citation @key */
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
    "extra",          # tables, footnotes, attr_list, def_list, abbr
    "fenced_code",    # ``` code blocks
    "nl2br",          # newline → <br>
    "sane_lists",     # list behaviour yang benar
    "toc",            # heading anchors
]


def _md_to_html(text: str, base_url: str = "", theme: str = "light") -> str:
    """
    Konversi teks Markdown ke HTML lengkap dengan CSS bawaan.
    Jika markdown library tidak tersedia, kembalikan teks plain dalam <pre>.
    Juga menerapkan highlighting untuk [[wiki-link]] dan @citation.
    """
    import re
    from noteration.ui.theme import ThemeMode, _DARK_COLORS, _LIGHT_COLORS, get_syntax_palette, get_effective_mode

    mode = get_effective_mode(theme)
    palette = get_syntax_palette(mode)
    base_colors = _DARK_COLORS if mode == ThemeMode.DARK else _LIGHT_COLORS

    # Map colors to CSS variables
    def get_hex(role): return base_colors.get(role, "#000000")
    
    css_vars = f"""
    :root {{
      --bg:      {get_hex(QPalette.ColorRole.Base)};
      --text:    {get_hex(QPalette.ColorRole.Text)};
      --muted:   {get_hex(QPalette.ColorRole.PlaceholderText)};
      --border:  {get_hex(QPalette.ColorRole.Mid)};
      --code-bg: {palette.get("code_block", ("","#f6f8fa"))[1]};
      --link:    {get_hex(QPalette.ColorRole.Link)};
      --bq-border: {get_hex(QPalette.ColorRole.Highlight)};
      --bq-bg:   {palette.get("quote", ("","#f9f9f9"))[1]};
      --wiki-bg: {palette.get("wiki", ("","#EEEDFE"))[1]};
      --wiki-fg: {palette.get("wiki", ("#534AB7",""))[0]};
      --cite-bg: {palette.get("citation", ("","#E1F5EE"))[1]};
      --cite-fg: {palette.get("citation", ("#0F6E56",""))[0]};
    }}
    """
    
    if _HAS_MARKDOWN:
        body = _markdown_lib.markdown(
            text, extensions=_MARKDOWN_EXTENSIONS,
        )
    else:
        import html as _html
        body = f"<pre>{_html.escape(text)}</pre>"

    def _safe_replace(html: str) -> str:
        parts = re.split(r'(<code.*?>.*?</code>|<pre.*?>.*?</pre>)', html, flags=re.DOTALL)
        
        def _wikilink_sub(m: re.Match) -> str:
            target = m.group(1).strip()
            href = "noteration://wiki/" + target.replace(" ", "%20")
            return f'<a class="wikilink" href="{href}" title="Note: {target}">[[{target}]]</a>'

        new_parts = []
        for p in parts:
            if p.startswith(('<code', '<pre')):
                new_parts.append(p)
            else:
                p = re.sub(r'\[\[([^\]]+)\]\]', _wikilink_sub, p)
                p = re.sub(
                    r'(@[A-Za-z][A-Za-z0-9_:\-]+)',
                    r'<span class="citation">\1</span>',
                    p,
                )
                new_parts.append(p)
        return "".join(new_parts)

    body = _safe_replace(body)

    base_tag = f'<base href="{base_url}">' if base_url else ""
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {base_tag}
  <style>
    {_PREVIEW_CSS}
    {css_vars}
  </style>
</head>
<body>
{body}
</body>
</html>"""


if _HAS_WEBENGINE:
    class _NoterationPage(QWebEnginePage):
        """
        Custom WebEnginePage yang mencegat semua navigasi:
        - noteration://wiki/<target>  → emit link_clicked, blok
        - http / https / ftp          → buka xdg-open, blok
        - about:blank / file://       → izinkan (setHtml internal)
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

            # Jika bukan klik link (misal setHtml internal), izinkan
            if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                return True

            if scheme == "noteration":
                # noteration://wiki/<target>
                if url.host() == "wiki":
                    target = url.path().lstrip("/")
                    self.link_clicked.emit(target)
                return False  # blok navigasi

            if scheme in ("http", "https", "ftp"):
                import subprocess
                subprocess.Popen(["xdg-open", url_str])
                return False  # blok navigasi di webview

            return False  # blok semua lainnya


class MarkdownPreview(QWidget):
    """
    Widget preview Markdown menggunakan QWebEngineView.
    Fallback ke QTextBrowser jika WebEngine tidak tersedia.

    API publik:
      set_content(markdown_text, base_path)  — render teks baru
    Signal:
      link_clicked(str)  — target wiki-link diklik
    """

    link_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Cek apakah dipaksa pakai QTextBrowser (untuk kompatibilitas hardware)
        force_text = os.environ.get("NOTERATION_USE_TEXT_BROWSER") == "1"

        if _HAS_WEBENGINE and not force_text:
            self._view = QWebEngineView()
            self._page = _NoterationPage(self)
            self._page.link_clicked.connect(self.link_clicked)
            self._view.setPage(self._page)
            
            # Disable context menu to keep it clean
            self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self._view.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            
            layout.addWidget(self._view)
            self._use_webengine = True
        else:
            # Use QTextBrowser for reliable rendering across all environments
            from PySide6.QtWidgets import QTextBrowser
            self._tb = QTextBrowser()
            self._tb.setOpenExternalLinks(False)
            self._tb.setOpenLinks(False)
            self._tb.anchorClicked.connect(self._on_tb_anchor)
            self._tb.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            layout.addWidget(self._tb)
            self._use_webengine = False

    def _on_tb_anchor(self, url: QUrl) -> None:
        """Handler klik link di QTextBrowser fallback."""
        scheme = url.scheme()
        if scheme == "noteration" and url.host() == "wiki":
            self.link_clicked.emit(url.path().lstrip("/"))
        elif scheme in ("http", "https"):
            import subprocess
            subprocess.Popen(["xdg-open", url.toString()])

    def set_content(self, markdown_text: str, base_path: Path | None = None, theme: str = "light") -> None:
        """Render markdown_text dan tampilkan."""
        base_url = QUrl()
        if base_path and base_path.exists():
            if base_path.is_dir():
                # Jika base_path adalah direktori (vault_path), gunakan langsung
                base_dir = str(base_path)
            else:
                # Jika base_path adalah file (file_path), gunakan parent-nya
                base_dir = str(base_path.parent)
            
            if not base_dir.endswith("/"):
                base_dir += "/"
            base_url = QUrl.fromLocalFile(base_dir)

        html = _md_to_html(markdown_text, base_url.toString(), theme=theme)

        if self._use_webengine:
            self._page.setHtml(html, base_url)
        else:
            self._tb.setHtml(html)

# =========================================================================
# EditorTab
# =========================================================================

class EditorTab(QWidget):
    """
    Tab editor Markdown lengkap (Phase 3).

    Signals
    -------
    cursor_moved(line, col)
    content_changed()
    wiki_link_clicked(target)
    headings_changed([(level, title), ...])   — debounced
    citations_changed([key, ...])             — debounced
    word_count_changed(int)                   — debounced
    """

    cursor_moved       = Signal(int, int)
    content_changed    = Signal()
    wiki_link_clicked  = Signal(str)
    headings_changed   = Signal(list)
    citations_changed  = Signal(list)
    word_count_changed = Signal(int)

    def __init__(
        self,
        file_path: Path,
        vault_path: Path,
        config: NoterationConfig,
        papis_bridge=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.file_path   = file_path
        self.vault_path  = vault_path
        self.config      = config
        self.is_modified = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar atas per-tab ──────────────────────────────────────
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
        self._act_edit.setToolTip("Mode edit — Ctrl+Shift+V")
        self._act_edit.triggered.connect(lambda: self.set_view_mode(False))

        self._act_view = self._tab_toolbar.addAction("👁  View")
        self._act_view.setCheckable(True)
        self._act_view.setChecked(False)
        self._act_view.setToolTip("Mode preview render — Ctrl+Shift+V")
        self._act_view.triggered.connect(lambda: self.set_view_mode(True))

        # Pastikan hanya satu yang aktif
        _grp = QActionGroup(self._tab_toolbar)
        _grp.setExclusive(True)
        _grp.addAction(self._act_edit)
        _grp.addAction(self._act_view)

        layout.addWidget(self._tab_toolbar)

        # Stack: index 0 = editor, index 1 = preview
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self._editor = MarkdownEditor(config)
        self._editor.wiki_link_activated.connect(self.wiki_link_clicked)
        self._editor.cursorPositionChanged.connect(self._on_cursor_moved)
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.image_dropped.connect(self._on_image_dropped)
        self._editor.image_pasted.connect(self._on_image_pasted)
        self._stack.addWidget(self._editor)        # index 0

        self._preview = MarkdownPreview()
        self._preview.link_clicked.connect(self._on_preview_link)
        self._stack.addWidget(self._preview)       # index 1
        self._stack.setCurrentIndex(0)             # mulai di mode edit

        self._is_view_mode = False

        # Apply initial theme palette to highlighter
        self._update_highlighter_theme()

        # Debounce 300 ms untuk sidebar update
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit_parsed_signals)

        # Citation autocomplete
        self._completer = None
        if papis_bridge:
            try:
                from noteration.editor.citation_completer import CitationCompleter
                self._completer = CitationCompleter(
                    self._editor, papis_bridge, self)
            except Exception:
                pass   # graceful: jika PySide6 completer gagal


        # Shortcut Ctrl+Shift+V: toggle View/Edit mode
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

    # ── File I/O ──────────────────────────────────────────────────────

    def _load_file(self) -> None:
        if self.file_path.exists():
            text = self.file_path.read_text(encoding="utf-8")
            self._editor.setPlainText(text)
        self.is_modified = False
        self._emit_parsed_signals()

    def save(self) -> None:
        self.file_path.write_text(
            self._editor.toPlainText(), encoding="utf-8")
        self.is_modified = False

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._editor.set_line_numbers_visible(visible)

    # ── View / Edit mode ──────────────────────────────────────────────

    def set_view_mode(self, enabled: bool) -> None:
        """
        Toggle antara mode edit (QPlainTextEdit) dan mode preview (render HTML).
        Dipanggil dari toolbar, context menu, atau shortcut Ctrl+Shift+V.
        """
        from PySide6.QtWidgets import QApplication
        self._is_view_mode = enabled
        self._act_edit.setChecked(not enabled)
        self._act_view.setChecked(enabled)
        if enabled:
            self._stack.setCurrentIndex(1)
            self._refresh_preview()
            QApplication.processEvents()
        else:
            self._stack.setCurrentIndex(0)
            self._editor.setFocus()

    def _refresh_preview(self) -> None:
        """Render ulang markdown ke HTML dan kirim ke MarkdownPreview."""
        self._preview.set_content(
            self._editor.toPlainText(),
            base_path=self.vault_path,
            theme=self.config.theme,
        )

    def _on_preview_link(self, target: str) -> None:
        """
        Terima target wiki-link yang sudah diekstrak oleh _NoterationPage
        (atau QTextBrowser fallback) dan teruskan ke main_window.
        Signal link_clicked dari MarkdownPreview sudah berisi target bersih
        (bukan full URL), sehingga tidak perlu parsing di sini.
        """
        if target:
            self.wiki_link_clicked.emit(target)

    # ── Insert helpers ────────────────────────────────────────────────

    def insert_text(self, text: str) -> None:
        self._editor.insertPlainText(text)

    def insert_quote(self, text: str, citation_key: str) -> None:
        """Sisipkan kutipan PDF sebagai Markdown blockquote."""
        lines = text.strip().splitlines()
        bq = "\n".join(f"> {ln}" for ln in lines)
        bq += f"\n> — @{citation_key}\n\n"
        self._editor.insertPlainText(bq)

    def insert_image(self, rel_path: str) -> None:
        md = f"![]({rel_path})\n\n"
        self._editor.insertPlainText(md)

    def _on_image_dropped(self, source_path: str) -> None:
        from pathlib import Path
        import shutil

        src = Path(source_path)
        if not src.exists():
            return

        attachments_dir = self.vault_path / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:6]
        ext = src.suffix
        filename = f"{ts}_{uid}{ext}"
        dest = attachments_dir / filename

        shutil.copy2(src, dest)

        rel_path = Path("attachments") / filename
        self.insert_image(str(rel_path))

    def _on_image_pasted(self, image) -> None:
        """Handle pasted image from clipboard."""
        from PySide6.QtGui import QImage
        if isinstance(image, QImage):
            self._paste_image_from_clipboard(image)

    def _paste_image_from_clipboard(self, image: "QImage") -> None:
        """Save pasted image to attachments and insert markdown."""
        
        attachments_dir = self.vault_path / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:6]
        filename = f"{ts}_{uid}.png"
        dest = attachments_dir / filename
        
        image.save(str(dest))  # Format deduced from file extension
        
        rel_path = Path("attachments") / filename
        self.insert_image(str(rel_path))

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
        # Cari @key (case insensitive agar lebih toleran)
        pattern = f"@{re.escape(key)}\\b"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            cursor = self._editor.textCursor()
            cursor.setPosition(match.start())
            self._editor.setTextCursor(cursor)
            self._editor.setFocus()

    def _open_find_replace(self) -> None:
        """Buka dialog Find/Replace."""
        if not hasattr(self, '_find_replace_dlg'):
            self._find_replace_dlg = FindReplaceDialog(self)
            self._find_replace_dlg.find_next_requested.connect(self._on_find_next)
            self._find_replace_dlg.replace_requested.connect(self._on_replace)
            self._find_replace_dlg.replace_all_requested.connect(self._on_replace_all)
        # Pre-fill dengan teks terpilih
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            self._find_replace_dlg.set_initial_text(cursor.selectedText())
        self._find_replace_dlg.show()
        self._find_replace_dlg.raise_()
        self._find_replace_dlg.activateWindow()

    def _on_find_next(self, query: str, case: bool, whole: bool, regex: bool) -> None:
        """Handle find next request."""
        doc = self._editor.document()
        cursor = self._editor.textCursor()
        start_pos = cursor.position()
        flags = QTextDocument.FindFlag(0)
        if case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole:
            flags |= QTextDocument.FindFlag.FindWholeWords
        # Pencarian maju dari posisi kursor
        new_cursor = doc.find(query, start_pos, flags)
        if new_cursor.isNull():
            # Wrap around: cari dari awal dokumen
            new_cursor = doc.find(query, 0, flags)
        if not new_cursor.isNull():
            self._editor.setTextCursor(new_cursor)
            self._editor.setFocus()

    def _on_replace(self, query: str, replace_text: str, case: bool, whole: bool, regex: bool) -> None:
        """Handle replace request."""
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            # Cek apakah teks terpilih cocok
            import re as _re
            flags = 0
            if not case:
                flags |= _re.IGNORECASE
            if whole:
                query = r'\b' + query + r'\b'
            if regex or _re.search(query, selected, flags):
                cursor.insertText(replace_text)
        # Lanjutkan ke match berikutnya
        self._on_find_next(query, case, whole, regex)

    def _on_replace_all(self, query: str, replace_text: str, case: bool, whole: bool, regex: bool) -> None:
        """Handle replace all request."""
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
            self._editor.document().setModified(True)
            self.is_modified = True
            self.content_changed.emit()

    def current_text(self) -> str:
        return self._editor.toPlainText()

    # ── Parsed data ───────────────────────────────────────────────────

    def headings(self) -> list[tuple[int, str]]:
        return extract_headings(self._editor.toPlainText())

    def citation_keys(self) -> list[str]:
        return [c.key for c in parse_citations(self._editor.toPlainText())]

    def word_count(self) -> int:
        text = self._editor.toPlainText()
        text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
        text = re.sub(r'```.*?```',        '', text, flags=re.DOTALL)
        text = re.sub(r'`[^`]+`',          '', text)
        return len(re.findall(r'\b\w+\b', text))

    # ── Signals ───────────────────────────────────────────────────────

    def _on_cursor_moved(self) -> None:
        c = self._editor.textCursor()
        self.cursor_moved.emit(c.blockNumber() + 1, c.columnNumber() + 1)

    def _on_text_changed(self) -> None:
        self.is_modified = True
        self.content_changed.emit()
        if hasattr(self, '_debounce') and self._debounce:
            self._debounce.start()

    def _emit_parsed_signals(self) -> None:
        self.headings_changed.emit(self.headings())
        self.citations_changed.emit(self.citation_keys())
        self.word_count_changed.emit(self.word_count())

    def closeEvent(self, event) -> None:
        if hasattr(self, '_debounce') and self._debounce:
            self._debounce.stop()
        super().closeEvent(event)
