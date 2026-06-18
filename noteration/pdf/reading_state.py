"""noteration/pdf/reading_state.py
Manager for persistent but non-Git-tracked reading progress.
"""

import json
import threading
from pathlib import Path
from typing import TypedDict

from noteration.logger import get_logger

logger = get_logger(__name__)


class ReadingState(TypedDict):
    last_page: int
    reading_progress: float


class ReadingStateStore:
    """Manages reading state (last_page, reading_progress)
    stored outside of the Git-tracked vault/annotations directory.
    """

    def __init__(self, vault_path: Path) -> None:
        # Use a hidden directory in the vault: vault/.noteration/reading_state/
        self._state_dir = vault_path / ".noteration" / "reading_state"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _state_path(self, papis_key: str) -> Path:
        return self._state_dir / f"{papis_key}.json"

    def get_state(self, papis_key: str) -> ReadingState:
        """Load reading state for a document."""
        with self._lock:
            path = self._state_path(papis_key)
            if path.exists():
                try:
                    with open(path) as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load reading state for {papis_key}: {e}")
            return {"last_page": 0, "reading_progress": 0.0}

    def save_state(self, papis_key: str, last_page: int, reading_progress: float) -> None:
        """Save reading state for a document."""
        with self._lock:
            path = self._state_path(papis_key)
            state: ReadingState = {
                "last_page": last_page,
                "reading_progress": reading_progress,
            }
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save reading state for {papis_key}: {e}")
