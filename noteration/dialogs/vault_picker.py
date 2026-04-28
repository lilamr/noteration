"""
noteration/dialogs/vault_picker.py
Dialog startup untuk memilih atau membuat vault penelitian.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QFileDialog, QMessageBox,
    QMenu,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

# Tempat menyimpan daftar vault yang pernah dibuka
_VAULTS_FILE = Path.home() / ".noteration" / "vaults.toml"


def _load_known_vaults() -> list[dict]:
    """Muat daftar vault dari ~/.noteration/vaults.toml."""
    if not _VAULTS_FILE.exists():
        return []
    try:
        import sys
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib  # type: ignore
        with open(_VAULTS_FILE, "rb") as f:
            data = tomllib.load(f)
        return data.get("vaults", [])
    except Exception:
        return []


def _save_vault(vault_path: Path, name: str) -> None:
    """Tambahkan vault baru ke daftar."""
    _VAULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    vaults = _load_known_vaults()
    paths = [v.get("path", "") for v in vaults]
    if str(vault_path) not in paths:
        vaults.append({"name": name, "path": str(vault_path)})
    try:
        import tomli_w
        with open(_VAULTS_FILE, "wb") as f:
            tomli_w.dump({"vaults": vaults}, f)
    except ImportError:
        pass


def _remove_vault(vault_path: Path) -> None:
    """Hapus vault dari daftar."""
    _VAULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    vaults = _load_known_vaults()
    vaults = [v for v in vaults if v.get("path") != str(vault_path)]
    try:
        import tomli_w
        with open(_VAULTS_FILE, "wb") as f:
            tomli_w.dump({"vaults": vaults}, f)
    except ImportError:
        pass


class VaultPickerDialog(QDialog):
    """
    Dialog yang muncul saat aplikasi pertama kali dibuka.
    Pengguna memilih vault yang ada atau membuat vault baru.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Noteration — Pilih Vault")
        self.setFixedSize(480, 380)
        self._selected_vault: Path | None = None
        self._setup_ui()
        self._populate_vaults()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        title = QLabel("Noteration")
        title.setFont(QFont("Georgia", 20, QFont.Weight.DemiBold))
        subtitle = QLabel("Pilih vault penelitian untuk dibuka, atau buat vault baru.")
        subtitle.setStyleSheet("color: gray;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # List vault
        self._list = QListWidget()
        self._list.setIconSize(QSize(32, 32))
        self._list.setAlternatingRowColors(True)
        self._list.doubleClicked.connect(self._open_selected)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._list)

        # Tombol aksi
        btn_row = QHBoxLayout()

        self._btn_browse = QPushButton("Cari Vault…")
        self._btn_browse.clicked.connect(self._browse_vault)
        btn_row.addWidget(self._btn_browse)

        self._btn_new = QPushButton("Buat Baru…")
        self._btn_new.clicked.connect(self._create_vault)
        btn_row.addWidget(self._btn_new)

        btn_row.addStretch()

        self._btn_open = QPushButton("Buka")
        self._btn_open.setDefault(True)
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_selected)
        btn_row.addWidget(self._btn_open)

        layout.addLayout(btn_row)

        self._list.currentItemChanged.connect(
            lambda cur, _: self._btn_open.setEnabled(cur is not None)
        )

    # ------------------------------------------------------------------
    # Vault list
    # ------------------------------------------------------------------

    def _populate_vaults(self) -> None:
        self._list.clear()
        vaults = _load_known_vaults()
        for v in vaults:
            name = v.get("name", "Unnamed")
            path = v.get("path", "")
            item = QListWidgetItem(f"  {name}\n  {path}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._list.addItem(item)

        if self._list.count():
            self._list.setCurrentRow(0)

    def _show_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        menu = QMenu(self)
        act_open = menu.addAction("Buka Vault")
        menu.addSeparator()
        act_remove = menu.addAction("Hapus dari Daftar")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen == act_remove:
            self._remove_vault_item(path)
        elif chosen == act_open:
            self._open_selected()

    def _remove_vault_item(self, path: str) -> None:
        reply = QMessageBox.question(
            self, "Hapus Vault",
            f"Hapus vault ini dari daftar?\n\n{path}\n\n(Direktori tidak akan dihapus)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            _remove_vault(Path(path))
            self._populate_vaults()

    # ------------------------------------------------------------------
    # Aksi
    # ------------------------------------------------------------------

    def _browse_vault(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Pilih Direktori Vault", str(Path.home())
        )
        if path:
            vault_path = Path(path)
            # Tebak nama dari folder
            name = vault_path.name.replace("-", " ").replace("_", " ").title()
            _save_vault(vault_path, name)
            self._populate_vaults()

    def _create_vault(self) -> None:
        from noteration.dialogs.new_vault import NewVaultDialog
        dlg = NewVaultDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vault_path, name = dlg.result_vault()
            self._init_vault(vault_path, name)
            _save_vault(vault_path, name)
            self._populate_vaults()

    def _init_vault(self, vault_path: Path, name: str) -> None:
        """Buat struktur direktori vault baru."""
        for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
            (vault_path / sub).mkdir(parents=True, exist_ok=True)

    def _open_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not Path(path).exists():
            QMessageBox.warning(self, "Tidak ditemukan", f"Direktori tidak ditemukan:\n{path}")
            return
        self._selected_vault = Path(path)
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_vault(self) -> Path:
        assert self._selected_vault is not None
        return self._selected_vault
