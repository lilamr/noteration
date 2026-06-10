"""Noteration application bootstrap.
"""

from __future__ import annotations

import sys
import os
import atexit
import signal
import shutil
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from noteration import __version__
from noteration.dialogs.vault_picker import VaultPickerDialog
from noteration.ui.main_window import MainWindow
from noteration.core.session import VaultSession
from noteration.ui.theme import apply_theme, ThemeMode, SystemThemeWatcher
from noteration.config import NoterationConfig
from noteration.logger import setup_logging, get_logger

logger = get_logger(__name__)

# Global tracker for cleanup
_TEMP_SESSION_DIR: Path | None = None


def _cleanup_temp_dir():
    """Final emergency cleanup of the temporary session directory."""
    global _TEMP_SESSION_DIR
    if _TEMP_SESSION_DIR and _TEMP_SESSION_DIR.exists():
        try:
            logger.info(f"Emergency cleanup of session: {_TEMP_SESSION_DIR}")
            shutil.rmtree(_TEMP_SESSION_DIR)
            _TEMP_SESSION_DIR = None
        except Exception as e:
            print(f"Failed to cleanup temp dir {_TEMP_SESSION_DIR}: {e}")


def _signal_handler(sig, frame):
    """Handle termination signals."""
    logger.info(f"Received signal {sig}, exiting...")
    _cleanup_temp_dir()
    sys.exit(0)


# Register cleanup
atexit.register(_cleanup_temp_dir)
if sys.platform != "win32":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)


def _global_config() -> NoterationConfig | None:
    """Attempt to read config from the last known vault."""
    vaults_file = Path.home() / ".noteration" / "vaults.toml"
    if not vaults_file.exists():
        return None
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
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
    # ── Security & Stability ──────────────────────────────────────────
    # Disable GPU acceleration if it's known to cause crashes (e.g. libva errors)
    # This is often needed for QtWebEngine on certain Linux drivers.
    os.environ["QTWEBENGINE_DISABLE_GPU"] = "1"

    # ── Logging ───────────────────────────────────────────────────────
    setup_logging()

    # ── QApplication ──────────────────────────────────────────────────
    # Force software rendering for maximum compatibility (prevents driver Segfaults)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL)

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
    watcher.theme_changed.connect(lambda mode: apply_theme(app, mode))
    if theme_mode == "system":
        watcher.start()

    # ── VaultPickerDialog ─────────────────────────────────────────────
    picker = VaultPickerDialog()
    if picker.exec() != VaultPickerDialog.DialogCode.Accepted:
        return 0

    vault_path = picker.selected_vault()

    # ── Vault Session Management ──────────────────────────────────────
    session = VaultSession(vault_path)

    if session.is_encrypted:
        logger.info(f"Vault {vault_path.name} detected as ENCRYPTED.")
        from noteration.dialogs.unlock_dialog import UnlockDialog
        from noteration.utils.encryption import is_age_available

        if not is_age_available():
            QMessageBox.critical(
                None,
                "Encryption Error",
                "This vault is encrypted but the 'age' tool was not found on your system.\n\n"
                "Please install 'age' (https://age-encryption.org) to access your data.",
            )
            return 0

        unlock = UnlockDialog(vault_path)
        if unlock.exec() != UnlockDialog.DialogCode.Accepted:
            logger.info("Vault unlock cancelled by user.")
            return 0

        try:
            if not session.unlock(unlock.get_key()):
                QMessageBox.warning(
                    None,
                    "Unlock Failed",
                    "Decryption produced no valid configuration. Please check if your private key is correct.",
                )
                return 0

            # Set global for emergency atexit cleanup
            global _TEMP_SESSION_DIR
            _TEMP_SESSION_DIR = session.temp_dir

        except Exception as e:
            logger.exception(f"Vault unlock failed: {e}")
            QMessageBox.critical(None, "Decryption Error", f"Failed to decrypt vault: {e}")
            return 1

    # ── MainWindow ────────────────────────────────────────────────────
    window = MainWindow(
        session.active_path,
        storage_path=vault_path,
        secret_key=session.secret_key,
        session_path=session.temp_dir,
    )
    if session.is_encrypted:
        window.vault.core.session_hashes = session.session_hashes
        window.setWindowTitle(f"{window.windowTitle()} [ENCRYPTED SESSION]")
    window.show()

    # Wire theme changes from Settings to the application instance
    def _on_theme_changed(theme_str: str) -> None:
        apply_theme(app, ThemeMode(theme_str))
        if theme_str == "system":
            watcher.start()
        else:
            watcher.stop()

    window.theme_change_requested.connect(_on_theme_changed)

    # Ensure graceful shutdown on app exit
    def shutdown():
        window.vault.shutdown()
        try:
            session.close()
        except Exception as e:
            QMessageBox.critical(None, "Save Error", f"Failed to re-encrypt changes: {e}")

    app.aboutToQuit.connect(shutdown)

    exit_code = app.exec()
    return exit_code
