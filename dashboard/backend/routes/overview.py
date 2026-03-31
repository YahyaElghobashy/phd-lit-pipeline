"""Dashboard API — Overview route."""
from fastapi import APIRouter

from ..services.state_reader import get_overview

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview")
async def overview():
    """Aggregate pipeline statistics for the dashboard."""
    return get_overview()
