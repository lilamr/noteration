"""REST API router for note management.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from noteration.api.deps import get_core, verify_api_key
from noteration.api.models import NoteCreate, NoteResponse, NoteUpdate
from noteration.core.vault_core import VaultCore
from noteration.utils.path_safety import is_safe_path

router = APIRouter(prefix="/notes", dependencies=[Depends(verify_api_key)])


@router.get("", response_model=List[NoteResponse])
async def list_notes(core: VaultCore = Depends(get_core)):
    """List all notes in the vault."""
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


@router.get("/{note_id}")
async def get_note(note_id: str, core: VaultCore = Depends(get_core)):
    """Retrieve a note by its ID."""
    note_path = (core.vault_path / "notes" / f"{note_id}.md").resolve()
    if not is_safe_path(core.vault_path / "notes", note_path) or not note_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")

    return {
        "note_id": note_id,
        "content": note_path.read_text(encoding="utf-8"),
        "backlinks": core.graph.backlinks(note_id),
    }


@router.post("")
async def create_note(note: NoteCreate, core: VaultCore = Depends(get_core)):
    """Create a new note."""
    note_path = (core.vault_path / "notes" / f"{note.note_id}.md").resolve()
    if not is_safe_path(core.vault_path / "notes", note_path):
        raise HTTPException(status_code=400, detail="Invalid note path")
    if note_path.exists():
        raise HTTPException(status_code=400, detail="Note already exists")

    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(note.content, encoding="utf-8")
    core.graph.update_note(note_path)
    return {"status": "ok", "note_id": note.note_id}


@router.put("/{note_id}")
async def update_note(note_id: str, note: NoteUpdate, core: VaultCore = Depends(get_core)):
    """Update an existing note."""
    note_path = (core.vault_path / "notes" / f"{note_id}.md").resolve()
    if not is_safe_path(core.vault_path / "notes", note_path) or not note_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")

    note_path.write_text(note.content, encoding="utf-8")
    core.graph.update_note(note_path)
    return {"status": "ok"}


@router.delete("/{note_id}")
async def delete_note(note_id: str, core: VaultCore = Depends(get_core)):
    """Delete a note by its ID."""
    note_path = (core.vault_path / "notes" / f"{note_id}.md").resolve()
    if not is_safe_path(core.vault_path / "notes", note_path) or not note_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")

    note_path.unlink()
    return {"status": "ok"}
