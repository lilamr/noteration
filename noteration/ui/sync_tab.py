"""
Git synchronization tab with status, log, and commit history.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noteration.vault_manager import VaultManager

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QGroupBox, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit,
    QDialog, QDialogButtonBox, QFormLayout, QMessageBox,
    QGridLayout, QAbstractItemView,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QFont

from noteration.config import NoterationConfig
from noteration.sync.git_engine import (
    GitRepo, SyncResult, SyncStatus, SyncStrategy,
)


# ── Worker ────────────────────────────────────────────────────────────────

class SyncWorker(QObject):
    log_line = Signal(str, str)   # (text, level)
    finished = Signal(object)     # SyncResult

    def __init__(self, vault_path: Path, repo: GitRepo | None, config: NoterationConfig) -> None:
        super().__init__()
        self._vault_path = vault_path
        self._repo   = repo
        self._config = config
        self._op     = "sync"

    def set_operation(self, op: str) -> None:
        self._op = op

    def run(self) -> None:
        def log(msg: str) -> None:
            lvl = ("ok"    if msg.startswith("  ✓") or msg.startswith("✓") else
                   "error" if "✗" in msg or "ERROR" in msg else
                   "warn"  if "⚠" in msg else "info")
            self.log_line.emit(msg, lvl)

        if self._op == "init":
            try:
                GitRepo.init(self._vault_path)
                log("✓ Git repository initialized")
                self.finished.emit(SyncResult(
                    status=SyncStatus.SUCCESS, message="Init complete"))
            except Exception as e:
                log(f"✗ {e}")
                self.finished.emit(SyncResult(
                    status=SyncStatus.ERROR, message=str(e)))
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
        
        # We prefer the active branch for "Sync Now". 
        # If the config has a specific branch, we'll use it, 
        # but if empty (default), GitRepo will automatically use the active branch.
        branch = self._config.get("sync", "branch", "")

        strat_s  = self._config.get("sync", "strategy", "rebase")
        strategy = {"merge": SyncStrategy.MERGE,
                    "stash": SyncStrategy.STASH
                    }.get(strat_s, SyncStrategy.REBASE)

        if self._repo:
            result = self._repo.sync(
                remote=remote, branch=branch,
                strategy=strategy, log_callback=log,
            )
            self.finished.emit(result)


# ── Set-remote dialog ─────────────────────────────────────────────────────

class SetRemoteDialog(QDialog):
    def __init__(self, current: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Remote Repository")
        self.resize(440, 160)
        lay = QFormLayout(self)

        self.name_edit = QLineEdit("origin")
        self.url_edit  = QLineEdit()
        
        # If remotes exist, default to the first one
        if current:
            self.name_edit.setText(current[0][0])
            self.url_edit.setText(current[0][1])

        lay.addRow("Remote Name:", self.name_edit)
        lay.addRow("Repository URL:", self.url_edit)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def result_remote(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.url_edit.text().strip()


# ── Main Tab ──────────────────────────────────────────────────────────────

class SyncTab(QWidget):
    _lbl_branch: QLabel
    _lbl_remote: QLabel
    _lbl_status: QLabel
    _lbl_last: QLabel

    def __init__(self, vault: "VaultManager",
                 parent=None) -> None:
        super().__init__(parent)
        self.vault      = vault
        self.vault_path = vault.vault_path
        self.config     = vault.config
        self._repo      = vault.git_repo
        self._thread: QThread | None     = None
        self._worker: SyncWorker | None  = None
        self._pending: SyncResult | None = None

        self._setup_ui()
        self._refresh_status()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 1. Top: Status & Controls
        status_group = QGroupBox("Repository Status")
        status_layout = QVBoxLayout(status_group)
        
        grid = QGridLayout()
        grid.addWidget(QLabel("Active Branch:"), 0, 0)
        self._lbl_branch = QLabel("—")
        grid.addWidget(self._lbl_branch, 0, 1)
        
        grid.addWidget(QLabel("Remote:"), 1, 0)
        self._lbl_remote = QLabel("—")
        grid.addWidget(self._lbl_remote, 1, 1)
        
        grid.addWidget(QLabel("Sync Status:"), 2, 0)
        self._lbl_status = QLabel("—")
        grid.addWidget(self._lbl_status, 2, 1)
        
        status_layout.addLayout(grid)
        
        btn_layout = QHBoxLayout()
        self._btn_sync = QPushButton("Sync Now")
        self._btn_sync.clicked.connect(self.start_sync)
        self._btn_sync.setStyleSheet("font-weight: bold; padding: 6px;")
        
        self._btn_abort = QPushButton("Abort Sync")
        self._btn_abort.clicked.connect(self._abort_sync)
        self._btn_abort.setVisible(False)
        
        self._btn_resolve = QPushButton("Resolve Conflicts")
        self._btn_resolve.clicked.connect(self._open_conflict_dialog)
        self._btn_resolve.setVisible(False)
        self._btn_resolve.setStyleSheet("background-color: #FFF3E0; color: #E65100; font-weight:bold;")

        self._btn_remote = QPushButton("Set Remote")
        self._btn_remote.clicked.connect(self._set_remote)

        self._btn_init = QPushButton("Initialize Git")
        self._btn_init.clicked.connect(self._init_git)
        self._btn_init.setVisible(False)

        btn_layout.addWidget(self._btn_sync)
        btn_layout.addWidget(self._btn_resolve)
        btn_layout.addWidget(self._btn_abort)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_remote)
        btn_layout.addWidget(self._btn_init)
        status_layout.addLayout(btn_layout)
        
        splitter.addWidget(status_group)
        
        # 2. Middle: Log
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_group)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Monospace", 9))
        self._log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        log_layout.addWidget(self._log)
        splitter.addWidget(log_group)
        
        # 3. Bottom: History
        hist_group = QGroupBox("Recent Commit History")
        hist_layout = QVBoxLayout(hist_group)
        self._hist = QTableWidget(0, 4)
        self._hist.setHorizontalHeaderLabels(["SHA", "Message", "Author", "Time"])
        self._hist.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._hist.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._hist.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hist_layout.addWidget(self._hist)
        splitter.addWidget(hist_group)
        
        layout.addWidget(splitter)

    def _append_log(self, text: str, level: str = "info") -> None:
        color = {
            "ok":    "#4CAF50",
            "error": "#F44336",
            "warn":  "#FF9800",
            "info":  "#D4D4D4"
        }.get(level, "#D4D4D4")
        
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        
        cursor.insertText(text + "\n")
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    # ── Status ────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        self._repo = self.vault.git_repo
        if self._repo is None:
            self._lbl_branch.setText("—")
            self._lbl_remote.setText("Offline")
            self._lbl_status.setText("✗ Not a Git repo")
            self._lbl_status.setStyleSheet("color:#C62828;font-weight:bold;")
            self._btn_abort.setVisible(False)
            self._btn_sync.setEnabled(False)
            self._btn_remote.setEnabled(False)
            self._btn_init.setVisible(True)
            return

        self._btn_init.setVisible(False)
        st = self._repo.status()

        self._lbl_branch.setText(st.branch or "—")
        self._lbl_remote.setText(", ".join(st.remotes) or "None")

        # Detect stuck state
        is_stuck = self._repo.is_rebase_in_progress() or self._repo.is_merge_in_progress()
        self._btn_abort.setVisible(is_stuck)

        if not st.is_repo:
            self._lbl_status.setText("✗ Not a Git repo")
            self._lbl_status.setStyleSheet(
                "color:#C62828;font-weight:bold;border:none;background:transparent;")
        elif is_stuck:
            self._lbl_status.setText("⚠ Rebase/Merge Conflict")
            self._lbl_status.setStyleSheet(
                "color:#C62828;font-weight:bold;border:none;background:transparent;")
            # Show resolve button if unmerged conflicts exist
            conflicts = self._repo._detect_conflicts()
            if conflicts:
                self._btn_resolve.setVisible(True)
                self._pending = SyncResult(status=SyncStatus.CONFLICT, conflicts=conflicts)
        elif st.is_dirty:
            n = len(st.modified) + len(st.untracked)
            self._lbl_status.setText(f"● {n} local changes")
            self._lbl_status.setStyleSheet(
                "color:#E65100;font-weight:bold;border:none;background:transparent;")
        elif st.ahead > 0:
            self._lbl_status.setText(f"● {st.ahead} commits ahead (not pushed)")
            self._lbl_status.setStyleSheet(
                "color:#1565C0;font-weight:bold;border:none;background:transparent;")
        elif st.behind > 0:
            self._lbl_status.setText(f"● {st.behind} commits behind (not pulled)")
            self._lbl_status.setStyleSheet(
                "color:#6A1B9A;font-weight:bold;border:none;background:transparent;")
        else:
            self._lbl_status.setText("✓ Synced")
            self._lbl_status.setStyleSheet(
                "color:#2E7D32;font-weight:bold;border:none;background:transparent;")

        self._btn_sync.setEnabled(True)
        self._btn_remote.setEnabled(True)
        self._refresh_history()

    # ── History ──────────────────────────────────────────────────────

    def _refresh_history(self) -> None:
        if self._repo is None:
            self._hist.setRowCount(0)
            return

        commits = self._repo.recent_commits(25)
        self._hist.setRowCount(len(commits))
        mono = QFont("Consolas", 10)
        for row, c in enumerate(commits):
            for col, val in enumerate(
                [c["sha"], c["message"], c["author"], c["time"]]
            ):
                item = QTableWidgetItem(str(val))
                if col == 0:
                    item.setFont(mono)
                self._hist.setItem(row, col, item)
        
        self._hist.resizeColumnToContents(0)
        self._hist.resizeColumnToContents(2)
        self._hist.resizeColumnToContents(3)

    # ── Workers ───────────────────────────────────────────────────────

    def start_sync(self) -> None:
        if self._repo is None:
            QMessageBox.information(self, "Git Inactive", "This vault is not a Git repository.")
            return

        if self._thread and self._thread.isRunning():
            return

        # If rebase is in progress, continue
        if self._repo.is_rebase_in_progress():
            self._run_worker("continue")
        else:
            self._run_worker("sync")

    def _abort_sync(self) -> None:
        if QMessageBox.warning(self, "Abort Synchronization", 
                             "This will abort the ongoing rebase/merge operation. "
                             "Uncommitted changes might be lost. Continue?",
                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._run_worker("abort")

    def _init_git(self) -> None:
        if QMessageBox.question(self, "Initialize Git",
                              "Do you want to create a new Git repository in this vault?") == QMessageBox.StandardButton.Yes:
            self._run_worker("init")

    def _run_worker(self, op: str) -> None:
        self._log.clear()
        self._append_log(f"--- Operation: {op.upper()} ---", "info")
        
        self._btn_sync.setEnabled(False)
        self._btn_init.setEnabled(False)
        self._btn_abort.setEnabled(False)
        self._btn_resolve.setVisible(False)

        self._thread = QThread()
        self._worker = SyncWorker(self.vault_path, self._repo, self.config)
        self._worker.set_operation(op)
        self._worker.moveToThread(self._thread)
        self._worker.log_line.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_finished(self, result: SyncResult) -> None:
        self._btn_sync.setEnabled(True)
        self._btn_init.setEnabled(True)
        self._btn_abort.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        
        self.vault.refresh_git_repo()
        self._refresh_status()
        self.vault.request_git_status()

        if result.status == SyncStatus.CONFLICT:
            self._pending = result
            self._btn_resolve.setVisible(True)
            self._append_log(
                f"\n⚠  {len(result.conflicts)} conflicting files — "
                "click 'Resolve Conflicts' to resolve", "warn")
        elif result.ok:
            self._append_log(f"\n✓  {result.message}", "ok")
        else:
            self._append_log(f"\n✗  {result.message}", "error")

    # ── Conflict ──────────────────────────────────────────────────────

    def _open_conflict_dialog(self) -> None:
        if not self._pending:
            return
        
        self._resolve_conflicts()

    def _resolve_conflicts(self) -> None:
        if self._pending is None or self._repo is None:
            return

        from noteration.dialogs.conflict_dialog import ConflictResolutionDialog
        dlg = ConflictResolutionDialog(self._pending.conflicts, self)
        if dlg.exec():
            res = dlg.get_resolutions()
            for path, content in res.items():
                self._repo.resolve_conflict(path, content)
            
            self._append_log(
                f"✓ {len(res)} files resolved — continuing rebase…", "ok")
            self._btn_resolve.setVisible(False)
            self._pending = None
            # Automatically trigger continue rebase
            QTimer.singleShot(600, self.start_sync)

    # ── Remote ────────────────────────────────────────────────────────

    def _set_remote(self) -> None:
        if self._repo is None:
            return
        current = self._repo.list_remotes()
        dlg = SetRemoteDialog(current, self)
        if dlg.exec():
            name, url = dlg.result_remote()
            if url:
                self._repo.add_remote(name, url)
                self.config.set("sync", "remote", name)
                self.config.save()
                self._refresh_status()
                self._append_log(f"✓ Remote '{name}' → {url}", "ok")
