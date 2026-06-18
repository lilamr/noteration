"""Pure Python core logic for a Noteration vault.

This module provides the central, Qt-independent core engine for managing
research vaults, including state management, engine initialization, and
business rules.
"""

import threading
from pathlib import Path
from typing import Callable, Optional

from noteration.config import NoterationConfig
from noteration.core.events import EventBus
from noteration.core.repository import NoteRepository
from noteration.db.link_graph import LinkGraph
from noteration.literature.csl_renderer import CSLRenderer
from noteration.literature.papis_bridge import PapisBridge
from noteration.logger import get_logger, setup_logging
from noteration.pdf.pdf_index import PdfIndex
from noteration.search.fts_engine import FTSEngine
from noteration.search.vault_search import VaultSearch
from noteration.sync.git_engine import GitRepo

logger = get_logger(__name__)


class VaultCore:
    """The central non-GUI engine for a single research vault.

    Manages state, engines, and business rules with lazy loading.
    """

    def __init__(
        self,
        vault_path: Path,
        storage_path: Optional[Path] = None,
        secret_key: Optional[str] = None,
        session_path: Optional[Path] = None,
    ) -> None:
        """Initialize the VaultCore with vault and storage paths, and optional keys."""
        self.vault_path = vault_path
        self.storage_path = storage_path or vault_path
        self.secret_key = secret_key
        self.session_path = session_path
        self._init_directories()

        setup_logging(self.vault_path, session_path=session_path)
        logger.info(
            f"Initializing VaultCore for {self.vault_path} (Storage: {self.storage_path}, Session: {session_path})"
        )

        # Core state
        self.notes = NoteRepository(self.vault_path / "notes")
        self.config = NoterationConfig(self.vault_path)
        self.events = EventBus()
        self._lock = threading.RLock()

        # Lazy engine instances
        self._pdf_index: Optional[PdfIndex] = None
        self._graph: Optional[LinkGraph] = None
        self._fts: Optional[FTSEngine] = None
        self._papis: Optional[PapisBridge] = None
        self._search_engine: Optional[VaultSearch] = None

        self.csl = CSLRenderer(self.config.get("literature", "citation_style", "apa"))

        # Git is initialized eagerly but check is cheap
        self.git_repo: Optional[GitRepo] = None
        self.refresh_git_repo(skip_ensure_ignored=False)

        self.session_hashes: dict[str, str] = {}
        logger.info("VaultCore base initialization complete (Engines will load lazily).")

    def encrypt_vault(self, log_callback: Optional[Callable[[str], None]] = None) -> None:
        """Proxy to VaultSession.encrypt_vault using current core state.
        """
        from noteration.core.session import VaultSession

        session = VaultSession(self.storage_path)
        session.temp_dir = self.vault_path
        session.secret_key = self.secret_key
        session.session_hashes = self.session_hashes
        session.encrypt_vault(log_callback=log_callback)
        # Update our hashes after encryption
        self.session_hashes = session.session_hashes

    def decrypt_vault(self, log_callback: Optional[Callable[[str], None]] = None) -> None:
        """Proxy to VaultSession.decrypt_vault using current core state.
        """
        from noteration.core.session import VaultSession

        session = VaultSession(self.storage_path)
        session.temp_dir = self.vault_path
        session.secret_key = self.secret_key
        session.decrypt_vault(log_callback=log_callback)
        # Update our hashes after decryption
        self.session_hashes = session.session_hashes

    @property
    def pdf_index(self) -> PdfIndex:
        """Return the lazy-initialized PDF index.
        """
        with self._lock:
            if self._pdf_index is None:
                logger.info("  → Initializing PDF Index (Lazy)...")
                try:
                    self._pdf_index = PdfIndex(self.vault_path)
                    self._pdf_index.load()
                except Exception as e:
                    logger.exception(f"Unexpected error initializing PDF Index: {e}")
                    self._pdf_index = PdfIndex(self.vault_path)
            return self._pdf_index

    @property
    def graph(self) -> LinkGraph:
        """Return the lazy-initialized link graph.
        """
        with self._lock:
            if self._graph is None:
                logger.info("  → Initializing Link Graph (Lazy)...")
                try:
                    self._graph = LinkGraph(self.vault_path, notes=self.notes)
                    self._graph.load()
                except Exception as e:
                    logger.exception(f"Unexpected error initializing Link Graph: {e}")
                    self._graph = LinkGraph(self.vault_path, notes=self.notes)
            return self._graph

    @property
    def fts(self) -> Optional[FTSEngine]:
        """Return the lazy-initialized FTS engine.
        """
        with self._lock:
            if self._fts is None:
                logger.info("  → Initializing FTS Engine (Lazy)...")
                try:
                    self._fts = FTSEngine(self.vault_path)
                except Exception as e:
                    logger.exception(f"Unexpected error initializing FTS Engine (Search will be disabled): {e}")
                    # FTS is optional, so we log and continue
                    self._fts = None
            return self._fts

    @property
    def papis(self) -> PapisBridge:
        """Return the lazy-initialized Papis bridge.
        """
        with self._lock:
            if self._papis is None:
                logger.info("  → Initializing Papis Bridge (Lazy)...")
                try:
                    lib_path = self.config.papis_library
                    if not lib_path or not lib_path.exists():
                        lib_path = self.vault_path / "literature"
                    self._papis = PapisBridge(lib_path)
                except Exception as e:
                    logger.exception(f"Unexpected error initializing Papis Bridge: {e}")
                    self._papis = PapisBridge(self.vault_path / "literature")
            return self._papis

    @property
    def search_engine(self) -> VaultSearch:
        """Return the lazy-initialized search engine.
        """
        with self._lock:
            if self._search_engine is None:
                logger.info("  → Initializing Search Engine (Lazy)...")
                # Search engine uses papis and fts properties (triggering their lazy load if needed)
                self._search_engine = VaultSearch(
                    self.vault_path, self.papis, fts_engine=self.fts, notes=self.notes
                )
            return self._search_engine

    def _init_directories(self) -> None:
        """Ensure all required vault subdirectories exist.
        """
        for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
            (self.vault_path / sub).mkdir(parents=True, exist_ok=True)

    def refresh_git_repo(self, skip_ensure_ignored: bool = False) -> None:
        """Refresh the Git repository instance if it exists.
        """
        if (self.storage_path / ".git").exists():
            if not self.git_repo or not self.git_repo.is_valid:
                work_tree = self.vault_path if self.vault_path != self.storage_path else None
                self.git_repo = GitRepo(self.storage_path, work_tree=work_tree)
                if not skip_ensure_ignored:
                    self.git_repo.ensure_ignored()
        else:
            self.git_repo = None

    def refresh_csl_renderer(self) -> None:
        """Reload the CSL renderer with the latest citation style configuration.
        """
        self.csl = CSLRenderer(self.config.get("literature", "citation_style", "apa"))
        logger.info(
            f"CSL Renderer refreshed with style: {self.config.get('literature', 'citation_style', 'apa')}"
        )

    def save_all(self) -> None:
        """Persist all in-memory engine data to disk.
        """
        logger.debug("Saving vault state...")
        if self._graph:
            self._graph.save()
        if self._pdf_index:
            self._pdf_index.save()
        self.config.save()

    def shutdown(self) -> None:
        """Gracefully shutdown core services and save final state.
        """
        logger.info("Shutting down VaultCore...")
        self.save_all()
        if self._fts:
            self._fts.close()

    def disable_encryption(self) -> bool:
        """Permanently disable encryption for this vault.
        """
        try:
            self.config.set("security", "encryption_enabled", False)
            self.config.set("security", "public_key", "")
            self.config.save()
            logger.info(f"Encryption disabled for vault {self.vault_path}")
            return True
        except Exception as e:
            logger.exception(f"Unexpected error disabling encryption: {e}")
            return False
