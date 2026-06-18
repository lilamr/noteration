"""noteration/controllers/library_controller.py
Manages Papis literature library in background threads.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QObject, QThread, Signal

from noteration.literature.papis_bridge import PapisBridge
from noteration.logger import get_logger
from noteration.utils.qt_helpers import BaseWorker

logger = get_logger(__name__)


class _LoadEntriesWorker(BaseWorker):
    """Worker for loading Papis literature entries in a background thread."""

    finished = Signal(list)

    def __init__(
        self, bridge: PapisBridge, force: bool = False, fts_engine: Optional[Any] = None
    ) -> None:
        """Initialize the load worker.

        Args:
            bridge: The Papis bridge instance.
            force: Whether to force reload entries.
            fts_engine: Optional FTS engine for search indexing.
        """
        super().__init__()
        self.bridge = bridge
        self.force = force
        self.fts_engine = fts_engine

    def run(self) -> None:
        """Execute the entry loading process."""
        try:
            entries = self.bridge.all_entries(force_reload=self.force, fts_engine=self.fts_engine)
            self.finished.emit(entries)
        except Exception as e:
            logger.exception(f"Background literature load failed: {e}")
            self.error.emit(f"Failed to load literature: {str(e)}")
            self.finished.emit([])


class LibraryController(QObject):
    """Orchestrates literature management tasks for a vault."""

    entries_loaded = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, bridge: PapisBridge, parent: Optional[QObject] = None) -> None:
        """Initialize the library controller.

        Args:
            bridge: The Papis bridge instance.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._bridge = bridge
        self._load_thread: Optional[QThread] = None
        self._load_worker: Optional[_LoadEntriesWorker] = None

    @property
    def bridge(self) -> PapisBridge:
        """Return the Papis bridge."""
        return self._bridge

    def load_entries(self, force: bool = False, fts_engine: Optional[Any] = None) -> None:
        """Start loading literature entries in a background thread.

        Args:
            force: Whether to force reload entries.
            fts_engine: Optional FTS engine.
        """
        if self._load_thread and self._load_thread.isRunning():
            return

        self._load_thread = QThread()
        self._load_worker = _LoadEntriesWorker(self._bridge, force, fts_engine=fts_engine)
        self._load_worker.moveToThread(self._load_thread)

        self._load_worker.finished.connect(self._on_entries_loaded)
        self._load_worker.error.connect(self.error_occurred)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_worker.finished.connect(self._clear_load_worker)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_thread.start()

    def _clear_load_worker(self) -> None:
        """Safely delete and nullify the load worker."""
        if self._load_worker:
            self._load_worker.deleteLater()
            self._load_worker = None

    def _on_entries_loaded(self, entries: list) -> None:
        """Slot for handling loaded entries."""
        self.entries_loaded.emit(entries)

    def shutdown(self) -> None:
        """Shutdown the controller and stop threads."""
        self._safe_stop_thread("_load_thread")
        self._load_worker = None

    def _safe_stop_thread(self, attr_name: str) -> None:
        """Helper to safely stop a QThread stored in an attribute.
        Ensures the Python reference is held if the thread fails to stop.
        """
        thread = getattr(self, attr_name, None)
        if thread and thread.isRunning():
            thread.requestInterruption()
            thread.quit()
            if thread.wait(5000):
                # Only nullify if the thread actually stopped
                setattr(self, attr_name, None)
            else:
                logger.error(f"Thread {attr_name} failed to stop within 5s. Holding reference to prevent crash.")
        else:
            setattr(self, attr_name, None)
