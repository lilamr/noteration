"""GUI Adapter for VaultCore.

Provides Qt signals for the UI while delegating business logic to VaultCore.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from noteration.config import NoterationConfig
    from noteration.db.link_graph import LinkGraph
    from noteration.literature.csl_renderer import CSLRenderer
    from noteration.literature.papis_bridge import PapisBridge
    from noteration.pdf.pdf_index import PdfIndex
    from noteration.search.vault_search import VaultSearch
    from noteration.sync.git_engine import GitRepo

from PySide6.QtCore import QObject, QThread, Signal

from noteration.controllers.index_controller import IndexController
from noteration.controllers.library_controller import LibraryController
from noteration.controllers.sync_controller import SyncController
from noteration.core.session_state import SessionStateStore
from noteration.core.vault_core import VaultCore
from noteration.logger import get_logger
from noteration.utils.qt_helpers import SaveWorker

logger = get_logger(__name__)


class VaultManager(QObject):
    """Adapter for coordinating UI components and VaultCore logic.

    Acts as the primary bridge between the MainWindow and business logic.
    Delegates operations to specialized controllers (IndexController,
    SyncController, LibraryController) and manages the lifecycle of
    the underlying VaultCore instance.
    """

    # Core components
    core: VaultCore
    config: NoterationConfig
    session_state: SessionStateStore
    vault_path: Path
    storage_path: Path
    secret_key: Optional[str]

    # Controllers
    index: IndexController
    sync: SyncController
    _library_controller: LibraryController
    _is_shutting_down: bool

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
        """Initializes the VaultManager.

        Args:
            vault_path: Path to the root of the vault directory.
            storage_path: Optional path to the storage directory for indices and metadata.
            secret_key: Optional encryption key to unlock the vault.
            session_path: Optional path for temporary session data.
            parent: Optional parent QObject for Qt's object hierarchy.
        """
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
        self.session_state = self.core.session_state

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
        self._pdf_threads: list[QThread] = []

    def register_pdf_thread(self, thread: QThread) -> None:
        """Register a PDF processing thread to be managed by VaultManager."""
        self._pdf_threads.append(thread)
        thread.finished.connect(lambda: self._pdf_threads.remove(thread) if thread in self._pdf_threads else None)

    def unregister_pdf_thread(self, thread: QThread) -> None:
        """Unregister a PDF processing thread."""
        if thread in self._pdf_threads:
            self._pdf_threads.remove(thread)

    def _connect_controller_signals(self) -> None:
        """Connect signals from the specialized controllers to the manager's signals."""
        # Index signals
        self.index.indexing_finished.connect(self.indexing_finished)
        self.index.graph_updated.connect(self.graph_updated)
        self.index.status_message.connect(self.status_message)

        # Sync signals
        self.sync.git_status_updated.connect(self.git_status_updated)
        self.sync.status_message.connect(self.status_message)
        """Connect signals from the specialized controllers to the manager's signals."""
        # Index signals
        self.index.indexing_finished.connect(self.indexing_finished)
        self.index.graph_updated.connect(self.graph_updated)
        self.index.status_message.connect(self.status_message)

        # Sync signals
        self.sync.git_status_updated.connect(self.git_status_updated)
        self.sync.status_message.connect(self.status_message)

    @property
    def library(self) -> LibraryController:
        """Returns the controller for managing the literature library."""
        return self._library_controller

    @property
    def is_syncing(self) -> bool:
        """Checks if a Git synchronization operation is in progress.

        Returns:
            True if synchronization is currently active, False otherwise.
        """
        return self.sync.is_syncing

    @is_syncing.setter
    def is_syncing(self, value: bool) -> None:
        self.sync.is_syncing = value

    @property
    def papis(self) -> PapisBridge:
        """Returns the bridge interface for interacting with Papis literature."""
        return self.core.papis

    @property
    def git_repo(self) -> Optional[GitRepo]:
        """Returns the Git repository interface, if initialized."""
        return self.core.git_repo

    @property
    def pdf_index(self) -> PdfIndex:
        """Returns the PDF indexer instance."""
        return self.core.pdf_index

    @property
    def graph(self) -> LinkGraph:
        """Returns the graph representation of note links."""
        return self.core.graph

    @property
    def search_engine(self) -> VaultSearch:
        """Returns the search engine instance."""
        return self.core.search_engine

    @property
    def csl(self) -> CSLRenderer:
        """Returns the CSL renderer for literature citations."""
        return self.core.csl

    def save_all(self) -> None:
        """Persists all in-memory vault data to disk."""
        self.core.save_all()

    def shutdown(self) -> None:
        """Gracefully shuts down all background tasks and saves final state.

        Performs cleanup of controllers and persists the core Vault state.
        """
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        
        logger.info("Terminating background PDF threads...")
        for thread in self._pdf_threads:
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
                if thread.isRunning():
                    thread.terminate()

        logger.info("Shutting down controllers...")
        self.index.shutdown()
        self.sync.shutdown()
        self.library.shutdown()

        logger.info("Persisting final vault state...")
        self.core.shutdown()
        logger.info("Vault shutdown complete")

    # ── Background Task Delegation ───────────────────────────────────

    def scan_pdfs(self) -> None:
        """Triggers a scan for new or updated PDFs in the vault."""
        self.index.scan_pdfs()

    def build_graph(self, force: bool = False) -> None:
        """Rebuilds the note link graph.

        Args:
            force: If True, forces a rebuild of the entire graph.
        """
        self.index.build_graph(force=force)

    def track_changes(self, path: Path) -> None:
        """Triggers a check for Git status updates for the given path.

        Args:
            path: The path of the modified resource.
        """
        if self.core.git_repo:
            self.request_git_status()

    def request_git_status(self, fetch: bool = False) -> None:
        """Requests a Git status update from the sync controller.

        Args:
            fetch: If True, performs a fetch from remote before checking status.
        """
        self.sync.request_status(fetch=fetch)

    def refresh_csl_renderer(self) -> None:
        """Refreshes the CSL renderer configuration."""
        self.core.refresh_csl_renderer()

    def update_note_in_graph(self, note_path: Path) -> None:
        """Updates a specific note in the link graph.

        Args:
            note_path: Path to the note to update.
        """
        self.core.graph.update_note(note_path)
        self.graph_updated.emit(1)

    def save_note(self, note_path: Path, content: str) -> SaveWorker:
        """Creates a background worker to save and index a note.

        Args:
            note_path: Path to the note file.
            content: The plaintext content of the note.

        Returns:
            A SaveWorker instance ready to be moved to a thread.
        """
        # Prepare metadata in main thread (regex and path logic)
        try:
            rel = note_path.relative_to(self.vault_path / "notes")
            note_id = str(rel.with_suffix(""))
        except ValueError:
            note_id = note_path.stem

        tags = list(set(re.findall(r"(?:^|\s)#([\w-]+)", content)))

        worker = SaveWorker(
            note_path,
            content,
            fts=self.core.fts,
            graph=self.core.graph,
            note_id=note_id,
            tags=tags,
        )
        return worker

    def permanently_decrypt(self) -> bool:
        """Permanently disables encryption for the vault.

        Returns:
            True if encryption was successfully disabled, False otherwise.
        """
        if self.core.disable_encryption():
            self.secret_key = None  # Clear secret key to signal no re-encryption
            return True
        return False

    def get_all_tags(self) -> list[tuple[str, str]]:
        """Retrieves all tags present in the vault.

        Returns:
            A list of tuples, where each tuple contains (tag_name, tag_count).
        """
        if self._is_shutting_down or not self.core.fts:
            return []
        try:
            return self.core.fts.get_all_tags()
        except (AttributeError, RuntimeError):  # Assuming FTS might raise these on closed DB
            return []

    def get_tags_for_note(self, note_id: str) -> list[str]:
        """Retrieves all tags associated with a specific note.

        Args:
            note_id: The ID of the note.

        Returns:
            A list of tag strings.
        """
        if self._is_shutting_down or not self.core.fts:
            return []
        try:
            return self.core.fts.get_tags_for_note(note_id)
        except (AttributeError, RuntimeError):
            return []
