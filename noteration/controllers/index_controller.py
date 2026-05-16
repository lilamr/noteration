"""
noteration/controllers/index_controller.py
Manages PDF indexing and link graph building in background threads.
"""

from __future__ import annotations

import shiboken6
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal, QThread

from noteration.pdf.pdf_index import PdfIndex
from noteration.db.link_graph import LinkGraph
from noteration.logger import get_logger

logger = get_logger(__name__)


class _ScanWorker(QObject):
    """Worker for PDF indexing in a background thread."""
    done = Signal(int)
    error = Signal(str)

    def __init__(self, pdf_index: PdfIndex, library_path: Path, stop_check: Callable[[], bool]) -> None:
        super().__init__()
        self.pdf_index = pdf_index
        self.library_path = library_path
        self.stop_check = stop_check

    def run(self) -> None:
        try:
            self.pdf_index.load()
            count = self.pdf_index.scan_vault(self.library_path, check_stop=self.stop_check)
            self.done.emit(count)
        except (IOError, OSError) as e:
            msg = f"IO error during background PDF scan: {e}"
            logger.error(msg)
            self.error.emit(msg)
            self.done.emit(0)
        except Exception as e:
            logger.exception(f"Unexpected error during background PDF scan: {e}")
            self.error.emit(f"PDF indexing failed: {str(e)}")
            self.done.emit(0)


class _GraphWorker(QObject):
    """Worker for LinkGraph building in a background thread."""
    done = Signal(int)
    error = Signal(str)

    def __init__(self, graph: LinkGraph, force: bool, stop_check: Callable[[], bool]) -> None:
        super().__init__()
        self.graph = graph
        self.force = force
        self.stop_check = stop_check

    def run(self) -> None:
        try:
            if not self.force and self.graph.load():
                self.done.emit(0)
                return
                
            count = self.graph.build_from_vault(force=self.force, check_stop=self.stop_check)
            self.done.emit(count)
        except (IOError, OSError) as e:
            msg = f"IO error during background graph build: {e}"
            logger.error(msg)
            self.error.emit(msg)
            self.done.emit(0)
        except Exception as e:
            logger.exception(f"Unexpected error during background graph build: {e}")
            self.error.emit(f"Graph build failed: {str(e)}")
            self.done.emit(0)


class IndexController(QObject):
    """Orchestrates indexing tasks for a vault."""
    
    indexing_finished = Signal(int)
    graph_updated = Signal(int)
    status_message = Signal(str, int)

    def __init__(self, vault_path: Path, library_path: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        self.library_path = library_path
        self.pdf_index = PdfIndex(vault_path)
        self.graph = LinkGraph(vault_path)
        
        self._is_shutting_down = False
        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[_ScanWorker] = None
        self._graph_thread: Optional[QThread] = None
        self._graph_worker: Optional[_GraphWorker] = None

    def scan_pdfs(self) -> None:
        if self._is_shutting_down:
            return
        if self._scan_thread and shiboken6.isValid(self._scan_thread) and self._scan_thread.isRunning():
            return

        self._scan_thread = QThread()
        self._scan_worker = _ScanWorker(
            self.pdf_index, 
            self.library_path,
            stop_check=lambda: self._is_shutting_down
        )
        self._scan_worker.moveToThread(self._scan_thread)

        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.error.connect(lambda msg: self.status_message.emit(msg, 5000))
        self._scan_worker.done.connect(self._scan_thread.quit)
        self._scan_worker.done.connect(self._clear_scan_worker)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.finished.connect(lambda: setattr(self, "_scan_thread", None))
        self._scan_thread.start()

    def _clear_scan_worker(self) -> None:
        if self._scan_worker:
            self._scan_worker.deleteLater()
            self._scan_worker = None

    def _on_scan_done(self, count: int) -> None:
        self.indexing_finished.emit(count)
        if count > 0:
            self.status_message.emit(f"PDF index: {count} new files indexed.", 3000)

    def build_graph(self, force: bool = False) -> None:
        if self._is_shutting_down:
            return
        if self._graph_thread and shiboken6.isValid(self._graph_thread) and self._graph_thread.isRunning():
            return

        self._graph_thread = QThread()
        self._graph_worker = _GraphWorker(
            self.graph, 
            force=force,
            stop_check=lambda: self._is_shutting_down
        )
        self._graph_worker.moveToThread(self._graph_thread)

        self._graph_worker.done.connect(self._on_graph_done)
        self._graph_worker.error.connect(lambda msg: self.status_message.emit(msg, 5000))
        self._graph_worker.done.connect(self._graph_thread.quit)
        self._graph_worker.done.connect(self._clear_graph_worker)
        self._graph_thread.started.connect(self._graph_worker.run)
        self._graph_thread.finished.connect(self._graph_thread.deleteLater)
        self._graph_thread.finished.connect(lambda: setattr(self, "_graph_thread", None))
        self._graph_thread.start()

    def _clear_graph_worker(self) -> None:
        if self._graph_worker:
            self._graph_worker.deleteLater()
            self._graph_worker = None

    def _on_graph_done(self, count: int) -> None:
        if count > 0:
            self.status_message.emit(f"Backlink graph: {count} links found.", 3000)
        self.graph_updated.emit(count)

    def shutdown(self) -> None:
        self._is_shutting_down = True
        for attr in ["_scan_thread", "_graph_thread"]:
            thread = getattr(self, attr, None)
            if thread and shiboken6.isValid(thread) and thread.isRunning():
                thread.quit()
                if not thread.wait(2000):
                    thread.terminate()
            setattr(self, attr, None)
        self._scan_worker = None
        self._graph_worker = None
        
        # Save state
        self.pdf_index.save()
        self.graph.save()
