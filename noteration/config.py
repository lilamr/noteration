"""
noteration/config.py
Memuat dan menulis konfigurasi dari config.toml di dalam vault.
"""

from __future__ import annotations

import sys
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
        "auto_sync": True,
        "sync_interval": 300,
        "remote": "origin",
        "branch": "main",
    },
    "ui": {
        "theme": "system",
        "sidebar_visible": True,
    },
}


class NoterationConfig:
    """Wrapper di atas config.toml vault."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._config_path = vault_path / ".noteration" / "config.toml"
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        self._data = dict(_DEFAULTS)
        if self._config_path.exists():
            with open(self._config_path, "rb") as f:
                user_data = tomllib.load(f)
            # deep merge
            for section, values in user_data.items():
                if section in self._data and isinstance(self._data[section], dict):
                    self._data[section] = {**self._data[section], **values}
                else:
                    self._data[section] = values

    def save(self) -> None:
        if not _HAS_TOMLI_W:
            return
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "wb") as f:
            tomli_w.dump(self._data, f)

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
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
