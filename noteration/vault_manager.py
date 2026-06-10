"""GUI Adapter for VaultCore.

Provides Qt signals for the UI while delegating business logic to VaultCore.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from noteration.core.vault_core import VaultCore
from noteration.controllers.index_controller import IndexController
from noteration.controllers.sync_controller import SyncController
from noteration.controllers.library_controller import LibraryController
from noteration.logger import get_logger

logger = get_logger(__name__)


class VaultManager(QObject):
    """Manager that handles the state and business operations of a Vault.

    MainWindow interacts with this Manager, which delegates to specialized controllers.
    """

    # Proxy signals (for MainWindow)
    status_message = Signal(str, int)
    git_status_updated = Signal(object)
    indexing_finished = Signal(int)
    graph_updated = Signal(int)
    tags_updated = Signal()
    initialization_finished = Signal()

    def __init__(
        self,
        vault_path: Path,
        storage_path: Optional[Path] = None,
        secret_key: Optional[str] = None,
        session_path: Optional[Path] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        # Initialize the core business logic (Pure Python)
        self.core = VaultCore(
            vault_path, storage_path=storage_path, secret_key=secret_key, session_path=session_path
        )
        self.secret_key = secret_key

        # Shortcuts for UI compatibility
        self.vault_path = self.core.vault_path
        self.storage_path = self.core.storage_path
        self.config = self.core.config

        # Initialize Qt-based controllers as adapters
        self.index = IndexController(
            self.core.pdf_index,
            self.core.graph,
            self.core.fts,
            self.core.papis,
            self.core.notes,
            self,
        )
        self.sync = SyncController(self.core, self)
        self._library_controller = LibraryController(self.core.papis, self)

        self._connect_controller_signals()
        self._is_shutting_down = False

    def _connect_controller_signals(self) -> None:
        # Index signals
        self.index.indexing_finished.connect(self.indexing_finished)
        self.index.graph_updated.connect(self.graph_updated)
        self.index.status_message.connect(self.status_message)

        # Sync signals
        self.sync.git_status_updated.connect(self.git_status_updated)
        self.sync.status_message.connect(self.status_message)

    @property
    def library(self) -> LibraryController:
        """Return the library controller.
        """
        return self._library_controller

    @property
    def is_syncing(self) -> bool:
        """Return the syncing status.
        """
        return self.sync.is_syncing

    @is_syncing.setter
    def is_syncing(self, value: bool) -> None:
        self.sync.is_syncing = value

    @property
    def papis(self):
        """Return the Papis bridge.
        """
        return self.core.papis

    @property
    def git_repo(self):
        """Return the Git repository.
        """
        return self.core.git_repo

    @property
    def pdf_index(self):
        """Return the PDF index.
        """
        return self.core.pdf_index

    @property
    def graph(self):
        """Return the link graph.
        """
        return self.core.graph

    @property
    def search_engine(self):
        """Return the search engine.
        """
        return self.core.search_engine

    @property
    def csl(self):
        """Return the CSL renderer.
        """
        return self.core.csl

    def save_all(self) -> None:
        """Persist all in-memory data to disk.
        """
        self.core.save_all()

    def shutdown(self) -> None:
        """Gracefully stop all background threads and save final state.
        """
        if self._is_shutting_down:
            return
        self._is_shutting_down = True

        logger.info("Shutting down controllers...")
        self.index.shutdown()
        self.sync.shutdown()
        self.library.shutdown()

        logger.info("Persisting final vault state...")
        self.core.shutdown()
        logger.info("Vault shutdown complete")

    # ── Background Task Delegation ───────────────────────────────────

    def scan_pdfs(self) -> None:
        """Scan for PDFs.
        """
        self.index.scan_pdfs()

    def build_graph(self, force: bool = False) -> None:
        """Build the graph.
        """
        self.index.build_graph(force=force)

    def track_changes(self, path: Path) -> None:
        """Centralized trigger to update UI status.
        """
        if self.core.git_repo:
            self.request_git_status()

    def request_git_status(self, fetch: bool = False) -> None:
        """Request Git status.
        """
        self.sync.request_status(fetch=fetch)

    def refresh_csl_renderer(self) -> None:
        """Refresh CSL renderer.
        """
        self.core.refresh_csl_renderer()

    def update_note_in_graph(self, note_path: Path) -> None:
        """Update note in graph.
        """
        self.core.graph.update_note(note_path)
        self.graph_updated.emit(1)

    def permanently_decrypt(self) -> bool:
        """Permanently decrypt the vault by disabling encryption.

        Returns True if successful.
        """
        if self.core.disable_encryption():
            self.secret_key = None  # Clear secret key to signal no re-encryption
            return True
        return False

    def get_all_tags(self) -> list[tuple[str, str]]:
        """Get all tags.
        """
        if self._is_shutting_down or not self.core.fts:
            return []
        try:
            return self.core.fts.get_all_tags()
        except (AttributeError, RuntimeError):  # Assuming FTS might raise these on closed DB
            return []

    def get_tags_for_note(self, note_id: str) -> list[str]:
        """Get tags for a specific note.
        """
        if self._is_shutting_down or not self.core.fts:
            return []
        try:
            return self.core.fts.get_tags_for_note(note_id)
        except (AttributeError, RuntimeError):
            return []
