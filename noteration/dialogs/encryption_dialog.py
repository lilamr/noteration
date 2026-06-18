"""Provide the dialog for managing vault encryption using age.

This module contains the `EncryptionDialog` and supporting `EncryptionWorker`
to handle the encryption of vault files, ensuring secure data management.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from noteration.config import NoterationConfig
from noteration.logger import get_logger
from noteration.utils.encryption import encrypt_file, generate_keypair, is_age_available
from noteration.utils.qt_helpers import BaseWorker

logger = get_logger(__name__)


class EncryptionWorker(BaseWorker):
    """Handle the encryption of vault files in a background thread.
    """

    finished = Signal(bool, str)
    progress = Signal(int, int)

    def __init__(self, vault_path: Path, public_key: str) -> None:
        """Initialize the encryption worker."""
        super().__init__()
        self.vault_path = vault_path
        self.public_key = public_key

    def run(self) -> None:
        """Perform the encryption of all files in the vault."""
        try:
            # 1. Collect all files to encrypt
            files_to_encrypt = []
            for subdir in ["notes", "literature", "annotations", "attachments"]:
                path = self.vault_path / subdir
                if path.exists():
                    for f in path.rglob("*"):
                        if f.is_file() and not f.suffix == ".age":
                            files_to_encrypt.append(f)

            total = len(files_to_encrypt)
            if total == 0:
                self.finished.emit(True, "No files found to encrypt.")
                return

            # 2. Encrypt each file
            for i, file_path in enumerate(files_to_encrypt):
                self.progress.emit(i + 1, total)

                encrypted_path = file_path.with_suffix(file_path.suffix + ".age")
                tmp_encrypted_path = encrypted_path.with_suffix(encrypted_path.suffix + ".tmp")

                # Encrypt to temporary .age file
                encrypt_file(file_path, self.public_key, tmp_encrypted_path)

                # Atomically replace/create the .age file
                tmp_encrypted_path.replace(encrypted_path)

                # Delete original
                file_path.unlink()

            self.finished.emit(True, f"Successfully encrypted {total} files.")
        except Exception as e:
            logger.error(f"Vault encryption failed: {e}")
            self.finished.emit(False, str(e))


class EncryptionDialog(QDialog):
    """Display the dialog to configure and execute vault encryption.
    """

    def __init__(self, vault_path: Path, config: NoterationConfig, parent=None) -> None:
        """Initialize the encryption dialog."""
        super().__init__(parent)
        self.vault_path = vault_path
        self.config = config
        self.setWindowTitle("Vault Encryption (age)")
        self.resize(500, 450)

        self.public_key = ""
        self.private_key = ""
        self._thread: Optional[QThread] = None
        self._worker: Optional[EncryptionWorker] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI for the encryption dialog."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 1. Header/Info
        title = QLabel("🛡️ Encrypt Research Vault")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "This will encrypt all notes, PDFs, and attachments in your vault using "
            "<b>age</b> encryption. Original files will be replaced with .age files."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        if not is_age_available():
            err = QLabel("❌ <b>Error:</b> 'age' tools not found in system PATH.")
            err.setStyleSheet("color: red;")
            layout.addWidget(err)
            btn_gen = QPushButton("Close")
            btn_gen.clicked.connect(self.reject)
            layout.addWidget(btn_gen)
            return

        # 2. Key Generation
        layout.addWidget(QLabel("<b>Step 1: Generate your Keys</b>"))

        btn_gen = QPushButton("Generate New Keypair")
        btn_gen.clicked.connect(self._generate_keys)
        layout.addWidget(btn_gen)

        # Public Key Display
        layout.addWidget(QLabel("Public Key (Stored in vault):"))
        self._pub_edit = QLineEdit()
        self._pub_edit.setReadOnly(True)
        layout.addWidget(self._pub_edit)

        # Private Key Display
        layout.addWidget(QLabel("<b>Private Key (SAVE THIS SECURELY!):</b>"))
        self._priv_edit = QTextEdit()
        self._priv_edit.setReadOnly(True)
        self._priv_edit.setMaximumHeight(80)
        self._priv_edit.setStyleSheet("background: #FFF9C4; font-family: monospace;")
        layout.addWidget(self._priv_edit)

        warning = QLabel(
            "⚠️ <b>WARNING:</b> If you lose your private key, you will LOSE ACCESS "
            "to your research data forever. There is no password recovery."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #D32F2F;")
        layout.addWidget(warning)

        # 3. Confirmation
        self._chk_saved = QCheckBox(
            "I have saved my private key in a safe place (e.g. Password Manager)"
        )
        layout.addWidget(self._chk_saved)

        # 4. Action
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._btn_encrypt = QPushButton("🔒 Start Vault Encryption")
        self._btn_encrypt.setEnabled(False)
        self._btn_encrypt.setStyleSheet("padding: 10px; font-weight: bold;")
        self._btn_encrypt.clicked.connect(self._start_encryption)
        layout.addWidget(self._btn_encrypt)

        self._chk_saved.toggled.connect(
            lambda checked: self._btn_encrypt.setEnabled(checked and bool(self.public_key))
        )

    def _generate_keys(self) -> None:
        """Generate a new public/private keypair."""
        try:
            pub, priv = generate_keypair()
            self.public_key = pub
            self.private_key = priv
            self._pub_edit.setText(pub)
            self._priv_edit.setText(priv)
            self._btn_encrypt.setEnabled(self._chk_saved.isChecked())
        except Exception as e:
            QMessageBox.critical(self, "Key Generation Failed", str(e))

    def _start_encryption(self) -> None:
        """Initiate the vault encryption process."""
        reply = QMessageBox.warning(
            self,
            "Confirm Encryption",
            "Are you absolutely sure? This will replace your original files with encrypted versions.\n\n"
            "Make sure you have a backup before proceeding for the first time.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        self._btn_encrypt.setEnabled(False)
        self._progress.setVisible(True)

        # Start background thread
        self._thread = QThread(self)
        self._worker = EncryptionWorker(self.vault_path, self.public_key)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)

        self._thread.start()

    def _on_progress(self, current: int, total: int) -> None:
        """Update the progress bar."""
        self._progress.setMaximum(total)
        self._progress.setValue(current)

    def _on_finished(self, success: bool, message: str) -> None:
        """Handle completion of the encryption process."""
        if self._thread:
            self._thread.finished.connect(self._thread.deleteLater)
            if hasattr(self, "_worker") and self._worker:
                self._worker.deleteLater()
            self._thread.quit()
            self._thread = None
            self._worker = None
            # We don't wait anymore

        if success:
            # Mark vault as encrypted in config
            self.config.set("security", "encryption_enabled", True)
            self.config.set("security", "public_key", self.public_key)
            self.config.save()

            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.critical(self, "Encryption Failed", message)
            self.reject()
