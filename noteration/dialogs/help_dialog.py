"""Provide a help dialog to display the user guide.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from noteration.ui.editor_tab import MarkdownPreview


class HelpDialog(QDialog):
    """Display a Markdown file rendered as HTML in a dialog.
    """

    def __init__(self, title: str, file_name: str, parent=None) -> None:
        """Initialize the help dialog with the given title and file."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        layout = QVBoxLayout(self)

        self._preview = MarkdownPreview(self)
        layout.addWidget(self._preview)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._load_file(file_name)

    def _load_file(self, file_name: str) -> None:
        """Load and display the content of the specified Markdown file."""
        # Path to the doc file
        doc_path = Path(__file__).parent.parent / "docs" / file_name

        if not doc_path.exists():
            # Fallback to simple HTML if file is missing
            self._preview.set_content(f"# Error\n\nFile '{file_name}' not found.")
            return

        try:
            content = doc_path.read_text(encoding="utf-8")
            # Set content using the existing MarkdownPreview infrastructure
            self._preview.set_content(content, theme="light")
        except Exception as e:
            self._preview.set_content(f"# Error\n\nFailed to load '{file_name}': {str(e)}")
