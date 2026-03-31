"""Dashboard API — Action trigger routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..services.process_runner import active_process

router = APIRouter(prefix="/api/actions", tags=["actions"])


class RunRequest(BaseModel):
    command: str  # "extraction" | "gap_analysis" | "discovery"
    flags: dict = {}


@router.get("/status")
async def action_status():
    """Get the current pipeline process status."""
    return active_process.status()


@router.post("/run")
async def action_run(req: RunRequest):
    """Start a pipeline command. Only one process at a time."""
    result = await active_process.start(req.command, req.flags)
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@router.post("/cancel")
async def action_cancel():
    """Send SIGINT to the running process."""
    result = await active_process.cancel()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
