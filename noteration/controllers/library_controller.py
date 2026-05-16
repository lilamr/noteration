"""
noteration/controllers/library_controller.py
Manages Papis literature library in background threads.
"""

from __future__ import annotations

import shiboken6
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThread

from noteration.literature.papis_bridge import PapisBridge
from noteration.logger import get_logger

logger = get_logger(__name__)


class _LoadEntriesWorker(QObject):
    """Load Papis entries in a background thread."""
    done = Signal(list)
    error = Signal(str)

    def __init__(self, bridge: PapisBridge, force: bool = False) -> None:
        super().__init__()
        self.bridge = bridge
        self.force = force

    def run(self) -> None:
        try:
            entries = self.bridge.all_entries(force_reload=self.force)
            self.done.emit(entries)
        except Exception as e:
            logger.exception(f"Background literature load failed: {e}")
            self.error.emit(f"Failed to load literature: {str(e)}")
            self.done.emit([])


class LibraryController(QObject):
    """Orchestrates literature tasks for a vault."""
    
    entries_loaded = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, library_path: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.library_path = library_path
        self._bridge = PapisBridge(library_path)
        self._load_thread: Optional[QThread] = None
        self._load_worker: Optional[_LoadEntriesWorker] = None

    @property
    def bridge(self) -> PapisBridge:
        return self._bridge

    def load_entries(self, force: bool = False) -> None:
        if self._load_thread and shiboken6.isValid(self._load_thread) and self._load_thread.isRunning():
            return

        self._load_thread = QThread()
        self._load_worker = _LoadEntriesWorker(self._bridge, force)
        self._load_worker.moveToThread(self._load_thread)

        self._load_worker.done.connect(self._on_entries_loaded)
        self._load_worker.error.connect(self.error_occurred)
        self._load_worker.done.connect(self._load_thread.quit)
        self._load_worker.done.connect(self._load_worker.deleteLater)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_thread.finished.connect(self._load_thread.deleteLater)
        self._load_thread.finished.connect(lambda: setattr(self, "_load_thread", None))
        self._load_thread.start()

    def _on_entries_loaded(self, entries: list) -> None:
        self.entries_loaded.emit(entries)

    def shutdown(self) -> None:
        if self._load_thread and shiboken6.isValid(self._load_thread) and self._load_thread.isRunning():
            self._load_thread.quit()
            self._load_thread.wait(1000)
        self._load_worker = None
        self._load_thread = None
