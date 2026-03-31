"""
Dashboard — Report Reader Service
Reads run report JSON files from the reports/ directory.
"""
from __future__ import annotations

import json
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent
REPORTS_DIR = PIPELINE_DIR / "reports"


def list_runs() -> list[dict]:
    """List all run reports sorted by date (newest first)."""
    if not REPORTS_DIR.exists():
        return []

    results = []
    for f in sorted(REPORTS_DIR.glob("run_*.json"), reverse=True):
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
            results.append({
                "run_id": data.get("run_id", f.stem),
                "filename": f.name,
                "started_at": data.get("started_at"),
                "finished_at": data.get("finished_at"),
                "duration_seconds": data.get("duration_seconds"),
                "total_queued": data.get("total_queued", 0),
                "completed": data.get("completed", 0),
                "failed": data.get("failed", 0),
                "skipped": data.get("skipped", 0),
                "args": data.get("args", {}),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return results


def get_run(run_id: str) -> dict | None:
    """Get full run report by run_id."""
    if not REPORTS_DIR.exists():
        return None

    # Try direct filename match
    for f in REPORTS_DIR.glob("run_*.json"):
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
            if data.get("run_id") == run_id or f.stem == f"run_{run_id}":
                return data
        except (json.JSONDecodeError, KeyError):
            continue

    return None
