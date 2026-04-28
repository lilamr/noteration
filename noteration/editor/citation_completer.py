"""
noteration/editor/citation_completer.py

QCompleter berbasis Papis untuk autocomplete @citation di editor.
Diaktifkan saat pengguna mengetik '@' di MarkdownEditor.

Perbaikan:
  - refresh_keys() dipanggil otomatis saat library berubah
  - Display string aman saat title kosong
  - Completion prefix diset ulang tiap ketik agar filter selalu akurat
  - _on_activated menangani format display string dengan benar
  - Tidak import re berulang di dalam method
"""

from __future__ import annotations

import re

from PySide6.QtWidgets import QCompleter
from PySide6.QtCore import Qt, QStringListModel, QTimer, Signal, QObject
from PySide6.QtGui import QTextCursor

from noteration.literature.papis_bridge import PapisBridge


class CitationCompleter(QObject):
    """
    Controller autocomplete @citation.
    Attach ke QPlainTextEdit; mendengarkan textChanged dan memunculkan
    QCompleter dropdown saat kata saat ini diawali '@'.
    """

    citation_inserted = Signal(str)   # key yang dipilih

    # Regex untuk mendeteksi token @word di akhir prefix baris
    _AT_RE = re.compile(r'@([A-Za-z]\w*)$')

    def __init__(self, editor, bridge: PapisBridge, parent=None) -> None:
        super().__init__(parent)
        self._editor  = editor
        self._bridge  = bridge
        self._keys:   list[str] = []      # key asli (tanpa dekorasi)
        self._display: list[str] = []     # string yang ditampilkan di popup

        # Model & completer
        self._model = QStringListModel()
        self._completer = QCompleter(self._model, self._editor)
        self._completer.setWidget(self._editor)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.activated.connect(self._on_activated)

        # Muat keys secara async agar tidak memblok UI saat init
        QTimer.singleShot(200, self.refresh_keys)

        # Hubungkan ke editor
        self._editor.textChanged.connect(self._on_text_changed)

    # ── Public API ────────────────────────────────────────────────────

    def refresh_keys(self) -> None:
        """
        Muat ulang semua key dari bridge.
        Dipanggil setelah dokumen baru ditambahkan ke library.
        """
        entries = self._bridge.all_entries(force_reload=True)
        self._keys = [e.key for e in entries]
        self._display = [
            f"@{e.key}  —  {e.title[:60]}" if e.title else f"@{e.key}"
            for e in entries
        ]
        self._model.setStringList(self._display)

    # ── Text change detection ─────────────────────────────────────────

    def _on_text_changed(self) -> None:
        cursor     = self._editor.textCursor()
        block_text = cursor.block().text()
        col        = cursor.positionInBlock()
        prefix     = block_text[:col]

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
                popup.sizeHintForColumn(0)
                + popup.verticalScrollBar().sizeHint().width()
                + 8
            )
        self._completer.complete(rect)

    # ── On selection ──────────────────────────────────────────────────

    def _on_activated(self, text: str) -> None:
        """
        Sisipkan '@key' menggantikan '@partial' yang sudah diketik.
        `text` adalah string display: "@Key2023  —  Title" atau "@Key2023".
        """
        # Ekstrak key dengan aman dari display string
        raw = text.split("  —  ")[0].strip()
        key = raw.lstrip("@").strip()
        if not key:
            return

        cursor     = self._editor.textCursor()
        block_text = cursor.block().text()
        col        = cursor.positionInBlock()

        m = self._AT_RE.search(block_text[:col])
        if m:
            # Hapus "@partial" yang sudah diketik
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
