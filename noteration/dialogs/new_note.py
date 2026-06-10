"""Provide the dialog for creating a new note.
"""

from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QHBoxLayout,
    QMessageBox,
)
from noteration.utils.path_safety import is_safe_path


class NewNoteDialog(QDialog):
    """Display the dialog for creating a new note within the vault.
    """

    def __init__(self, vault_path: Path, parent=None) -> None:
        """Initialize the new note dialog."""
        super().__init__(parent)
        self.vault_path = vault_path
        self._path: Path | None = None
        self.setWindowTitle("New Note")
        self.resize(360, 140)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Note name:"))
        self._input = QLineEdit()
        self._input.setPlaceholderText("e.g., methodology-sampling")
        layout.addWidget(self._input)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Create")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _accept(self) -> None:
        """Validate input and create the new note."""
        name = self._input.text().strip()
        if not name:
            return
        if not name.endswith(".md"):
            name += ".md"

        # name could be "folder/note.md"
        potential_path = (self.vault_path / "notes" / name).resolve()

        if not is_safe_path(self.vault_path / "notes", potential_path):
            QMessageBox.critical(self, "Error", "Invalid note name (path traversal attempted).")
            return

        self._path = potential_path
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if not self._path.exists():
                self._path.write_text(f"# {self._path.stem}\n\n", encoding="utf-8")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create note: {e}")

    def result_path(self) -> Path:
        """Return the path of the created note."""
        if self._path is None:
            raise RuntimeError("New note path requested before dialog completion.")
        return self._path
