"""noteration/controllers/library_controller.py
Manages Papis literature library in background threads.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QObject, QThread, Signal

from noteration.literature.papis_bridge import PapisBridge
from noteration.logger import get_logger

logger = get_logger(__name__)


class _LoadEntriesWorker(QObject):
    """Load Papis entries in a background thread."""

    done = Signal(list)
    error = Signal(str)

    def __init__(
        self, bridge: PapisBridge, force: bool = False, fts_engine: Optional[Any] = None
    ) -> None:
        super().__init__()
        self.bridge = bridge
        self.force = force
        self.fts_engine = fts_engine

    def run(self) -> None:
        try:
            entries = self.bridge.all_entries(force_reload=self.force, fts_engine=self.fts_engine)
            self.done.emit(entries)
        except Exception as e:
            logger.exception(f"Background literature load failed: {e}")
            self.error.emit(f"Failed to load literature: {str(e)}")
            self.done.emit([])


class LibraryController(QObject):
    """Orchestrates literature tasks for a vault."""

    entries_loaded = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, bridge: PapisBridge, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._load_thread: Optional[QThread] = None
        self._load_worker: Optional[_LoadEntriesWorker] = None

    @property
    def bridge(self) -> PapisBridge:
        return self._bridge

    def load_entries(self, force: bool = False, fts_engine: Optional[Any] = None) -> None:
        if self._load_thread and self._load_thread.isRunning():
            return

        self._load_thread = QThread()
        self._load_worker = _LoadEntriesWorker(self._bridge, force, fts_engine=fts_engine)
        self._load_worker.moveToThread(self._load_thread)

        self._load_worker.done.connect(self._on_entries_loaded)
        self._load_worker.error.connect(self.error_occurred)
        self._load_worker.done.connect(self._load_thread.quit)
        self._load_worker.done.connect(self._load_worker.deleteLater)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_thread.start()

    def _on_entries_loaded(self, entries: list) -> None:
        self.entries_loaded.emit(entries)

    def shutdown(self) -> None:
        self._safe_stop_thread("_load_thread")
        self._load_worker = None

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
