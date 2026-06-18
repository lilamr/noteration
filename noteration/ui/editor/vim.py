"""noteration/ui/editor/vim.py

Vim-mode support for the Markdown editor.
"""

from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit


class VimMode(Enum):
    NORMAL = "NORMAL"
    INSERT = "INSERT"
    VISUAL = "VISUAL"
    LINE_VISUAL = "LINE_VISUAL"
    COMMAND = "COMMAND"


class VimCommandField(QLineEdit):
    """Small command field for Vim-like commands (e.g., :w, :q)."""

    command_entered = Signal(str)
    esc_pressed = Signal()

    def __init__(self, parent=None) -> None:
        """Initialize the Vim command field."""
        super().__init__(parent)
        self.setPlaceholderText("Enter command (e.g., :w, :q)...")
        self.setStyleSheet(
            "QLineEdit { border: 1px solid palette(mid); padding: 4px; "
            " font-family: monospace; background: palette(base); }"
        )
        self.hide()

    def keyPressEvent(self, event) -> None:
        """Handle key press events for Vim commands."""
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
