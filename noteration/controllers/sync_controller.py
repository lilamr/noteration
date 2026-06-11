"""noteration/controllers/sync_controller.py
Manages Git synchronization in background threads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from noteration.core.vault_core import VaultCore

from PySide6.QtCore import QObject, QThread, Signal

from noteration.logger import get_logger
from noteration.sync.git_engine import GitRepo

logger = get_logger(__name__)


class _StatusWorker(QObject):
    """Worker to check Git status in a background thread."""

    done = Signal(object)
    error = Signal(str)

    def __init__(self, repo: GitRepo, fetch: bool = False, session_hashes: dict[str, str] | None = None) -> None:
        super().__init__()
        self.repo = repo
        self.fetch = fetch
        self.session_hashes = session_hashes

    def run(self) -> None:
        try:
            status = self.repo.status(fetch=self.fetch, session_hashes=self.session_hashes)
            self.done.emit(status)
        except Exception as e:
            logger.exception(f"Background status check failed: {e}")
            self.error.emit(f"Git status check failed: {str(e)}")
            self.done.emit(None)


class SyncController(QObject):
    """Orchestrates Git tasks for a vault."""

    git_status_updated = Signal(object)
    status_message = Signal(str, int)

    def __init__(self, core: VaultCore, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.core = core
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
        return self.core.git_repo

    def refresh_git_repo(self) -> None:
        self.core.refresh_git_repo()

    def request_status(self, fetch: bool = False) -> None:
        if self._is_shutting_down:
            return
        if not self.git_repo or not self.git_repo.is_valid:
            self.git_status_updated.emit(None)
            return

        if self._status_thread and self._status_thread.isRunning():
            return

        self._status_thread = QThread()
        self._status_worker = _StatusWorker(
            self.git_repo, fetch=fetch, session_hashes=self.core.session_hashes
        )
        self._status_worker.moveToThread(self._status_thread)

        self._status_worker.done.connect(self._status_thread.quit)
        self._status_worker.error.connect(lambda msg: self.status_message.emit(msg, 5000))
        self._status_worker.done.connect(self.git_status_updated)
        self._status_worker.done.connect(self._status_worker.deleteLater)
        self._status_thread.started.connect(self._status_worker.run)
        self._status_thread.start()

    def shutdown(self) -> None:
        self._is_shutting_down = True
        self._safe_stop_thread("_status_thread")
        self._status_worker = None

    def _safe_stop_thread(self, attr_name: str) -> None:
        """Helper to safely stop a QThread stored in an attribute without blocking."""
        thread = getattr(self, attr_name, None)
        if thread and thread.isRunning():
            thread.requestInterruption()
            thread.quit()
            # Wait for the thread to actually finish to avoid Segfaults on exit
            if not thread.wait(5000):
                logger.warning(f"Thread {attr_name} failed to stop within timeout.")

        setattr(self, attr_name, None)
