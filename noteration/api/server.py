"""Noteration API server.

This module defines the FastAPI application, routes, and core initialization for the Noteration REST API.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, Header, HTTPException

from noteration.api.models import (
    GraphStats,
    NoteCreate,
    NoteResponse,
    NoteUpdate,
    SearchResult,
    SyncStatus,
)
from noteration.core.vault_core import VaultCore
from noteration.utils.path_safety import is_safe_path

_vault_path: Path | None = None
_core: VaultCore | None = None


def set_vault_path(path: Path):
    """Set the vault path for the server instance.

    Args:
        path: The pathlib.Path to the research vault.
    """
    global _vault_path
    _vault_path = path


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the FastAPI application lifespan.

    Initializes the VaultCore instance before startup and handles shutdown cleanup.
    """
    global _core
    if not _vault_path:
        raise RuntimeError("Vault path not set before starting server")
    _core = VaultCore(_vault_path)
    yield
    _core.shutdown()


app = FastAPI(title="Noteration API", lifespan=lifespan)


def get_core() -> VaultCore:
    """Get the current VaultCore instance.

    Returns:
        The initialized VaultCore instance.

    Raises:
        HTTPException: If VaultCore is not initialized.
    """
    if not _core:
        raise HTTPException(status_code=503, detail="VaultCore not initialized")
    return _core


def verify_api_key(x_api_key: str = Header(default="")):
    """Verify the provided API key.

    Args:
        x_api_key: The API key from the request header.

    Raises:
        HTTPException: If API is not configured or key is invalid.
    """
    core = get_core()
    configured = core.config.get("api", "api_key", "")
    if not configured:
        raise HTTPException(
            status_code=503, detail="API is not configured. Please set an API key in settings."
        )
    if x_api_key != configured:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/notes", response_model=List[NoteResponse], dependencies=[Depends(verify_api_key)])
async def list_notes(core: VaultCore = Depends(get_core)):
    """List all notes in the vault.

    Returns:
        A list of NoteResponse objects containing metadata for all notes.
    """
    results = []
    for p in core.notes.list_notes():
        rel_path = p.relative_to(core.notes.notes_dir)
        note_id = str(rel_path.with_suffix(""))
        results.append(
            NoteResponse(
                note_id=note_id,
                title=p.stem,
                path=str(rel_path),
                word_count=0,
                modified_at=p.stat().st_mtime,
                tags=core.fts.get_tags_for_note(note_id) if core.fts else [],
            )
        )
    return results


@app.get("/notes/{note_id}", dependencies=[Depends(verify_api_key)])
async def get_note(note_id: str, core: VaultCore = Depends(get_core)):
    """Retrieve a note by its ID.

    Args:
        note_id: The ID of the note.

    Returns:
        A dictionary containing note details.

    Raises:
        HTTPException: If note is not found.
    """
    note_path = (core.vault_path / "notes" / f"{note_id}.md").resolve()
    if not is_safe_path(core.vault_path / "notes", note_path) or not note_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")

    return {
        "note_id": note_id,
        "content": note_path.read_text(encoding="utf-8"),
        "backlinks": core.graph.backlinks(note_id),
    }


@app.post("/notes", dependencies=[Depends(verify_api_key)])
async def create_note(note: NoteCreate, core: VaultCore = Depends(get_core)):
    """Create a new note.

    Args:
        note: The NoteCreate object containing ID and content.

    Returns:
        A status dictionary.

    Raises:
        HTTPException: If path is invalid or note already exists.
    """
    note_path = (core.vault_path / "notes" / f"{note.note_id}.md").resolve()
    if not is_safe_path(core.vault_path / "notes", note_path):
        raise HTTPException(status_code=400, detail="Invalid note path")
    if note_path.exists():
        raise HTTPException(status_code=400, detail="Note already exists")

    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(note.content, encoding="utf-8")
    core.graph.update_note(note_path)
    return {"status": "ok", "note_id": note.note_id}


@app.put("/notes/{note_id}", dependencies=[Depends(verify_api_key)])
async def update_note(note_id: str, note: NoteUpdate, core: VaultCore = Depends(get_core)):
    """Update an existing note.

    Args:
        note_id: The ID of the note to update.
        note: The NoteUpdate object containing content.

    Returns:
        A status dictionary.

    Raises:
        HTTPException: If note is not found or path is invalid.
    """
    note_path = (core.vault_path / "notes" / f"{note_id}.md").resolve()
    if not is_safe_path(core.vault_path / "notes", note_path) or not note_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")

    note_path.write_text(note.content, encoding="utf-8")
    core.graph.update_note(note_path)
    return {"status": "ok"}


@app.delete("/notes/{note_id}", dependencies=[Depends(verify_api_key)])
async def delete_note(note_id: str, core: VaultCore = Depends(get_core)):
    """Delete a note by its ID.

    Args:
        note_id: The ID of the note to delete.

    Returns:
        A status dictionary.

    Raises:
        HTTPException: If note is not found or path is invalid.
    """
    note_path = (core.vault_path / "notes" / f"{note_id}.md").resolve()
    if not is_safe_path(core.vault_path / "notes", note_path) or not note_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")

    note_path.unlink()
    # Optional: trigger graph update or FTS removal
    return {"status": "ok"}


@app.get("/search", response_model=List[SearchResult], dependencies=[Depends(verify_api_key)])
async def search(q: str, limit: int = 10, core: VaultCore = Depends(get_core)):
    """Search for notes using a query string.

    Args:
        q: The search query string.
        limit: The maximum number of results to return.

    Returns:
        A list of search results.

    Raises:
        HTTPException: If the FTS engine is not available.
    """
    if not core.fts:
        raise HTTPException(status_code=501, detail="FTS engine not available")
    results = core.fts.search_notes(q, limit=limit)
    return [
        SearchResult(
            type="note", id=r["note_id"], title=r["note_id"], snippet=r["snippet"], score=r["score"]
        )
        for r in results
    ]


@app.get("/graph/stats", response_model=GraphStats, dependencies=[Depends(verify_api_key)])
async def get_graph_stats(core: VaultCore = Depends(get_core)):
    """Retrieve graph statistics.

    Returns:
        GraphStats object containing node, link, and orphan counts.
    """
    s = core.graph.stats()
    return GraphStats(nodes=s["nodes"], links=s["edges"], orphans=s["orphans"], hub=s["hub"])


@app.get("/sync/status", response_model=SyncStatus, dependencies=[Depends(verify_api_key)])
async def get_sync_status(core: VaultCore = Depends(get_core)):
    """Retrieve git synchronization status.

    Returns:
        SyncStatus object containing git status details.

    Raises:
        HTTPException: If git is not initialized.
    """
    if not core.git_repo:
        raise HTTPException(status_code=501, detail="Git not initialized")
    st = core.git_repo.status(session_hashes=core.session_hashes)
    return SyncStatus(
        branch=st.branch, remotes=st.remotes, is_dirty=st.is_dirty, ahead=st.ahead, behind=st.behind
    )
