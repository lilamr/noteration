"""Shared state for the REST API.
"""

from pathlib import Path
from typing import Optional

from noteration.core.vault_core import VaultCore

_vault_path: Optional[Path] = None
_core: Optional[VaultCore] = None


def set_vault_path(path: Path):
    """Set the vault path."""
    global _vault_path
    _vault_path = path


def get_vault_path() -> Optional[Path]:
    """Get the vault path."""
    return _vault_path


def set_core(core: VaultCore):
    """Set the core instance."""
    global _core
    _core = core


def get_core() -> Optional[VaultCore]:
    """Get the core instance."""
    return _core
