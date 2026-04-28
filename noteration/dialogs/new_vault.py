"""
noteration/dialogs/new_vault.py
Dialog untuk membuat vault baru.
"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QHBoxLayout, QFileDialog
)

class NewVaultDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Buat Vault Baru")
        self.resize(400, 180)
        self._vault: tuple[Path, str] | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nama vault:"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("contoh: Penelitian Kehutanan")
        layout.addWidget(self._name)

        layout.addWidget(QLabel("Lokasi:"))
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
        ok = QPushButton("Buat")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Batal")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pilih Lokasi Vault")
        if path:
            self._path_input.setText(path)

    def _accept(self) -> None:
        name = self._name.text().strip() or "Vault Baru"
        raw = self._path_input.text().strip() or str(Path.home() / "noteration" / name.lower().replace(" ", "-"))
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        self._vault = (path, name)
        self.accept()

    def result_vault(self) -> tuple[Path, str]:
        assert self._vault is not None
        return self._vault
