"""
noteration/vault_manager.py
Core engine orchestrator and background task manager for a single vault.
Delegates specialized tasks to controllers (Index, Sync, Library).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from noteration.config import NoterationConfig
from noteration.controllers.index_controller import IndexController
from noteration.controllers.sync_controller import SyncController
from noteration.controllers.library_controller import LibraryController
from noteration.search.vault_search import VaultSearch
from noteration.logger import setup_logging, get_logger

logger = get_logger(__name__)


class VaultManager(QObject):
    """
    Manager that handles the state and business operations of a Vault.
    MainWindow interacts with this Manager, which delegates to specialized controllers.
    """
    
    # Proxy signals (for backward compatibility with MainWindow)
    status_message = Signal(str, int)
    git_status_updated = Signal(object)
    indexing_finished = Signal(int)
    graph_updated = Signal(int)

    @property
    def library(self) -> LibraryController:
        return self._library_controller

    def __init__(self, vault_path: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        self._init_directories()
        setup_logging(vault_path)
        logger.info(f"Initializing VaultManager for {vault_path}")

        self.config = NoterationConfig(vault_path)
        
        # Controllers
        self.index = IndexController(vault_path, self.config.papis_library, self)
        self.sync = SyncController(vault_path, self)
        self._library_controller = LibraryController(self.config.papis_library, self)
        self.search_engine = VaultSearch(vault_path, self._library_controller.bridge)

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
    def is_syncing(self) -> bool:
        return self.sync.is_syncing

    @is_syncing.setter
    def is_syncing(self, value: bool) -> None:
        self.sync.is_syncing = value

    @property
    def papis(self):
        return self.library.bridge

    @property
    def git_repo(self):
        return self.sync.git_repo

    @property
    def pdf_index(self):
        return self.index.pdf_index

    @property
    def graph(self):
        return self.index.graph

    def _init_directories(self) -> None:
        """Ensure all required vault subdirectories exist."""
        for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
            (self.vault_path / sub).mkdir(parents=True, exist_ok=True)

    def save_all(self) -> None:
        """Persist all in-memory data to disk."""
        self.graph.save()
        self.pdf_index.save()
        self.config.save()

    def shutdown(self) -> None:
        """Gracefully stop all background threads and save final state."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        
        logger.info("Shutting down controllers...")
        self.index.shutdown()
        self.sync.shutdown()
        self.library.shutdown()
        
        logger.info("Persisting final vault state...")
        self.save_all()
        logger.info("Vault shutdown complete")

    # ── Background Task Delegation ───────────────────────────────────

    def scan_pdfs(self) -> None:
        self.index.scan_pdfs()

    def build_graph(self, force: bool = False) -> None:
        self.index.build_graph(force=force)

    def request_git_status(self, fetch: bool = False) -> None:
        self.sync.request_status(fetch=fetch)

    def refresh_git_repo(self) -> None:
        self.sync.refresh_git_repo()

    def update_note_in_graph(self, note_path: Path) -> None:
        self.graph.update_note(note_path)
        self.graph_updated.emit(1)
