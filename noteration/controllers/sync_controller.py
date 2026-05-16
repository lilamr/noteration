"""
noteration/controllers/sync_controller.py
Manages Git synchronization in background threads.
"""

from __future__ import annotations

import shiboken6
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThread

from noteration.sync.git_engine import GitRepo
from noteration.logger import get_logger

logger = get_logger(__name__)


class _StatusWorker(QObject):
    """Worker to check Git status in a background thread."""
    done = Signal(object)
    error = Signal(str)

    def __init__(self, repo: GitRepo, fetch: bool = False) -> None:
        super().__init__()
        self.repo = repo
        self.fetch = fetch

    def run(self) -> None:
        try:
            status = self.repo.status(fetch=self.fetch)
            self.done.emit(status)
        except Exception as e:
            logger.exception(f"Background status check failed: {e}")
            self.error.emit(f"Git status check failed: {str(e)}")
            self.done.emit(None)


class SyncController(QObject):
    """Orchestrates Git tasks for a vault."""
    
    git_status_updated = Signal(object)
    status_message = Signal(str, int)

    def __init__(self, vault_path: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        self._git_repo: Optional[GitRepo] = None
        self._is_shutting_down = False
        self._is_syncing = False
        self._status_thread: Optional[QThread] = None
        self._status_worker: Optional[_StatusWorker] = None

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing

    @is_syncing.setter
    def is_syncing(self, value: bool) -> None:
        self._is_syncing = value

    @property
    def git_repo(self) -> Optional[GitRepo]:
        if self._git_repo is None:
            self.refresh_git_repo()
        return self._git_repo

    def refresh_git_repo(self) -> None:
        if (self.vault_path / ".git").exists():
            if not self._git_repo or not self._git_repo.is_valid:
                self._git_repo = GitRepo(self.vault_path)
                self._git_repo.ensure_ignored()
        else:
            self._git_repo = None

    def request_status(self, fetch: bool = False) -> None:
        if self._is_shutting_down:
            return
        if not self.git_repo or not self.git_repo.is_valid:
            self.git_status_updated.emit(None)
            return
        
        if self._status_thread and shiboken6.isValid(self._status_thread) and self._status_thread.isRunning():
            return

        self._status_thread = QThread()
        self._status_worker = _StatusWorker(self.git_repo, fetch=fetch)
        self._status_worker.moveToThread(self._status_thread)
        
        self._status_worker.done.connect(self._status_thread.quit)
        self._status_worker.error.connect(lambda msg: self.status_message.emit(msg, 5000))
        self._status_worker.done.connect(self.git_status_updated)
        self._status_worker.done.connect(self._status_worker.deleteLater)
        self._status_thread.started.connect(self._status_worker.run)
        self._status_thread.finished.connect(self._status_thread.deleteLater)
        self._status_thread.finished.connect(lambda: setattr(self, "_status_thread", None))
        self._status_thread.start()

    def shutdown(self) -> None:
        self._is_shutting_down = True
        if self._status_thread and shiboken6.isValid(self._status_thread) and self._status_thread.isRunning():
            self._status_thread.quit()
            if not self._status_thread.wait(2000):
                self._status_thread.terminate()
        self._status_worker = None
        self._status_thread = None
