"""Dashboard API — Papers routes."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from ..services.state_reader import get_papers
from ..services.extraction_reader import list_extractions, get_extraction

router = APIRouter(prefix="/api", tags=["papers"])


@router.get("/papers")
async def papers_list(
    search: Optional[str] = Query(None),
    theme: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    relevance: Optional[str] = Query(None),
):
    """List all papers with optional filtering."""
    return get_papers(search=search, theme=theme, status=status, relevance=relevance)


@router.get("/papers/{paper_id}")
async def paper_detail(paper_id: str):
    """Get full extraction data for a single paper."""
    data = get_extraction(paper_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Paper '{paper_id}' not found")
    return data


@router.get("/extractions")
async def extractions_list():
    """List all extraction summaries (lightweight)."""
    return list_extractions()
