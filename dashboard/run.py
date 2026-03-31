#!/usr/bin/env python3
"""
PhD Pipeline Dashboard — Launcher
===================================
Single command to start the dashboard:
    python dashboard/run.py

Builds the frontend if needed, then starts the FastAPI server.
"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = DASHBOARD_DIR / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


def ensure_backend_deps():
    """Install backend dependencies if needed."""
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        print("Installing backend dependencies...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(DASHBOARD_DIR / "requirements.txt")],
            stdout=subprocess.DEVNULL,
        )


def build_frontend():
    """Build frontend if dist/ doesn't exist."""
    if FRONTEND_DIST.exists() and any(FRONTEND_DIST.iterdir()):
        return  # Already built

    if not FRONTEND_DIR.exists():
        print("Frontend directory not found. Skipping build.")
        print("The API is still available at /api/*")
        return

    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print("Installing frontend dependencies...")
        subprocess.check_call(["npm", "install"], cwd=str(FRONTEND_DIR))

    print("Building frontend...")
    subprocess.check_call(["npm", "run", "build"], cwd=str(FRONTEND_DIR))


def main():
    ensure_backend_deps()
    build_frontend()

    import uvicorn

    print(f"\n  PhD Pipeline Dashboard")
    print(f"  Dr. Yara Aboubakr")
    print(f"  {'─' * 30}")
    print(f"  API:  {URL}/api/health")
    if FRONTEND_DIST.exists():
        print(f"  App:  {URL}")
    print(f"  Docs: {URL}/docs")
    print()

    # Open browser after a short delay
    if FRONTEND_DIST.exists():
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(URL)).start()

    uvicorn.run(
        "dashboard.backend.app:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
