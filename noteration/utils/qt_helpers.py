"""Qt helper utilities for Noteration.
Contains base classes for threading and workers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from noteration.db.link_graph import LinkGraph
    from noteration.search.fts_engine import FTSEngine


class BaseWorker(QObject):
    """Base class for all background workers in Noteration.
    Provides a standardized interface for signals and execution.
    """

    # Standard signals
    # subclasses can override these with more specific types if needed,
    # but the names should remain consistent.
    finished = Signal()
    error = Signal(str)

    def run(self) -> None:
        """Main execution logic to be implemented by subclasses.
        This method will be called when the thread starts.
        """
        raise NotImplementedError("Subclasses must implement run()")


class SaveWorker(BaseWorker):
    """Worker to handle background note saving, FTS indexing, and graph updates."""

    def __init__(
        self,
        file_path: "Path",
        content: str,
        fts: Optional["FTSEngine"] = None,
        graph: Optional["LinkGraph"] = None,
        note_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        """Initialize the SaveWorker with file path, content, and optional engines."""
        super().__init__()
        self.file_path = file_path
        self.content = content
        self.fts = fts
        self.graph = graph
        self.note_id = note_id
        self.tags = tags

    def run(self) -> None:
        """Perform saving and indexing in the background."""
        try:
            # 1. Write file to disk (I/O)
            self.file_path.write_text(self.content, encoding="utf-8")

            # 2. Update FTS tags if applicable
            if self.fts and self.note_id and self.tags is not None:
                try:
                    self.fts.index_tags(self.note_id, self.tags, "note")
                except Exception as e:
                    logging.getLogger(__name__).error(f"SaveWorker: FTS indexing failed: {e}")

            # 3. Update Link Graph if applicable
            if self.graph:
                try:
                    self.graph.update_note(self.file_path, save_after=True)
                except Exception as e:
                    logging.getLogger(__name__).error(f"SaveWorker: Graph update failed: {e}")

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
