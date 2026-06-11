"""noteration/controllers/index_controller.py
Manages PDF indexing and link graph building in background threads.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

from noteration.core.repository import NoteRepository
from noteration.db.link_graph import LinkGraph
from noteration.literature.papis_bridge import PapisBridge
from noteration.logger import get_logger
from noteration.pdf.pdf_index import PdfIndex
from noteration.search.fts_engine import FTSEngine

logger = get_logger(__name__)


class _ScanWorker(QObject):
    """Worker for PDF indexing in a background thread."""

    done = Signal(int)
    error = Signal(str)

    def __init__(
        self, pdf_index: PdfIndex, library_path: Path, stop_check: Callable[[], bool]
    ) -> None:
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
    """Worker for LinkGraph building and FTS indexing in a background thread."""

    done = Signal(int)
    progress = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        graph: LinkGraph,
        fts: Optional[FTSEngine],
        papis: Optional[PapisBridge],
        notes: NoteRepository,
        force: bool,
        stop_check: Callable[[], bool],
    ) -> None:
        super().__init__()
        self.graph = graph
        self.fts = fts
        self.papis = papis
        self.notes = notes
        self.force = force
        self.stop_check = stop_check

    def run(self) -> None:
        try:
            if not self.force:
                self.graph.load()

            # 1. Index Literature Tags
            self._index_literature_tags()
            if self.stop_check():
                return

            # 2. Rebuild Link Graph & Index Notes
            count = self._index_notes()

            self.done.emit(count)
        except Exception as e:
            logger.exception(f"Index worker failed: {e}")
            self.error.emit(str(e))
            self.done.emit(0)
        finally:
            if self.fts:
                self.fts.close()

    def _index_literature_tags(self) -> None:
        """Stage 1: Literature Metadata Indexing."""
        if not self.fts or not self.papis:
            return

        self.progress.emit("Indexing literature tags...")
        try:
            entries = self.papis.all_entries()
            with self.fts.connection() as conn:
                for entry in entries:
                    if self.stop_check() or QThread.currentThread().isInterruptionRequested():
                        break
                    if entry.tags and conn:
                        conn.execute(
                            "DELETE FROM tags WHERE id_ref = ? AND source = 'literature'",
                            (entry.key,),
                        )
                        for tag in entry.tags:
                            conn.execute(
                                "INSERT INTO tags (id_ref, tag, source) VALUES (?, ?, ?)",
                                (entry.key, tag, "literature"),
                            )
        except Exception as e:
            logger.warning(f"Failed to index literature tags: {e}")

    def _index_notes(self) -> int:
        """Stage 2: Link Graph & Full-Text Indexing."""
        if not self.notes.notes_dir.exists():
            return 0

        self.progress.emit("Indexing notes and building graph...")
        count = 0

        # Idiomatic use of FTS connection context manager
        fts_cm = self.fts.connection() if self.fts else None

        try:
            # We wrap the loop in the context manager if available
            # Note: connection() yield a sqlite3.Connection
            with fts_cm if fts_cm else contextlib.nullcontext() as conn:
                for md_file in self.notes.list_notes():
                    if self.stop_check() or QThread.currentThread().isInterruptionRequested():
                        break

                    note_id = self.graph._get_note_id(md_file)
                    try:
                        mtime = md_file.stat().st_mtime
                    except Exception as e:
                        logger.debug(f"Failed to get mtime for {md_file}: {e}")
                        continue

                    # Update Graph (without saving yet)
                    self.graph.update_note(md_file, save_after=False)

                    # Update FTS
                    if self.fts and conn and (self.force or self.fts.needs_update(note_id, mtime)):
                        try:
                            content = md_file.read_text(encoding="utf-8")
                            title = md_file.stem
                            for line in content.splitlines():
                                if line.startswith("# "):
                                    title = line[2:].strip()
                                    break

                            conn.execute(
                                "INSERT OR REPLACE INTO file_metadata (note_id, mtime) VALUES (?, ?)",
                                (note_id, mtime),
                            )
                            conn.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
                            conn.execute(
                                "INSERT INTO notes_fts (note_id, title, content) VALUES (?, ?, ?)",
                                (note_id, title, content),
                            )

                            tags = re.findall(r"(?:^|\s)#([\w-]+)", content)
                            if tags:
                                conn.execute(
                                    "DELETE FROM tags WHERE id_ref = ? AND source = 'note'",
                                    (note_id,),
                                )
                                for tag in tags:
                                    conn.execute(
                                        "INSERT INTO tags (id_ref, tag, source) VALUES (?, ?, ?)",
                                        (note_id, tag, "note"),
                                    )

                            count += 1
                        except Exception as e:
                            logger.warning(f"Failed to FTS index {md_file}: {e}")

            self.graph.save()
            return count
        except Exception as e:
            logger.exception(f"Error during note indexing: {e}")
            return count


class IndexController(QObject):
    """Orchestrates indexing tasks for a vault."""

    indexing_finished = Signal(int)
    graph_updated = Signal(int)
    status_message = Signal(str, int)

    def __init__(
        self,
        pdf_index: PdfIndex,
        graph: LinkGraph,
        fts: Optional[FTSEngine],
        papis: Optional[PapisBridge],
        notes: NoteRepository,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.pdf_index = pdf_index
        self.graph = graph
        self.fts = fts
        self.papis = papis
        self.notes = notes

        self.library_path = papis.library_path if papis else None

        self._is_shutting_down = False
        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[_ScanWorker] = None
        self._graph_thread: Optional[QThread] = None
        self._graph_worker: Optional[_GraphWorker] = None

    def scan_pdfs(self) -> None:
        if self._is_shutting_down or not self.library_path:
            return
        if self._scan_thread and self._scan_thread.isRunning():
            return

        self._scan_thread = QThread()
        self._scan_worker = _ScanWorker(
            self.pdf_index, self.library_path, stop_check=lambda: self._is_shutting_down
        )
        self._scan_worker.moveToThread(self._scan_thread)

        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.error.connect(lambda msg: self.status_message.emit(msg, 5000))
        self._scan_worker.done.connect(self._scan_thread.quit)
        self._scan_worker.done.connect(self._clear_scan_worker)
        self._scan_thread.started.connect(self._scan_worker.run)
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
        if self._graph_thread and self._graph_thread.isRunning():
            return

        self._graph_thread = QThread()
        self._graph_worker = _GraphWorker(
            self.graph,
            self.fts,
            self.papis,
            self.notes,
            force,
            stop_check=lambda: self._is_shutting_down,
        )

        self._graph_worker.moveToThread(self._graph_thread)

        self._graph_worker.done.connect(self._on_graph_done)
        self._graph_worker.progress.connect(lambda msg: self.status_message.emit(msg, 0))
        self._graph_worker.error.connect(lambda msg: self.status_message.emit(msg, 5000))
        self._graph_worker.done.connect(self._graph_thread.quit)
        self._graph_worker.done.connect(self._clear_graph_worker)
        self._graph_thread.started.connect(self._graph_worker.run)
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
        """Gracefully and safely shut down all background threads."""
        self._is_shutting_down = True

        # 1. Stop Workers and Block Signals
        # We block signals instead of manual disconnect to avoid RuntimeError
        # if the worker is already partially destroyed by Qt.
        for worker in [self._scan_worker, self._graph_worker]:
            if worker:
                worker.blockSignals(True)

        # 2. Shutdown threads using a safe pattern
        self._safe_stop_thread("_scan_thread")
        self._safe_stop_thread("_graph_thread")

        self._scan_worker = None
        self._graph_worker = None

        # 3. Save state
        self.pdf_index.save()
        self.graph.save()

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
