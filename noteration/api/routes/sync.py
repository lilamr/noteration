"""REST API router for synchronization functionality.
"""

from fastapi import APIRouter, Depends, HTTPException

from noteration.api.deps import get_core, verify_api_key
from noteration.api.models import SyncStatus
from noteration.core.vault_core import VaultCore

router = APIRouter(prefix="/sync", dependencies=[Depends(verify_api_key)])


@router.get("/status", response_model=SyncStatus)
async def get_sync_status(core: VaultCore = Depends(get_core)):
    """Retrieve git synchronization status."""
    if not core.git_repo:
        raise HTTPException(status_code=501, detail="Git not initialized")
    st = core.git_repo.status(session_hashes=core.session_hashes)
    return SyncStatus(
        branch=st.branch, remotes=st.remotes, is_dirty=st.is_dirty, ahead=st.ahead, behind=st.behind
    )
