"""Dependency injection for the REST API.
"""

from fastapi import Header, HTTPException

from noteration.api.state import get_core as get_core_state
from noteration.core.vault_core import VaultCore


def get_core() -> VaultCore:
    """Get the current VaultCore instance."""
    core = get_core_state()
    if not core:
        raise HTTPException(status_code=503, detail="VaultCore not initialized")
    return core


def verify_api_key(x_api_key: str = Header(default="")):
    """Verify the provided API key."""
    core = get_core()
    configured = core.config.get("api", "api_key", "")
    if not configured:
        raise HTTPException(
            status_code=503, detail="API is not configured. Please set an API key in settings."
        )
    if x_api_key != configured:
        raise HTTPException(status_code=401, detail="Invalid API key")
