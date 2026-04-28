"""
Git synchronization tab with status, log, and commit history.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QGroupBox, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QLineEdit,
    QDialog, QDialogButtonBox, QFormLayout, QMessageBox,
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

    def __init__(self, repo: GitRepo, config: NoterationConfig) -> None:
        super().__init__()
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
                GitRepo.init(self._repo.vault_path)
                log("✓ Repositori Git diinisialisasi")
                self.finished.emit(SyncResult(
                    status=SyncStatus.SUCCESS, message="Init selesai"))
            except Exception as e:
                log(f"✗ {e}")
                self.finished.emit(SyncResult(
                    status=SyncStatus.ERROR, message=str(e)))
            return
        
        if self._op == "abort":
            if self._repo.abort_sync():
                log("✓ Sinkronisasi dibatalkan")
                self.finished.emit(SyncResult(status=SyncStatus.SUCCESS, message="Aborted"))
            else:
                log("✗ Gagal membatalkan sinkronisasi")
                self.finished.emit(SyncResult(status=SyncStatus.ERROR, message="Abort failed"))
            return

        if self._op == "continue":
            result = self._repo.continue_sync(log_callback=log)
            self.finished.emit(result)
            return

        # Normal sync
        remote   = self._config.get("sync", "remote",   "origin")
        branch   = self._config.get("sync", "branch",   "main")
        strat_s  = self._config.get("sync", "strategy", "rebase")
        strategy = {"merge": SyncStrategy.MERGE,
                    "stash": SyncStrategy.STASH
                    }.get(strat_s, SyncStrategy.REBASE)

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

        self._name = QLineEdit("origin")
        self._url  = QLineEdit()
        self._url.setPlaceholderText(
            "https://github.com/username/vault-name.git")

        if current:
            self._name.setText(current[0][0])
            self._url.setText(current[0][1])

        lay.addRow("Nama remote:", self._name)
        lay.addRow("URL:", self._url)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def result_remote(self) -> tuple[str, str]:
        return self._name.text().strip(), self._url.text().strip()


# ── SyncTab ───────────────────────────────────────────────────────────────

class SyncTab(QWidget):

    _lbl_branch: QLabel
    _lbl_remote: QLabel
    _lbl_status: QLabel
    _lbl_ahead: QLabel
    _lbl_last: QLabel

    def __init__(self, vault_path: Path, config: NoterationConfig,
                 parent=None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        self.config     = config
        self._repo      = GitRepo(vault_path)
        self._thread: QThread | None     = None
        self._worker: SyncWorker | None  = None
        self._pending: SyncResult | None = None

        self._setup_ui()
        self._refresh_status()

        self._timer = QTimer(self)
        self._timer.setInterval(10_000)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_action_row())

        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.addWidget(self._build_status_cards())
        vsplit.addWidget(self._build_bottom())
        vsplit.setSizes([80, 200])
        root.addWidget(vsplit)

    def _build_status_cards(self) -> QGroupBox:
        grp = QGroupBox("Status Repositori")
        grp.setStyleSheet("QGroupBox{font-weight:bold;}")
        row = QHBoxLayout(grp)
        row.setSpacing(6)

        def card(title: str, attr: str) -> QFrame:
            f = QFrame()
            f.setStyleSheet(
                "QFrame{border:0.5px solid palette(mid);"
                "border-radius:4px;background:palette(base);}")
            vl = QVBoxLayout(f)
            vl.setContentsMargins(8, 4, 8, 4)
            vl.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet(
                "font-size:10px;color:gray;font-weight:600;"
                "border:none;background:transparent;")
            vl.addWidget(t)
            v = QLabel("—")
            v.setWordWrap(True)
            v.setStyleSheet("font-size:12px;border:none;background:transparent;")
            vl.addWidget(v)
            setattr(self, attr, v)
            return f

        row.addWidget(card("Branch",         "_lbl_branch"))
        row.addWidget(card("Remote",         "_lbl_remote"))
        row.addWidget(card("Status",         "_lbl_status"))
        row.addWidget(card("Ahead / Behind", "_lbl_ahead"))
        row.addWidget(card("Commit Terakhir","_lbl_last"))
        return grp

    def _build_action_row(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet("background:palette(window); border-bottom:1px solid palette(mid);")
        f.setFixedHeight(32)
        row = QHBoxLayout(f)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(4)

        self._btn_sync = QPushButton("↑↓  Sync Sekarang")
        self._btn_sync.setStyleSheet(
            "QPushButton{background:#1565C0;color:white;"
            "padding:4px 12px;border-radius:4px;font-weight:bold;}"
            "QPushButton:hover{background:#1976D2;}"
            "QPushButton:disabled{background:#90A4AE;}")
        self._btn_sync.setFixedHeight(26)
        self._btn_sync.clicked.connect(self.start_sync)
        row.addWidget(self._btn_sync)

        self._btn_abort = QPushButton("✕ Abort")
        self._btn_abort.setVisible(False)
        self._btn_abort.setStyleSheet(
            "QPushButton{background:#B71C1C;color:white;"
            "padding:4px 12px;border-radius:4px;font-weight:bold;}"
            "QPushButton:hover{background:#D32F2F;}")
        self._btn_abort.setFixedHeight(26)
        self._btn_abort.clicked.connect(self._abort_sync)
        row.addWidget(self._btn_abort)

        self._btn_init = QPushButton("Init Repo")
        self._btn_init.clicked.connect(self._init_repo)
        row.addWidget(self._btn_init)

        self._btn_remote = QPushButton("Set Remote…")
        self._btn_remote.clicked.connect(self._set_remote)
        row.addWidget(self._btn_remote)

        self._btn_resolve = QPushButton("🔀 Resolusi Konflik…")
        self._btn_resolve.setVisible(False)
        self._btn_resolve.setStyleSheet(
            "background:#B71C1C;color:white;"
            "padding:6px 12px;border-radius:6px;")
        self._btn_resolve.clicked.connect(self._open_conflict_dialog)
        row.addWidget(self._btn_resolve)

        row.addStretch()

        btn_refresh = QPushButton("↻")
        btn_refresh.setFixedWidth(32)
        btn_refresh.setToolTip("Refresh status")
        btn_refresh.clicked.connect(self._refresh_status)
        row.addWidget(btn_refresh)

        return f

    def _build_bottom(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 0, 12, 12)

        hsplit = QSplitter(Qt.Orientation.Horizontal)

        # Log
        log_grp = QGroupBox("Log Operasi")
        log_lay = QVBoxLayout(log_grp)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        f = QFont("Consolas", 10)
        f.setFixedPitch(True)
        self._log.setFont(f)
        log_lay.addWidget(self._log)
        btn_clr = QPushButton("Bersihkan Log")
        btn_clr.setFixedHeight(22)
        btn_clr.clicked.connect(self._log.clear)
        log_lay.addWidget(btn_clr)
        hsplit.addWidget(log_grp)

        # History table
        hist_grp = QGroupBox("Riwayat Commit")
        hist_lay = QVBoxLayout(hist_grp)
        self._hist = QTableWidget(0, 4)
        self._hist.setHorizontalHeaderLabels(["SHA","Pesan","Author","Waktu"])
        self._hist.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._hist.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._hist.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._hist.setAlternatingRowColors(True)
        self._hist.setStyleSheet("font-size:11px;")
        hist_lay.addWidget(self._hist)
        hsplit.addWidget(hist_grp)

        hsplit.setSizes([520, 320])
        lay.addWidget(hsplit)
        return w

    # ── Status ────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        st = self._repo.status()

        self._lbl_branch.setText(st.branch or "—")
        self._lbl_remote.setText(", ".join(st.remotes) or "Tidak ada")

        # Detect stuck state
        is_stuck = self._repo.is_rebase_in_progress() or self._repo.is_merge_in_progress()
        self._btn_abort.setVisible(is_stuck)

        if not st.is_repo:
            self._lbl_status.setText("✗ Bukan repo Git")
            self._lbl_status.setStyleSheet(
                "color:#C62828;font-weight:bold;border:none;background:transparent;")
        elif is_stuck:
            self._lbl_status.setText("⚠ Konflik Rebase/Merge")
            self._lbl_status.setStyleSheet(
                "color:#C62828;font-weight:bold;border:none;background:transparent;")
            # Tampilkan tombol resolve jika ada konflik unmerged
            conflicts = self._repo._detect_conflicts()
            if conflicts:
                self._btn_resolve.setVisible(True)
                self._pending = SyncResult(status=SyncStatus.CONFLICT, conflicts=conflicts)
        elif st.is_dirty:
            n = len(st.modified) + len(st.untracked)
            self._lbl_status.setText(f"● {n} perubahan")
            self._lbl_status.setStyleSheet(
                "color:#E65100;border:none;background:transparent;")
        elif not st.remotes:
            self._lbl_status.setText("○ Lokal (tidak ada remote)")
            self._lbl_status.setStyleSheet(
                "color:#616161;font-weight:bold;border:none;background:transparent;")
        elif st.ahead > 0 or st.behind > 0:
            self._lbl_status.setText("● Perlu sinkronisasi")
            self._lbl_status.setStyleSheet(
                "color:#1565C0;font-weight:bold;border:none;background:transparent;")
        else:
            self._lbl_status.setText("✓ Synced")
            self._lbl_status.setStyleSheet(
                "color:#2E7D32;font-weight:bold;border:none;background:transparent;")

        self._lbl_ahead.setText(f"↑{st.ahead}  ↓{st.behind}")

        if st.last_commit_sha:
            self._lbl_last.setText(
                f"{st.last_commit_sha} · {st.last_commit_time}\n"
                f"{st.last_commit_msg[:38]}")
        else:
            self._lbl_last.setText("—")

        self._refresh_history()

    # ── History ──────────────────────────────────────────────────────

    def _refresh_history(self) -> None:
        commits = self._repo.recent_commits(25)
        self._hist.setRowCount(len(commits))
        mono = QFont("Consolas", 10)
        for row, c in enumerate(commits):
            for col, val in enumerate(
                [c["sha"], c["message"], c["author"], c["time"]]
            ):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setFont(mono)
                    item.setForeground(QColor("#185FA5"))
                self._hist.setItem(row, col, item)
        self._hist.resizeColumnToContents(0)
        self._hist.resizeColumnToContents(2)
        self._hist.resizeColumnToContents(3)

    # ── Workers ───────────────────────────────────────────────────────

    def start_sync(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        
        # Jika sedang rebase, continue
        if self._repo.is_rebase_in_progress():
            self._run_worker("continue")
        else:
            self._run_worker("sync")

    def _abort_sync(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        if QMessageBox.question(
            self, "Abort Sync",
            "Batalkan sinkronisasi yang sedang berjalan?\n"
            "Ini akan mengembalikan repositori ke keadaan sebelum pull.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self._run_worker("abort")

    def _init_repo(self) -> None:
        self._run_worker("init")

    def _run_worker(self, op: str) -> None:
        self._log.clear()
        self._btn_sync.setEnabled(False)
        self._btn_init.setEnabled(False)
        self._btn_resolve.setVisible(False)
        self._btn_abort.setEnabled(False)
        self._pending = None

        self._thread = QThread()
        self._worker = SyncWorker(self._repo, self.config)
        self._worker.set_operation(op)
        self._worker.moveToThread(self._thread)
        self._worker.log_line.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _append_log(self, text: str, level: str = "info") -> None:
        colors = {
            "ok":    "#2E7D32",
            "error": "#C62828",
            "warn":  "#E65100",
            "info":  "#424242",
        }
        cur = self._log.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors.get(level, "#424242")))
        cur.insertText(text + "\n", fmt)
        self._log.setTextCursor(cur)
        self._log.ensureCursorVisible()

    def _on_finished(self, result: SyncResult) -> None:
        self._btn_sync.setEnabled(True)
        self._btn_init.setEnabled(True)
        self._btn_abort.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._refresh_status()

        if result.status == SyncStatus.CONFLICT:
            self._pending = result
            self._btn_resolve.setVisible(True)
            self._append_log(
                f"\n⚠  {len(result.conflicts)} file konflik — "
                "klik 'Resolusi Konflik' untuk menyelesaikan", "warn")
        elif result.ok:
            self._append_log(f"\n✓  {result.message}", "ok")
        else:
            self._append_log(f"\n✗  {result.message}", "error")

    # ── Conflict ──────────────────────────────────────────────────────

    def _open_conflict_dialog(self) -> None:
        if not self._pending:
            return
        from noteration.dialogs.conflict_dialog import ConflictResolutionDialog
        dlg = ConflictResolutionDialog(self._pending.conflicts, self)
        if dlg.exec():
            res = dlg.get_resolutions()
            for path, content in res.items():
                self._repo.resolve_conflict(path, content)
            self._append_log(
                f"✓ {len(res)} file resolved — melanjutkan rebase…", "ok")
            self._btn_resolve.setVisible(False)
            self._pending = None
            # Trigger continue rebase secara otomatis
            QTimer.singleShot(600, self.start_sync)

    # ── Remote ────────────────────────────────────────────────────────

    def _set_remote(self) -> None:
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

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
