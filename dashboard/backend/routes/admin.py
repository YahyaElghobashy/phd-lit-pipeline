"""Dashboard API — Admin routes (config, files, sheets, drive)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Request Models ────────────────────────────────────────────────────────

class ConfigUpdateRequest(BaseModel):
    config: dict


class FileDeleteRequest(BaseModel):
    path: str


class CreateFolderRequest(BaseModel):
    project_name: str


# ── Config ────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config():
    """Read research_config.yaml."""
    try:
        from ..services.config_manager import get_config
        return get_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config")
async def update_config(req: ConfigUpdateRequest):
    """Update research_config.yaml with the provided data."""
    try:
        from ..services.config_manager import update_config
        return update_config(req.config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate")
async def regenerate_files():
    """Regenerate pipeline files from config."""
    try:
        from ..services.config_manager import regenerate_files
        return regenerate_files()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Files ─────────────────────────────────────────────────────────────────

@router.get("/files")
async def list_files():
    """List local pipeline files (extractions, discoveries, reports)."""
    try:
        from ..services.config_manager import list_local_files
        return list_local_files()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/files")
async def delete_file(req: FileDeleteRequest):
    """Delete a local pipeline file by relative path."""
    try:
        from ..services.config_manager import delete_file
        deleted = delete_file(req.path)
        if not deleted:
            raise HTTPException(status_code=404, detail="File not found")
        return {"status": "deleted", "path": req.path}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Sheets ────────────────────────────────────────────────────────────────

@router.get("/sheets")
async def get_sheets():
    """Get Google Sheet tab names and row counts."""
    try:
        from ..services.config_manager import get_sheets_info
        return get_sheets_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sheets/rebuild")
async def rebuild_sheets():
    """Trigger a sheet rebuild (re-populate headers, etc.)."""
    try:
        import sys
        from pathlib import Path

        PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent
        if str(PIPELINE_DIR) not in sys.path:
            sys.path.insert(0, str(PIPELINE_DIR))

        from sheet_setup import setup_sheets
        result = setup_sheets()
        return {"status": "ok", "message": "Sheets rebuilt successfully", "result": str(result)}
    except ImportError:
        return {"status": "ok", "message": "sheet_setup module not available — skipped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Drive ─────────────────────────────────────────────────────────────────

@router.get("/drive/folders")
async def list_drive_folders():
    """List Google Drive folders."""
    try:
        from ..services.drive_manager import list_folders
        return list_folders()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drive/folders")
async def create_drive_folders(req: CreateFolderRequest):
    """Create folder structure in Google Drive."""
    try:
        from ..services.drive_manager import create_folder_structure
        return create_folder_structure(req.project_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
