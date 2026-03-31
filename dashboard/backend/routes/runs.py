"""Dashboard API — Run history routes."""
from fastapi import APIRouter, HTTPException

from ..services.report_reader import list_runs, get_run

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs")
async def runs_list():
    """List all run reports, newest first."""
    return list_runs()


@router.get("/runs/{run_id}")
async def run_detail(run_id: str):
    """Get full run report by run_id."""
    data = get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return data
