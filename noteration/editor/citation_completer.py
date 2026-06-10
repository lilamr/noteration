"""noteration/editor/citation_completer.py

Papis-based QCompleter for @citation autocomplete in the editor.
Activated when the user types '@' in MarkdownEditor.
"""

from __future__ import annotations

import re

from PySide6.QtWidgets import QCompleter
from PySide6.QtCore import Qt, QStringListModel, Signal, QObject
from PySide6.QtGui import QTextCursor

from noteration.literature.papis_bridge import PapisBridge


class CitationCompleter(QObject):
    """Controller for @citation autocomplete.
    Attaches to QPlainTextEdit; listens to textChanged and displays
    the QCompleter dropdown when the current word starts with '@'.
    """

    citation_inserted = Signal(str)  # The selected key

    # Regex to detect @word token at the end of a line prefix
    _AT_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_:\-]*)$")

    def __init__(self, editor, bridge: PapisBridge, parent=None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._bridge = bridge
        self._keys: list[str] = []  # Original keys (undecorated)
        self._display: list[str] = []  # Strings displayed in the popup

        # Model & completer setup
        self._model = QStringListModel()
        self._completer = QCompleter(self._model, self._editor)
        self._completer.setWidget(self._editor)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.activated.connect(self._on_activated)

        # Load keys immediately during initialization
        self.refresh_keys()

        # Connect to the editor
        self._editor.textChanged.connect(self._on_text_changed)

    # ── Public API ────────────────────────────────────────────────────

    def refresh_keys(self) -> None:
        """Reload all keys from the bridge.
        Called after a new document is added to the library.
        """
        entries = self._bridge.all_entries(force_reload=True)
        self._keys = [e.key for e in entries]
        self._display = [
            f"@{e.key}  —  {e.title[:60]}" if e.title else f"@{e.key}" for e in entries
        ]
        self._model.setStringList(self._display)

    # ── Text change detection ─────────────────────────────────────────

    def _on_text_changed(self) -> None:
        cursor = self._editor.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        prefix = block_text[:col]

        m = self._AT_RE.search(prefix)
        if m:
            partial = m.group(1)
            self._show_completion(partial, cursor)
        else:
            popup = self._completer.popup()
            if popup and popup.isVisible():
                popup.hide()

    def _show_completion(self, partial: str, cursor: QTextCursor) -> None:
        self._completer.setCompletionPrefix(partial)
        if self._completer.completionCount() == 0:
            popup = self._completer.popup()
            if popup:
                popup.hide()
            return

        rect = self._editor.cursorRect(cursor)
        popup = self._completer.popup()
        if popup:
            rect.setWidth(
                popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 8
            )
        self._completer.complete(rect)

    # ── Selection handler ─────────────────────────────────────────────

    def _on_activated(self, text: str) -> None:
        """Insert '@key' replacing the typed '@partial'.
        `text` is the display string: "@Key2023  —  Title" or "@Key2023".
        """
        # Safely extract key from the display string
        raw = text.split("  —  ")[0].strip()
        key = raw.lstrip("@").strip()
        if not key:
            return

        cursor = self._editor.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()

        m = self._AT_RE.search(block_text[:col])
        if m:
            # Remove the typed "@partial"
            remove_start = cursor.position() - len(m.group(0))
            cursor.setPosition(remove_start)
            cursor.setPosition(
                remove_start + len(m.group(0)),
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()

        cursor.insertText(f"@{key}")
        self._editor.setTextCursor(cursor)
        self.citation_inserted.emit(key)
