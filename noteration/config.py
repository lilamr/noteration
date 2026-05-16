"""
noteration/config.py
Load and save configuration from config.toml within the vault.
"""

from __future__ import annotations

import sys
import copy
import threading
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

try:
    import tomli_w  # pip install tomli-w
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False

_DEFAULTS: dict[str, Any] = {
    "general": {
        "autosave": True,
        "autosave_interval": 30,
    },
    "editor": {
        "tab_width": 2,
        "font_family": "Consolas",
        "font_size": 12,
        "show_line_numbers": True,
        "auto_indent": True,
    },
    "pdf": {
        "renderer": "qtpdf",
        "default_highlight_color": "#FFEB3B",
    },
    "papis": {
        "library_path": "",
    },
    "sync": {
        "remote": "origin",
        "branch": "",
    },
    "ui": {
        "theme": "system",
        "sidebar_visible": True,
    },
}


class NoterationConfig:
    """Wrapper for the vault's config.toml file."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._config_path = vault_path / ".noteration" / "config.toml"
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            self._data = copy.deepcopy(_DEFAULTS)
            if self._config_path.exists():
                try:
                    with open(self._config_path, "rb") as f:
                        user_data = tomllib.load(f)
                    # deep merge
                    for section, values in user_data.items():
                        if section in self._data and isinstance(self._data[section], dict):
                            self._data[section] = {**self._data[section], **values}
                        else:
                            self._data[section] = values
                except Exception as e:
                    import logging
                    logging.getLogger("noteration").error(f"Failed to load config: {e}")

    def save(self) -> None:
        if not _HAS_TOMLI_W:
            return
        with self._lock:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: save to temp then rename
            tmp_path = self._config_path.with_suffix(".tmp")
            try:
                with open(tmp_path, "wb") as f:
                    tomli_w.dump(self._data, f)
                tmp_path.replace(self._config_path)
            except Exception as e:
                import logging
                logging.getLogger("noteration").error(f"Failed to save config: {e}")
                if tmp_path.exists():
                    tmp_path.unlink()

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------

    def get(self, section: str, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        with self._lock:
            self._data.setdefault(section, {})[key] = value

    # Convenience properties
    @property
    def theme(self) -> str:
        return self.get("ui", "theme", "system")

    @property
    def papis_library(self) -> Path:
        p = self.get("papis", "library_path", "")
        if p:
            return Path(p).expanduser()
        return self.vault_path / "literature"

    @property
    def font_family(self) -> str:
        return self.get("editor", "font_family", "Consolas")

    @property
    def font_size(self) -> int:
        return int(self.get("editor", "font_size", 12))
