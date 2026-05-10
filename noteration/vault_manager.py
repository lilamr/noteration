"""
noteration/vault_manager.py
Core engine orchestrator and background task manager for a single vault.
Manages synchronization between business logic, engines, and the main interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import shiboken6
from PySide6.QtCore import QObject, Signal, QThread

from noteration.config import NoterationConfig
from noteration.literature.papis_bridge import PapisBridge
from noteration.pdf.pdf_index import PdfIndex
from noteration.db.link_graph import LinkGraph
from noteration.sync.git_engine import GitRepo
from noteration.logger import setup_logging, get_logger

logger = get_logger(__name__)


class _StatusWorker(QObject):
    """Worker to check Git status in a background thread."""
    done = Signal(object)

    def __init__(self, repo: GitRepo, fetch: bool = False) -> None:
        super().__init__()
        self.repo = repo
        self.fetch = fetch

    def run(self) -> None:
        try:
            status = self.repo.status(fetch=self.fetch)
            self.done.emit(status)
        except Exception as e:
            logger.error(f"Background status check failed: {e}")
            self.done.emit(None)


class VaultManager(QObject):
    """
    Manager that handles the state and business operations of a Vault.
    MainWindow interacts with this Manager instead of managing engines directly.
    """
    
    # Signals for status communication to the UI
    status_message = Signal(str, int)  # msg, timeout
    git_status_updated = Signal(object) # Sends GitStatus object
    indexing_finished = Signal(int)
    graph_updated = Signal(int)

    def __init__(self, vault_path: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        
        # Ensure vault structure exists (handles empty/newly selected folders)
        self._init_directories()
        
        # Setup logging to a file within the vault
        setup_logging(vault_path)
        logger.info(f"Initializing VaultManager for {vault_path}")

        self.config = NoterationConfig(vault_path)
        
        # Engine Initialization
        self.papis = PapisBridge(self.config.papis_library)
        self.pdf_index = PdfIndex(vault_path)
        self.graph = LinkGraph(vault_path)
        self.git_repo: Optional[GitRepo] = None
        self.refresh_git_repo()

        self._is_syncing = False
        self._status_thread: Optional[QThread] = None
        self._status_worker: Optional[_StatusWorker] = None

    def _init_directories(self) -> None:
        """Ensure all required vault subdirectories exist."""
        for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
            (self.vault_path / sub).mkdir(parents=True, exist_ok=True)

    def refresh_git_repo(self) -> None:
        """Check for Git repository existence and update the engine instance."""
        if (self.vault_path / ".git").exists():
            if not self.git_repo or not self.git_repo.is_valid:
                self.git_repo = GitRepo(self.vault_path)
                # Automatically fix tracking of junk files (logs, etc.)
                self.git_repo.ensure_ignored()
        else:
            self.git_repo = None

    @property
    def is_syncing(self) -> bool:
        """Check if a synchronization operation is currently in progress."""
        return self._is_syncing

    @is_syncing.setter
    def is_syncing(self, value: bool) -> None:
        self._is_syncing = value

    # ------------------------------------------------------------------
    # Engine Accessors
    # ------------------------------------------------------------------

    def save_all(self) -> None:
        """Save the state of all persistent engines."""
        self.graph.save()
        self.config.save()

    # ------------------------------------------------------------------
    # Background Tasks
    # ------------------------------------------------------------------

    def scan_pdfs(self) -> None:
        """Scan for new PDF files in the literature vault."""
        count = self.pdf_index.scan_vault(self.config.papis_library)
        self.indexing_finished.emit(count)
        if count > 0:
            self.status_message.emit(f"PDF index: {count} new files indexed.", 3000)

    def build_graph(self, force: bool = False) -> None:
        """Build or load the backlink graph."""
        if not force and self.graph.load():
            count = 0 # Loaded from cache
        else:
            count = self.graph.build_from_vault()
            self.status_message.emit(f"Backlink graph: {count} links found.", 3000)
        self.graph_updated.emit(count)

    def update_note_in_graph(self, note_path: Path) -> None:
        """Update a single note in the graph incrementally."""
        self.graph.update_note(note_path)
        self.graph_updated.emit(1)

    # ------------------------------------------------------------------
    # Git & Sync Operations
    # ------------------------------------------------------------------

    def request_git_status(self, fetch: bool = False) -> None:
        """Trigger a Git status update for the UI in a background thread."""
        if not self.git_repo or not self.git_repo.is_valid:
            self.git_status_updated.emit(None)
            return
        
        # Avoid overlapping status checks
        if self._status_thread and shiboken6.isValid(self._status_thread) and self._status_thread.isRunning():
            return

        # Run status check in a background thread to avoid UI stutters
        self._status_thread = QThread()
        self._status_worker = _StatusWorker(self.git_repo, fetch=fetch)
        self._status_worker.moveToThread(self._status_thread)
        
        self._status_worker.done.connect(self._status_thread.quit)
        self._status_worker.done.connect(self.git_status_updated)
        
        # Cleanup
        self._status_worker.done.connect(self._status_worker.deleteLater)
        self._status_thread.started.connect(self._status_worker.run)
        self._status_thread.finished.connect(self._status_thread.deleteLater)
        self._status_thread.finished.connect(self._clear_status_thread)
        
        self._status_thread.start()

    def _clear_status_thread(self) -> None:
        """Clear references to the status thread and worker."""
        self._status_thread = None
        self._status_worker = None
