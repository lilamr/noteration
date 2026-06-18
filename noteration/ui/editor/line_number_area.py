"""noteration/ui/editor/line_number_area.py

Small side panel for displaying line numbers in the editor.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from noteration.ui.editor.markdown_editor import MarkdownEditor


class LineNumberArea(QWidget):
    """Small side panel for displaying line numbers in the editor."""

    def __init__(self, editor: "MarkdownEditor") -> None:
        """Initialize the line number area."""
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        """Return the preferred size of the line number area."""
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint the line number area."""
        self._editor.line_number_area_paint_event(event)
