"""noteration/ui/sync_tab.py
Git synchronization tab with status, log, and commit history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from noteration.vault_manager import VaultManager

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from noteration.logger import get_logger
from noteration.sync.git_engine import (
    GitRepo,
    SyncResult,
    SyncStatus,
    SyncStrategy,
)
from noteration.utils.qt_helpers import BaseWorker

logger = get_logger(__name__)


# ── Worker ────────────────────────────────────────────────────────────────


class SyncWorker(BaseWorker):
    log_line = Signal(str, str)  # (text, level)
    finished = Signal(object)  # SyncResult

    def __init__(self, vault: "VaultManager") -> None:
        super().__init__()
        self._vault = vault
        self._vault_path = vault.vault_path
        self._storage_path = vault.storage_path
        self._repo = vault.core.git_repo
        self._config = vault.config
        self._op = "sync"

    def set_operation(self, op: str) -> None:
        """Set the current git operation."""
        self._op = op

    def run(self) -> None:
        """Execute the git synchronization operation."""
        def log(msg: str) -> None:
            lvl = (
                "ok"
                if msg.startswith("  ✓") or msg.startswith("✓")
                else "error"
                if "✗" in msg or "ERROR" in msg
                else "warn"
                if "⚠" in msg
                else "info"
            )
            self.log_line.emit(msg, lvl)

        # Handle Encrypted Vault Sync Lifecycle
        is_encrypted = self._config.get("security", "encryption_enabled", False)
        if is_encrypted and self._op == "sync":
            log("🛡️ Encrypted vault detected. Preparing for sync...")
            if not self._vault.secret_key:
                log(
                    "✗ Error: No private key available in this session. Cannot decrypt incoming changes."
                )
                self.finished.emit(
                    SyncResult(status=SyncStatus.ERROR, message="Missing private key")
                )
                return

            # 1. PRE-SYNC ENCRYPTION
            try:
                log("  → Encrypting all vault contents...")
                self._vault.core.encrypt_vault(log_callback=log)
                log("  ✓ All changes encrypted (Staging)")
            except Exception as e:
                log(f"✗ Pre-sync encryption failed: {e}")
                self.finished.emit(SyncResult(status=SyncStatus.ERROR, message=str(e)))
                return

        if self._op == "init":
            try:
                GitRepo.init(self._storage_path)
                log("✓ Git repository initialized")
                self.finished.emit(SyncResult(status=SyncStatus.SUCCESS, message="Init complete"))
            except Exception as e:
                log(f"✗ {e}")
                self.finished.emit(SyncResult(status=SyncStatus.ERROR, message=str(e)))
            return

        if self._op == "abort":
            if self._repo and self._repo.abort_sync():
                log("✓ Synchronization aborted")
                self.finished.emit(SyncResult(status=SyncStatus.SUCCESS, message="Aborted"))
            else:
                log("✗ Failed to abort synchronization")
                self.finished.emit(SyncResult(status=SyncStatus.ERROR, message="Abort failed"))
            return

        if self._op == "continue":
            if self._repo:
                result = self._repo.continue_sync(log_callback=log)
                self.finished.emit(result)
            return

        # Normal sync
        remote = self._config.get("sync", "remote", "origin")
        branch = self._config.get("sync", "branch", "")

        strat_s = self._config.get("sync", "strategy", "rebase")
        strategy = {"merge": SyncStrategy.MERGE, "stash": SyncStrategy.STASH}.get(
            strat_s, SyncStrategy.REBASE
        )

        if self._repo:
            try:
                # Ensure .gitignore is up to date and metadata is untracked before sync
                self._repo.ensure_ignored()

                result = self._repo.sync(
                    remote=remote,
                    branch=branch,
                    strategy=strategy,
                    log_callback=log,
                )

                # 2. POST-SYNC DECRYPTION (if sync was successful)
                if is_encrypted and result.status == SyncStatus.SUCCESS:
                    try:
                        log("🛡️ Sync complete. Decrypting new incoming changes...")
                        self._vault.core.decrypt_vault(log_callback=log)
                        log("  ✓ Incoming changes decrypted and available")
                    except Exception as e:
                        log(f"⚠ Warning: Post-sync decryption failed: {e}")

                self.finished.emit(result)
            except Exception as e:
                log(f"✗ Unexpected error: {e}")
                self.finished.emit(SyncResult(status=SyncStatus.ERROR, message=str(e)))


# ── Set-remote dialog ─────────────────────────────────────────────────────


class SetRemoteDialog(QDialog):
    def __init__(self, current: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Remote Repository")
        self.resize(440, 160)
        lay = QFormLayout(self)

        self.name_edit = QLineEdit("origin")
        self.url_edit = QLineEdit()

        if current:
            self.name_edit.setText(current[0][0])
            self.url_edit.setText(current[0][1])

        lay.addRow("Remote Name:", self.name_edit)
        lay.addRow("Repository URL:", self.url_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def result_remote(self) -> tuple[str, str]:
        """Return the configured remote name and URL."""
        return self.name_edit.text().strip(), self.url_edit.text().strip()


# ── UI Components ────────────────────────────────────────────────────────


class LogEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("DM Mono", 9))
        self.setStyleSheet("background: #1a1a1d; color: #e8e4da; border: 1px solid #2a2a2e;")

    def append_log(self, text: str, level: str = "info"):
        """Append a formatted log message to the log display."""
        fmt = QTextCharFormat()
        if level == "error":
            fmt.setForeground(QColor("#ff5f57"))
        elif level == "ok":
            fmt.setForeground(QColor("#28c840"))
        elif level == "warn":
            fmt.setForeground(QColor("#febc2e"))
        else:
            fmt.setForeground(QColor("#a0a0a8"))

        self.setCurrentCharFormat(fmt)
        self.appendPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.End)


# ── Main Tab ──────────────────────────────────────────────────────────────


class SyncTab(QWidget):
    def __init__(self, vault: "VaultManager", parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self._thread: Optional[QThread] = None
        self._worker: Optional[SyncWorker] = None

        self._setup_ui()
        self._refresh_status()

    def _setup_ui(self):
        """Initialize the synchronization tab UI components."""
        layout = QVBoxLayout(self)

        # 1. Status Group
        status_grp = QGroupBox("Git Status")
        status_lay = QGridLayout(status_grp)

        self._lbl_branch = QLabel("Checking...")
        self._lbl_remote = QLabel("Checking...")
        self._lbl_status = QLabel("Checking...")
        self._lbl_ahead = QLabel("0")
        self._lbl_behind = QLabel("0")
        self._lbl_last = QLabel("Checking...")

        status_lay.addWidget(QLabel("Branch:"), 0, 0)
        status_lay.addWidget(self._lbl_branch, 0, 1)
        status_lay.addWidget(QLabel("Remote:"), 1, 0)
        status_lay.addWidget(self._lbl_remote, 1, 1)
        status_lay.addWidget(QLabel("State:"), 0, 2)
        status_lay.addWidget(self._lbl_status, 0, 3)
        status_lay.addWidget(QLabel("Ahead:"), 1, 2)
        status_lay.addWidget(self._lbl_ahead, 1, 3)
        status_lay.addWidget(QLabel("Behind:"), 2, 0)
        status_lay.addWidget(self._lbl_behind, 2, 1)
        status_lay.addWidget(QLabel("Last Sync:"), 2, 2)
        status_lay.addWidget(self._lbl_last, 2, 3)

        layout.addWidget(status_grp)

        # 2. Controls
        ctrl_lay = QHBoxLayout()
        self._btn_sync = QPushButton("Sync Now")
        self._btn_sync.clicked.connect(self._on_sync)
        self._btn_sync.setStyleSheet("font-weight: bold; background: #2d6a4f; color: white;")

        self._btn_remote = QPushButton("Configure Remote")
        self._btn_remote.clicked.connect(self._on_set_remote)

        ctrl_lay.addWidget(self._btn_sync)
        ctrl_lay.addWidget(self._btn_remote)
        ctrl_lay.addStretch()

        layout.addLayout(ctrl_lay)

        # 3. Log
        layout.addWidget(QLabel("Operation Log:"))
        self._log_edit = LogEdit()
        layout.addWidget(self._log_edit)

    def _refresh_status(self):
        """Refresh the displayed Git status."""
        repo = self.vault.core.git_repo
        if not repo:
            self._lbl_branch.setText("Not a Git repository")
            self._btn_sync.setText("Initialize Git")
            return

        status = repo.status(session_hashes=self.vault.core.session_hashes)
        self._lbl_branch.setText(status.branch)
        self._lbl_remote.setText(", ".join(status.remotes) if status.remotes else "None")
        self._lbl_status.setText("Dirty (Uncommitted)" if status.is_dirty else "Clean")
        self._lbl_ahead.setText(str(status.ahead))
        self._lbl_behind.setText(str(status.behind))
        self._lbl_last.setText(status.last_commit_time or "Never")
        self._btn_sync.setText("Sync Now")

    def start_sync(self):
        """Initiate the synchronization process."""
        if not self.vault.core.git_repo:
            self._start_op("init", "Initializing...")
            return
        self._start_op("sync", "Synchronizing...")

    def _on_sync(self):
        """Handle sync button click."""
        self.start_sync()

    def _start_op(self, op: str, status_text: str):
        """Start a background synchronization operation."""
        if self._thread and self._thread.isRunning():
            return

        self._log_edit.append_log(f">>> Starting {op.upper()}...")
        self._btn_sync.setEnabled(False)
        self._btn_sync.setText(f"{status_text}...")
        self._btn_sync.setStyleSheet("font-weight: bold; background: #6c757d; color: white;")

        self._thread = QThread(self)
        self._worker = SyncWorker(self.vault)
        self._worker.set_operation(op)
        self._worker.moveToThread(self._thread)

        self._worker.log_line.connect(self._log_edit.append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.started.connect(self._worker.run)

        self._thread.start()

    def _on_finished(self, result: SyncResult):
        """Handle synchronization operation completion."""
        if self._thread:
            self._thread.finished.connect(self._thread.deleteLater)
            if hasattr(self, "_worker") and self._worker:
                self._worker.deleteLater()
            self._thread.quit()
            self._thread = None
            self._worker = None

        # 1. Handle Conflicts
        if result.status == SyncStatus.CONFLICT and result.conflicts:
            from noteration.dialogs.conflict_dialog import ConflictResolutionDialog

            dlg = ConflictResolutionDialog(result.conflicts, self)
            if dlg.exec():
                resolutions = dlg.get_resolutions()
                repo = self.vault.core.git_repo
                if repo:
                    self._log_edit.append_log("Applying resolutions...", "info")
                    public_key = self.vault.config.get("security", "public_key", "")
                    for path, content in resolutions.items():
                        repo.resolve_conflict(path, content, public_key=public_key)

                    # Continue the sync process (commit/push)
                    self._start_op("continue", "Completing sync")
                    return
            else:
                self._log_edit.append_log("⚠ Sync aborted. Conflicts remain unresolved.", "warn")

        # 2. Post-op cleanup and status update
        if result.ok:
            self.vault.core.refresh_git_repo()

        self._btn_sync.setEnabled(True)
        self._btn_sync.setText("Sync Now")
        self._btn_sync.setStyleSheet("font-weight: bold; background: #2d6a4f; color: white;")
        self._refresh_status()
        self._log_edit.append_log(f"--- {result.message} ---", "ok" if result.ok else "error")

        # Trigger global status update so MainWindow badge updates
        self.vault.request_git_status()

    def shutdown(self) -> None:
        """Safely stop any background sync threads."""
        if self._thread and self._thread.isRunning():
            logger.info("SyncTab: Stopping background sync thread...")
            self._thread.requestInterruption()
            self._thread.quit()
            if self._thread.wait(5000):
                self._thread = None
                self._worker = None
            else:
                logger.error("SyncTab: Sync thread failed to stop. Holding reference to prevent crash.")
        else:
            self._thread = None
            self._worker = None

    def _on_set_remote(self):
        """Handle set remote button click."""
        repo = self.vault.core.git_repo

        # If no repo exists, current remotes is empty
        current_remotes = repo.list_remotes() if repo else []

        dlg = SetRemoteDialog(current_remotes, self)
        if dlg.exec():
            name, url = dlg.result_remote()

            if not name or not url:
                self._log_edit.append_log("✗ Error: Remote name and URL cannot be empty.", "error")
                return

            if repo:
                try:
                    repo.add_remote(name, url)
                    self._log_edit.append_log(f"✓ Remote '{name}' set to: {url}", "ok")
                    self._refresh_status()
                except Exception as e:
                    self._log_edit.append_log(f"✗ Failed to set remote: {e}", "error")
            else:
                # If no repo exists, initialize it now with this remote
                try:
                    from noteration.sync.git_engine import GitRepo

                    GitRepo.init(self.vault.storage_path, remote_url=url)
                    self.vault.core.refresh_git_repo()
                    self._log_edit.append_log(
                        f"✓ Git repository initialized with remote: {url}", "ok"
                    )
                    self._refresh_status()
                except Exception as e:
                    self._log_edit.append_log(f"✗ Failed to initialize Git: {e}", "error")
