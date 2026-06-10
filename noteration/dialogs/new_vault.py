"""Provide the dialog for creating a new vault.
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
    QFileDialog,
)


class NewVaultDialog(QDialog):
    """Display the dialog for creating a new vault at a specified location.
    """

    def __init__(self, parent=None) -> None:
        """Initialize the new vault dialog."""
        super().__init__(parent)
        self.setWindowTitle("Create New Vault")
        self.resize(400, 180)
        self._vault: tuple[Path, str] | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Vault name:"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g., Forestry Research")
        layout.addWidget(self._name)

        layout.addWidget(QLabel("Location:"))
        loc_row = QHBoxLayout()
        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText(str(Path.home() / "noteration"))
        loc_row.addWidget(self._path_input)
        browse = QPushButton("…")
        browse.setFixedWidth(32)
        browse.clicked.connect(self._browse)
        loc_row.addWidget(browse)
        layout.addLayout(loc_row)

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

    def _browse(self) -> None:
        """Open a directory browser dialog to select the vault location."""
        path = QFileDialog.getExistingDirectory(self, "Select Vault Location")
        if path:
            self._path_input.setText(path)

    def _accept(self) -> None:
        """Validate input and create the directory for the new vault."""
        name = self._name.text().strip() or "New Vault"
        raw = self._path_input.text().strip() or str(
            Path.home() / "noteration" / name.lower().replace(" ", "-")
        )
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        self._vault = (path, name)
        self.accept()

    def result_vault(self) -> tuple[Path, str]:
        """Return the path and name of the created vault."""
        if self._vault is None:
            raise RuntimeError("Vault result requested before dialog completion.")
        return self._vault
