"""
Noteration application bootstrap.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from noteration import __version__
from noteration.dialogs.vault_picker import VaultPickerDialog
from noteration.ui.main_window import MainWindow
from noteration.ui.theme import apply_theme, ThemeMode, SystemThemeWatcher
from noteration.config import NoterationConfig
from noteration.logger import setup_logging, get_logger

logger = get_logger(__name__)


def _global_config() -> NoterationConfig | None:
    """Attempt to read config from the last known vault."""
    vaults_file = Path.home() / ".noteration" / "vaults.toml"
    if not vaults_file.exists():
        return None
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib   # type: ignore
        except ImportError:
            return None
    try:
        with open(vaults_file, "rb") as f:
            data = tomllib.load(f)
        vaults = data.get("vaults", [])
        if vaults:
            path = Path(vaults[-1].get("path", ""))
            if path.exists():
                return NoterationConfig(path)
    except Exception as e:
        logger.debug(f"Failed to load global config: {e}")
    return None


def main() -> int:
    # ── Logging ───────────────────────────────────────────────────────
    setup_logging()
    
    # ── QApplication ──────────────────────────────────────────────────
    app = QApplication(sys.argv)

    # Set metadata after creating the app instance
    QApplication.setApplicationName("Noteration")
    QApplication.setApplicationDisplayName("Noteration")
    QApplication.setApplicationVersion(__version__)
    QApplication.setOrganizationName("Noteration")
    QApplication.setOrganizationDomain("noteration.org")
    QApplication.setDesktopFileName("noteration")

    # HiDPI support
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    # ── Initial theme ──────────────────────────────────────────────────
    cfg = _global_config()
    theme_mode = cfg.get("ui", "theme", "system") if cfg else "system"
    apply_theme(app, ThemeMode(theme_mode))

    # ── System theme watcher ──────────────────────────────────────────
    watcher = SystemThemeWatcher()
    watcher.theme_changed.connect(
        lambda mode: apply_theme(app, mode)
    )
    if theme_mode == "system":
        watcher.start()

    # ── VaultPickerDialog ─────────────────────────────────────────────
    picker = VaultPickerDialog()
    if picker.exec() != VaultPickerDialog.DialogCode.Accepted:
        return 0

    vault_path = picker.selected_vault()

    # ── MainWindow ────────────────────────────────────────────────────
    window = MainWindow(vault_path)
    window.show()

    # Wire theme changes from Settings to the application instance
    def _on_theme_changed(theme_str: str) -> None:
        apply_theme(app, ThemeMode(theme_str))
        if theme_str == "system":
            watcher.start()
        else:
            watcher.stop()

    window.theme_change_requested.connect(_on_theme_changed)

    return app.exec()
