"""
Help dialog to display the user guide.
"""

from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt


class HelpDialog(QDialog):
    """Dialog that displays a Markdown file rendered as HTML."""

    def __init__(self, title: str, file_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        layout = QVBoxLayout(self)
        
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        layout.addWidget(self._browser)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._load_file(file_name)

    def _load_file(self, file_name: str) -> None:
        # Path to the doc file
        doc_path = Path(__file__).parent.parent / "docs" / file_name
        
        if not doc_path.exists():
            self._browser.setHtml(f"<h1>Error</h1><p>File '{file_name}' not found.</p>")
            return

        try:
            content = doc_path.read_text(encoding="utf-8")
            # We reuse the conversion logic from EditorTab
            from noteration.ui.editor_tab import _md_to_html
            
            # Use a dummy theme for the help dialog or detect from app
            html = _md_to_html(content, theme="light")
            self._browser.setHtml(html)
        except Exception as e:
            self._browser.setHtml(f"<h1>Error</h1><p>Failed to load '{file_name}': {str(e)}</p>")
