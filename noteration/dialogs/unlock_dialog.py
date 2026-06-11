"""Provide the dialog for unlocking encrypted vaults.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout


class UnlockDialog(QDialog):
    """Display a dialog to prompt the user for the private key to unlock a vault.
    """

    def __init__(self, vault_path: Path, parent=None) -> None:
        """Initialize the unlock dialog for the specified vault."""
        super().__init__(parent)
        self.vault_path = vault_path
        self.setWindowTitle("Unlock Vault")
        self.resize(400, 200)

        self.private_key = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI for the unlock dialog."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        layout.addWidget(QLabel(f"🔒 <b>{self.vault_path.name}</b> is encrypted."))
        layout.addWidget(QLabel("Please enter your age-private-key to unlock:"))

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("AGE-SECRET-KEY-1...")
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._key_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self) -> None:
        """Validate the key and accept the dialog."""
        self.private_key = self._key_edit.text().strip()
        if not self.private_key.startswith("AGE-SECRET-KEY-1"):
            QMessageBox.warning(
                self, "Invalid Key", "The provided key does not look like a valid age private key."
            )
            return
        self.accept()

    def get_key(self) -> str:
        """Return the entered private key."""
        return self.private_key
