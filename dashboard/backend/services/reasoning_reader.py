"""
Dashboard — Reasoning Reader Service
Reads local reasoning logs for full AI reasoning transparency in the dashboard.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Add pipeline dir so we can import pipeline modules
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))


def _get_log_path() -> Path:
    """Return path to reasoning log file."""
    from config import REASONING_LOG_FILE
    return REASONING_LOG_FILE


def _load_log() -> list[dict]:
    """Load the full reasoning log. Returns empty list on error."""
    log_file = _get_log_path()
    if not log_file.exists():
        return []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def get_reasoning_for_gap(gap_id: str) -> list[dict]:
    """
    Get all reasoning entries for a specific gap across all papers.
    Returns list of {paper_id, assessed_at, reasoning, pct_eliminated, confidence}.
    """
    data = _load_log()
    results = []
    for entry in data:
        for a in entry.get("assessments", []):
            if a.get("gap_id") == gap_id:
                results.append({
                    "paper_id": entry.get("paper_id", ""),
                    "assessed_at": entry.get("assessed_at", ""),
                    "reasoning": a.get("reasoning", ""),
                    "pct_eliminated": a.get("pct_eliminated", 0),
                    "aspect_addressed": a.get("aspect_addressed", ""),
                    "what_still_remains": a.get("what_still_remains", ""),
                    "confidence": a.get("confidence", {}),
                })
    return results


def get_reasoning_for_paper(paper_id: str) -> list[dict]:
    """
    Get all reasoning entries for a specific paper across all gaps.
    Returns list of assessment dicts.
    """
    data = _load_log()
    for entry in data:
        if entry.get("paper_id") == paper_id:
            return entry.get("assessments", [])
    return []


def get_reasoning_summary() -> dict:
    """Get summary statistics from the reasoning log."""
    data = _load_log()
    return {
        "total_papers": len(data),
        "total_assessments": sum(len(e.get("assessments", [])) for e in data),
        "paper_ids": [e.get("paper_id", "") for e in data],
    }
