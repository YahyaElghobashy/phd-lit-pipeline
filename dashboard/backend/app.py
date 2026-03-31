"""
PhD Literature Extraction Pipeline — Dashboard
================================================
FastAPI application serving the dashboard API and frontend.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import overview, papers, gaps, runs, actions, discovery, admin
from .ws.terminal import terminal_ws

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = DASHBOARD_DIR / "frontend" / "dist"
PIPELINE_DIR = DASHBOARD_DIR.parent

# Try to read researcher name from research_config.yaml for dynamic description
_description = "PhD Literature Extraction Pipeline Dashboard"
try:
    import yaml
    _config_path = PIPELINE_DIR / "research_config.yaml"
    if _config_path.exists():
        with open(_config_path, "r") as _f:
            _cfg = yaml.safe_load(_f) or {}
        _researcher = _cfg.get("project", {}).get("researcher_name", "")
        if _researcher:
            _description = f"Dashboard for {_researcher}'s Literature Extraction Pipeline"
except Exception:
    pass

app = FastAPI(
    title="PhD Pipeline Dashboard",
    description=_description,
    version="1.0.0",
)

# CORS for development (Vite dev server on 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(overview.router)
app.include_router(papers.router)
app.include_router(gaps.router)
app.include_router(runs.router)
app.include_router(actions.router)
app.include_router(discovery.router)
app.include_router(admin.router)

# WebSocket for terminal streaming
app.websocket("/ws/terminal")(terminal_ws)


# Serve frontend static files in production
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": "PhD Pipeline Dashboard"}
