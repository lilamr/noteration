"""
Noteration application bootstrap.
"""

from __future__ import annotations

import os
import sys
import platform

if platform.system() == "Linux":
    os.environ.setdefault("LIBVA_DRIVER_NAME", "mesa")
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    # Disable portal to avoid registration errors and delays
    # This must be set before QApplication is created
    os.environ["QT_XDG_NO_PORTAL"] = "1"
    os.environ["QT_NO_XDG_DESKTOP_PORTAL"] = "1"
    # Silence the warning logging itself
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.services.warning=false"

from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from noteration.dialogs.vault_picker import VaultPickerDialog
from noteration.ui.main_window import MainWindow
from noteration.ui.theme import apply_theme, ThemeMode, SystemThemeWatcher
from noteration.config import NoterationConfig


def _global_config() -> NoterationConfig | None:
    """Coba baca config dari vault terakhir yang dikenal."""
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
    except Exception:
        pass
    return None


def main() -> int:
    # ── QApplication ──────────────────────────────────────────────────
    # Set metadata before creating the app instance
    QApplication.setApplicationName("Noteration")
    QApplication.setApplicationDisplayName("Noteration")
    QApplication.setApplicationVersion("1.0.0")
    QApplication.setOrganizationName("Noteration")
    QApplication.setOrganizationDomain("noteration.org")
    QApplication.setDesktopFileName("noteration")

    app = QApplication(sys.argv)

    # HiDPI
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    # ── Tema awal ─────────────────────────────────────────────────────
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

    # Wire tema dari Settings → app live
    def _on_theme_changed(theme_str: str) -> None:
        apply_theme(app, ThemeMode(theme_str))
        if theme_str == "system":
            watcher.start()
        else:
            watcher.stop()

    window.theme_change_requested.connect(_on_theme_changed)

    return app.exec()
