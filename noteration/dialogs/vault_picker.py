"""Provide the startup dialog for choosing or creating a research vault.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from noteration.logger import get_logger

logger = get_logger(__name__)

# File to store the list of previously opened vaults
_VAULTS_FILE = Path.home() / ".noteration" / "vaults.toml"


def _load_known_vaults() -> list[dict]:
    """Load the vault list from ~/.noteration/vaults.toml."""
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
    """Add a new vault to the persistent list."""
    _VAULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    vaults = _load_known_vaults()
    paths = [v.get("path", "") for v in vaults]
    if str(vault_path) not in paths:
        vaults.append({"name": name, "path": str(vault_path)})
    try:
        import tomli_w

        # Atomic write
        tmp_path = _VAULTS_FILE.with_suffix(".tmp")
        with open(tmp_path, "wb") as f:
            tomli_w.dump({"vaults": vaults}, f)
        tmp_path.replace(_VAULTS_FILE)
    except Exception as e:
        logger.error(f"Failed to persist known vaults list: {e}")


def _remove_vault(vault_path: Path) -> None:
    """Remove a vault from the persistent list."""
    _VAULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    vaults = _load_known_vaults()
    vaults = [v for v in vaults if v.get("path") != str(vault_path)]
    try:
        import tomli_w

        # Atomic write
        tmp_path = _VAULTS_FILE.with_suffix(".tmp")
        with open(tmp_path, "wb") as f:
            tomli_w.dump({"vaults": vaults}, f)
        tmp_path.replace(_VAULTS_FILE)
    except Exception as e:
        logger.error(f"Failed to persist known vaults list: {e}")


class VaultPickerDialog(QDialog):
    """Display the dialog for selecting an existing vault or creating a new one.
    """

    def __init__(self, parent=None) -> None:
        """Initialize the vault picker dialog."""
        super().__init__(parent)
        self.setWindowTitle("Noteration — Select Vault")
        self.setFixedSize(480, 380)
        self._selected_vault: Path | None = None
        self._setup_ui()
        self._populate_vaults()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Set up the UI for the vault picker dialog."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        title = QLabel("Noteration")
        title.setFont(QFont("Georgia", 20, QFont.Weight.DemiBold))
        subtitle = QLabel("Select a research vault to open, or create a new vault.")
        subtitle.setStyleSheet("color: gray;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Vault list
        self._list = QListWidget()
        self._list.setIconSize(QSize(32, 32))
        self._list.setAlternatingRowColors(True)
        self._list.doubleClicked.connect(self._open_selected)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._list)

        # Action buttons
        btn_row = QHBoxLayout()

        self._btn_browse = QPushButton("Browse Vault…")
        self._btn_browse.clicked.connect(self._browse_vault)
        btn_row.addWidget(self._btn_browse)

        self._btn_new = QPushButton("Create New…")
        self._btn_new.clicked.connect(self._create_vault)
        btn_row.addWidget(self._btn_new)

        btn_row.addStretch()

        self._btn_open = QPushButton("Open")
        self._btn_open.setDefault(True)
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_selected)
        btn_row.addWidget(self._btn_open)

        layout.addLayout(btn_row)

        self._list.currentItemChanged.connect(
            lambda cur, _: self._btn_open.setEnabled(cur is not None)
        )

    # ------------------------------------------------------------------
    # Vault list management
    # ------------------------------------------------------------------

    def _populate_vaults(self) -> None:
        """Populate the vault list with known vaults."""
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
        """Display the context menu for the vault list."""
        item = self._list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        menu = QMenu(self)
        act_open = menu.addAction("Open Vault")
        menu.addSeparator()
        act_remove = menu.addAction("Remove from List")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen == act_remove:
            self._remove_vault_item(path)
        elif chosen == act_open:
            self._open_selected()

    def _remove_vault_item(self, path: str) -> None:
        """Handle removing a vault from the list."""
        reply = QMessageBox.question(
            self,
            "Remove Vault",
            f"Remove this vault from the list?\n\n{path}\n\n(The directory will not be deleted)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            _remove_vault(Path(path))
            self._populate_vaults()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_vault(self) -> None:
        """Open a directory browser to select a vault to browse."""
        path = QFileDialog.getExistingDirectory(self, "Select Vault Directory", str(Path.home()))
        if path:
            vault_path = Path(path)
            # Guess name from folder
            name = vault_path.name.replace("-", " ").replace("_", " ").title()
            _save_vault(vault_path, name)
            self._populate_vaults()

    def _create_vault(self) -> None:
        """Open the dialog to create a new vault."""
        from noteration.dialogs.new_vault import NewVaultDialog

        dlg = NewVaultDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vault_path, name = dlg.result_vault()
            self._init_vault(vault_path, name)
            _save_vault(vault_path, name)
            self._populate_vaults()

    def _init_vault(self, vault_path: Path, name: str) -> None:
        """Create the directory structure for a new vault."""
        for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
            (vault_path / sub).mkdir(parents=True, exist_ok=True)

    def _open_selected(self) -> None:
        """Open the currently selected vault."""
        item = self._list.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not Path(path).exists():
            QMessageBox.warning(self, "Not Found", f"Directory not found:\n{path}")
            return
        self._selected_vault = Path(path)
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_vault(self) -> Path:
        """Return the path to the selected vault."""
        if self._selected_vault is None:
            raise RuntimeError("Selected vault requested before dialog completion.")
        return self._selected_vault
