"""Load and save configuration from config.toml within the vault."""

from __future__ import annotations

import copy
import sys
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

from noteration.logger import get_logger

logger = get_logger(__name__)

_DEFAULTS: dict[str, Any] = {
    "version": {
        "schema_version": 1,
    },
    "general": {
        "autosave": True,
        "autosave_interval": 30,
        "restore_last_session": True,
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

CURRENT_SCHEMA_VERSION = 1


class NoterationConfig:
    """Wrapper for the vault's config.toml file."""

    def __init__(self, vault_path: Path) -> None:
        """Initialize the config wrapper for the given vault.

        Args:
            vault_path: The base path of the vault.

        """
        self.vault_path = vault_path
        self._config_path = vault_path / ".noteration" / "config.toml"
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Load / save / migrate
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load and migrate configuration data."""
        with self._lock:
            self._data = copy.deepcopy(_DEFAULTS)
            if self._config_path.exists():
                try:
                    with open(self._config_path, "rb") as f:
                        user_data = tomllib.load(f)

                    user_data.pop("session", None)

                    # Perform migration if needed
                    if self._migrate(user_data):
                        import logging

                        logging.getLogger("noteration").info(
                            f"Migrated config to version {CURRENT_SCHEMA_VERSION}"
                        )
                        # Save the migrated config back to disk later or immediately
                        # We'll save it at the end of _load to ensure the file is up to date
                        needs_save = True
                    else:
                        needs_save = False

                    # deep merge
                    for section, values in user_data.items():
                        if section in self._data and isinstance(self._data[section], dict):
                            self._data[section] = {**self._data[section], **values}
                        else:
                            self._data[section] = values

                    if needs_save:
                        self.save()

                except Exception as e:
                    logger.error(f"Failed to load config from {self._config_path}: {e}")

    def _migrate(self, data: dict[str, Any]) -> bool:
        """Migrate config data to the current schema version.

        Args:
            data: The loaded configuration data.

        Returns:
            True if the data was modified, False otherwise.

        """
        version_sec = data.get("version", {})
        if isinstance(version_sec, int):
            v = version_sec
        else:
            v = version_sec.get("schema_version", 0)

        if v >= CURRENT_SCHEMA_VERSION:
            return False

        # Placeholder for future migrations:
        # if v < 1: ...

        # Finally, update version
        data["version"] = {"schema_version": CURRENT_SCHEMA_VERSION}
        return True

    def save(self) -> None:
        """Save the current configuration to disk."""
        if not _HAS_TOMLI_W:
            return
        with self._lock:
            self._data.pop("session", None)
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: save to temp then rename
            tmp_path = self._config_path.with_suffix(".tmp")
            try:
                with open(tmp_path, "wb") as f:
                    tomli_w.dump(self._data, f)
                tmp_path.replace(self._config_path)
            except Exception as e:
                logger.error(f"Failed to save config to {self._config_path}: {e}")
                if tmp_path.exists():
                    tmp_path.unlink()

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            section: The configuration section.
            key: The configuration key.
            default: The default value if not found.

        Returns:
            The configuration value.

        """
        with self._lock:
            return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        """Set a configuration value.

        Args:
            section: The configuration section.
            key: The configuration key.
            value: The value to set.

        """
        with self._lock:
            self._data.setdefault(section, {})[key] = value

    # Convenience properties
    @property
    def theme(self) -> str:
        """Return the UI theme."""
        return self.get("ui", "theme", "system")

    @property
    def papis_library(self) -> Path:
        """Return the Papis library path."""
        p = self.get("papis", "library_path", "")
        if p:
            # Resolve relative to vault_path if it's relative
            return (self.vault_path / p).expanduser()
        return self.vault_path / "literature"

    @papis_library.setter
    def papis_library(self, value: Path | str) -> None:
        """Store the Papis library path relative to vault_path.

        Args:
            value: The path to set.

        """
        p = Path(value)
        try:
            relative_path = p.relative_to(self.vault_path)
            self.set("papis", "library_path", str(relative_path))
        except ValueError:
            # If not relative, store absolute path (less ideal for sync)
            self.set("papis", "library_path", str(p))

    @property
    def font_family(self) -> str:
        """Return the editor font family."""
        return self.get("editor", "font_family", "Consolas")

    @property
    def font_size(self) -> int:
        """Return the editor font size."""
        return int(self.get("editor", "font_size", 12))
