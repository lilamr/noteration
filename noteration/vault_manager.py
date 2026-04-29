"""
noteration/vault_manager.py
Core engine orchestrator and background task manager for a single vault.
Manages synchronization between business logic, engines, and the main interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer, QThread

from noteration.config import NoterationConfig
from noteration.literature.papis_bridge import PapisBridge
from noteration.pdf.pdf_index import PdfIndex
from noteration.db.link_graph import LinkGraph
from noteration.sync.git_engine import GitRepo
from noteration.logger import setup_logging, get_logger

logger = get_logger(__name__)


class _SyncWorker(QObject):
    """Simple worker to run Git synchronization in a background thread."""
    done = Signal()

    def __init__(self, repo: GitRepo) -> None:
        super().__init__()
        self.repo = repo

    def run(self) -> None:
        try:
            # Run synchronization without log callbacks for background mode
            self.repo.sync(log_callback=lambda _: None)
        except Exception as e:
            logger.error(f"Background sync failed: {e}")
        self.done.emit()


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
        
        # Setup logging to a file within the vault
        setup_logging(vault_path)
        logger.info(f"Initializing VaultManager for {vault_path}")

        self.config = NoterationConfig(vault_path)
        
        # Engine Initialization
        self.papis = PapisBridge(self.config.papis_library)
        self.pdf_index = PdfIndex(vault_path)
        self.graph = LinkGraph(vault_path)
        self.git_repo = GitRepo(vault_path) if (vault_path / ".git").exists() else None

        # Timer for Automatic Synchronization
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self.perform_auto_sync)
        self.restart_auto_sync()

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

    def request_git_status(self) -> None:
        """Trigger a Git status update for the UI."""
        if not self.git_repo or not self.git_repo.is_valid:
            self.git_status_updated.emit(None)
            return
        
        # In a real implementation, this could be run in a separate thread
        status = self.git_repo.status()
        self.git_status_updated.emit(status)

    def restart_auto_sync(self) -> None:
        """Restart the automatic sync timer based on the latest configuration."""
        self._sync_timer.stop()
        if self.config.get("sync", "auto_sync", True):
            interval = int(self.config.get("sync", "sync_interval", 300))
            self._sync_timer.setInterval(interval * 1000)
            self._sync_timer.start()

    def perform_auto_sync(self) -> None:
        """Run Git synchronization in the background if necessary."""
        if not self.git_repo or not self.git_repo.is_valid:
            return
            
        status = self.git_repo.status()
        if not status.is_dirty or not status.remotes:
            return

        self.status_message.emit("Git: performing automatic synchronization...", 2000)
        
        # Run in a background thread
        self._bg_thread = QThread()
        self._bg_worker = _SyncWorker(self.git_repo)
        self._bg_worker.moveToThread(self._bg_thread)
        
        self._bg_worker.done.connect(self._bg_thread.quit)
        self._bg_worker.done.connect(self._on_sync_finished)
        self._bg_thread.started.connect(self._bg_worker.run)
        
        self._bg_thread.start()

    def _on_sync_finished(self) -> None:
        self.request_git_status()
        self.status_message.emit("Git: synchronization complete.", 3000)
