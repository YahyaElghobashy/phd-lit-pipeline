"""Dashboard API — Gaps routes."""
from fastapi import APIRouter, Query
from typing import Optional

from ..services.state_reader import get_gaps

router = APIRouter(prefix="/api", tags=["gaps"])


@router.get("/gaps")
async def gaps_list(
    coverage: Optional[str] = Query(None),
    gap_type: Optional[str] = Query(None),
    assignment: Optional[str] = Query(None),
):
    """List all gaps with optional filtering."""
    return get_gaps(coverage=coverage, gap_type=gap_type, assignment=assignment)
