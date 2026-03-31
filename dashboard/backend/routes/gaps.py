"""Dashboard API — Gaps routes."""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..services.state_reader import get_gaps
from ..services.matrix_reader import get_evidence, get_gaps_with_matrix_state
from ..services.reasoning_reader import get_reasoning_for_gap, get_reasoning_summary

router = APIRouter(prefix="/api", tags=["gaps"])


class TierOverrideRequest(BaseModel):
    tier: str
    justification: str = ""


@router.get("/gaps")
async def gaps_list(
    coverage: Optional[str] = Query(None),
    gap_type: Optional[str] = Query(None),
    assignment: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
):
    """List all gaps with optional filtering, enriched with matrix state."""
    gaps = get_gaps_with_matrix_state()

    # Apply filters
    if coverage:
        gaps = [g for g in gaps if g.get("coverage_level", "").lower() == coverage.lower()]
    if gap_type:
        gaps = [g for g in gaps if g.get("gap_type", "").lower() == gap_type.lower()]
    if assignment:
        gaps = [g for g in gaps if g.get("paper_assignment", "").lower() == assignment.lower()]
    if tier:
        gaps = [g for g in gaps if g.get("tier", "").lower() == tier.lower()]

    return gaps


@router.get("/gaps/{gap_id}/evidence")
async def gap_evidence(gap_id: str):
    """Full evidence chain for a gap, including reasoning from local log."""
    evidence = get_evidence(gap_id)
    reasoning = get_reasoning_for_gap(gap_id)
    return {
        "gap_id": gap_id,
        "evidence": evidence,
        "reasoning": reasoning,
    }


@router.get("/gaps/{gap_id}/history")
async def gap_history(gap_id: str):
    """Timeline of elimination for a gap (sorted chronologically)."""
    evidence = get_evidence(gap_id)
    return {
        "gap_id": gap_id,
        "history": sorted(evidence, key=lambda e: e.get("assessed_at", "")),
    }


@router.post("/gaps/{gap_id}/override")
async def gap_override(gap_id: str, req: TierOverrideRequest):
    """Manual tier override for a gap."""
    import sys
    from pathlib import Path
    pipeline_dir = Path(__file__).resolve().parent.parent.parent.parent
    if str(pipeline_dir) not in sys.path:
        sys.path.insert(0, str(pipeline_dir))

    from config import VALID_TIERS
    if req.tier not in VALID_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{req.tier}'. Must be one of: {', '.join(VALID_TIERS)}"
        )

    from gap_taxonomy import GapTaxonomy
    taxonomy = GapTaxonomy()
    success = taxonomy.override_tier(gap_id, req.tier, req.justification)
    if not success:
        raise HTTPException(status_code=404, detail=f"Gap {gap_id} not found")
    return {"success": True, "gap_id": gap_id, "tier": req.tier}


@router.get("/reasoning/summary")
async def reasoning_log_summary():
    """Summary of the reasoning log (total papers, assessments, etc.)."""
    return get_reasoning_summary()
