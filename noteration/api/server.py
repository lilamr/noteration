"""Noteration API server.

This module defines the FastAPI application, routes, and core initialization for the Noteration REST API.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from noteration.api.routes import graph, notes, search, sync
from noteration.api.state import set_core
from noteration.api.state import set_vault_path as set_state_vault_path
from noteration.core.vault_core import VaultCore

_vault_path: Path | None = None
_core: VaultCore | None = None


def set_vault_path(path: Path):
    """Set the vault path for the server instance."""
    global _vault_path
    _vault_path = path
    set_state_vault_path(path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the FastAPI application lifespan.

    Initializes VaultCore with the set vault path and shuts it down on exit.
    """
    global _core
    if not _vault_path:
        raise RuntimeError("Vault path not set before starting server")
    _core = VaultCore(_vault_path)
    set_core(_core)
    yield
    _core.shutdown()


app = FastAPI(title="Noteration API", lifespan=lifespan)

# Include routers
app.include_router(notes.router)
app.include_router(search.router)
app.include_router(graph.router)
app.include_router(sync.router)
