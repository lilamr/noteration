"""REST API router for link graph functionality.
"""

from fastapi import APIRouter, Depends

from noteration.api.deps import get_core, verify_api_key
from noteration.api.models import GraphStats
from noteration.core.vault_core import VaultCore

router = APIRouter(prefix="/graph", dependencies=[Depends(verify_api_key)])


@router.get("/stats", response_model=GraphStats)
async def get_graph_stats(core: VaultCore = Depends(get_core)):
    """Retrieve graph statistics."""
    s = core.graph.stats()
    return GraphStats(nodes=s["nodes"], links=s["edges"], orphans=s["orphans"], hub=s["hub"])
