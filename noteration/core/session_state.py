"""Manager for persistent but non-Git-tracked window session state."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from noteration.logger import get_logger

logger = get_logger(__name__)


class SessionStateStore:
    """Store the last open tabs outside of Git-tracked config.toml."""

    def __init__(self, vault_path: Path) -> None:
        self._path = vault_path / ".noteration" / "session.json"
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        """Load the saved window session."""
        with self._lock:
            if not self._path.exists():
                return {"open_tabs": [], "active_pane": "main"}

            try:
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    return {"open_tabs": [], "active_pane": "main"}
                return data
            except Exception as e:
                logger.error(f"Failed to load session state from {self._path}: {e}")
                return {"open_tabs": [], "active_pane": "main"}

    def save(self, open_tabs: list[dict[str, Any]], active_pane: str) -> None:
        """Save the last open tabs and active pane."""
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {
                "open_tabs": open_tabs,
                "active_pane": active_pane,
            }
            try:
                tmp_path = self._path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                tmp_path.replace(self._path)
            except Exception as e:
                logger.error(f"Failed to save session state to {self._path}: {e}")
