"""
Find and Replace dialog for the Markdown editor.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QLabel, QPushButton, QCheckBox, QGroupBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut


class FindReplaceDialog(QDialog):
    """Dialog for finding and replacing text in the editor."""

    find_next_requested = Signal(str, bool, bool, bool)
    replace_requested = Signal(str, str, bool, bool, bool)
    replace_all_requested = Signal(str, str, bool, bool, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Find and Replace")
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._setup_ui()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Find row
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("Find:"))
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Text to find...")
        self._find_input.setClearButtonEnabled(True)
        find_layout.addWidget(self._find_input)
        layout.addLayout(find_layout)

        # Replace row
        replace_layout = QHBoxLayout()
        replace_layout.addWidget(QLabel("Replace:"))
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replacement text...")
        self._replace_input.setClearButtonEnabled(True)
        replace_layout.addWidget(self._replace_input)
        layout.addLayout(replace_layout)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QHBoxLayout(options_group)
        
        self._case_cb = QCheckBox("Case sensitive")
        self._whole_cb = QCheckBox("Whole words")
        self._regex_cb = QCheckBox("Regex")
        
        options_layout.addWidget(self._case_cb)
        options_layout.addWidget(self._whole_cb)
        options_layout.addWidget(self._regex_cb)
        layout.addWidget(options_group)

        # Buttons
        btn_layout = QHBoxLayout()
        
        self._find_btn = QPushButton("Find Next")
        self._find_btn.setDefault(True)
        self._find_btn.clicked.connect(self._on_find_next)
        
        self._replace_btn = QPushButton("Replace")
        self._replace_btn.clicked.connect(self._on_replace)
        
        self._replace_all_btn = QPushButton("Replace All")
        self._replace_all_btn.clicked.connect(self._on_replace_all)
        
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.close)
        
        btn_layout.addWidget(self._find_btn)
        btn_layout.addWidget(self._replace_btn)
        btn_layout.addWidget(self._replace_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._close_btn)
        
        layout.addLayout(btn_layout)

        self._find_input.setFocus()

    def _setup_shortcuts(self) -> None:
        # Escape to close
        QShortcut(QKeySequence("Escape"), self).activated.connect(self.close)
        # Enter in find input triggers Find Next
        self._find_input.returnPressed.connect(self._on_find_next)
        # Enter in replace input triggers Replace
        self._replace_input.returnPressed.connect(self._on_replace)

    def _on_find_next(self) -> None:
        query = self._find_input.text()
        if not query:
            return
        self.find_next_requested.emit(
            query,
            self._case_cb.isChecked(),
            self._whole_cb.isChecked(),
            self._regex_cb.isChecked()
        )

    def _on_replace(self) -> None:
        query = self._find_input.text()
        replace_text = self._replace_input.text()
        if not query:
            return
        self.replace_requested.emit(
            query,
            replace_text,
            self._case_cb.isChecked(),
            self._whole_cb.isChecked(),
            self._regex_cb.isChecked()
        )

    def _on_replace_all(self) -> None:
        query = self._find_input.text()
        replace_text = self._replace_input.text()
        if not query:
            return
        self.replace_all_requested.emit(
            query,
            replace_text,
            self._case_cb.isChecked(),
            self._whole_cb.isChecked(),
            self._regex_cb.isChecked()
        )

    def set_initial_text(self, text: str) -> None:
        """Set initial find text (e.g. from selection)."""
        if text:
            self._find_input.setText(text)
            self._find_input.selectAll()
