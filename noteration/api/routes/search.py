"""REST API router for search functionality.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from noteration.api.deps import get_core, verify_api_key
from noteration.api.models import SearchResult
from noteration.core.vault_core import VaultCore

router = APIRouter(prefix="/search", dependencies=[Depends(verify_api_key)])


@router.get("", response_model=List[SearchResult])
async def search(q: str, limit: int = 10, core: VaultCore = Depends(get_core)):
    """Search for notes using a query string."""
    if not core.fts:
        raise HTTPException(status_code=501, detail="FTS engine not available")
    results = core.fts.search_notes(q, limit=limit)
    return [
        SearchResult(
            type="note", id=r["note_id"], title=r["note_id"], snippet=r["snippet"], score=r["score"]
        )
        for r in results
    ]
