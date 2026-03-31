"""
Dashboard — State Reader Service
Reads pipeline_state.json (read-only) to provide overview and paper status data.
"""
from __future__ import annotations

import json
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent
STATE_FILE = PIPELINE_DIR / "pipeline_state.json"


def _load_state() -> dict:
    """Load pipeline state from disk. Returns empty dict on error."""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_overview() -> dict:
    """Aggregate pipeline statistics for the dashboard overview."""
    state = _load_state()
    papers = state.get("papers", {})

    total = len(papers)
    by_status: dict[str, int] = {}
    by_theme: dict[str, int] = {}
    by_relevance: dict[str, int] = {}
    total_duration = 0
    durations = []

    for _path, info in papers.items():
        status = info.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        dur = info.get("duration_seconds")
        if dur and isinstance(dur, (int, float)):
            total_duration += dur
            durations.append(dur)

    # Read extraction files to get theme and relevance distributions
    extractions_dir = PIPELINE_DIR / "extractions"
    if extractions_dir.exists():
        for ext_file in extractions_dir.glob("*.json"):
            try:
                with open(ext_file, "r") as f:
                    ext = json.load(f)
                # Theme from 10_CLASSIFICATION
                cls = ext.get("10_CLASSIFICATION", {})
                theme = cls.get("Primary_Theme", "Unknown")
                if theme:
                    by_theme[theme] = by_theme.get(theme, 0) + 1
                # Relevance from 9_RELEVANCE
                rel = ext.get("9_RELEVANCE", {})
                score = rel.get("Weighted_Score")
                if isinstance(score, (int, float)) and score > 0:
                    if score >= 4.5:
                        tier = "Essential"
                    elif score >= 3.5:
                        tier = "Highly Relevant"
                    elif score >= 2.5:
                        tier = "Moderate"
                    else:
                        tier = "Low"
                    by_relevance[tier] = by_relevance.get(tier, 0) + 1
                else:
                    # Try Relevance_Tier field directly
                    tier_str = rel.get("Relevance_Tier", "")
                    if tier_str:
                        by_relevance[tier_str] = by_relevance.get(tier_str, 0) + 1
            except (json.JSONDecodeError, KeyError):
                continue

    # Gap stats from pipeline state
    gap_tracker = state.get("gap_tracker", [])
    gaps_by_coverage: dict[str, int] = {}
    for gap in gap_tracker:
        cov = gap.get("coverage_level", "NOT ADDRESSED")
        gaps_by_coverage[cov] = gaps_by_coverage.get(cov, 0) + 1

    completed = by_status.get("complete", 0)
    failed = sum(v for k, v in by_status.items() if k.startswith("failed"))

    return {
        "total_papers": completed,  # Only count successfully extracted papers
        "completed": completed,
        "failed": failed,
        "in_progress": total - completed - failed,
        "total_gaps": len(gap_tracker),
        "by_status": by_status,
        "by_theme": by_theme,
        "by_relevance": by_relevance,
        "gaps_by_coverage": gaps_by_coverage,
        "avg_duration_seconds": round(total_duration / len(durations), 1) if durations else 0,
        "last_run": state.get("last_run"),
    }


def get_papers(
    search: str | None = None,
    theme: str | None = None,
    status: str | None = None,
    relevance: str | None = None,
) -> list[dict]:
    """List all papers with optional filtering."""
    state = _load_state()
    papers_raw = state.get("papers", {})

    # Build a lookup from paper_id -> extraction metadata
    ext_lookup: dict[str, dict] = {}
    extractions_dir = PIPELINE_DIR / "extractions"
    if extractions_dir.exists():
        for ext_file in extractions_dir.glob("*.json"):
            try:
                with open(ext_file, "r") as f:
                    ext = json.load(f)
                pid = ext.get("paper_id", "")
                if pid:
                    ident = ext.get("1_IDENTIFICATION", {})
                    cls = ext.get("10_CLASSIFICATION", {})
                    rel = ext.get("9_RELEVANCE", {})
                    ext_lookup[pid] = {
                        "year": ident.get("Year"),
                        "journal": ident.get("Journal", ""),
                        "doi": ident.get("DOI", ""),
                        "citation": ident.get("Full_Citation_APA7", ""),
                        "theme": cls.get("Primary_Theme", ""),
                        "paper_assignment": cls.get("Paper_Assignment", ""),
                        "relevance_tier": rel.get("Relevance_Tier", ""),
                        "weighted_score": rel.get("Weighted_Score", ""),
                    }
            except (json.JSONDecodeError, KeyError):
                continue

    results = []
    for _path, info in papers_raw.items():
        pid = info.get("paper_id") or ""
        paper_status = info.get("status", "unknown")

        # Skip papers with no extraction data (failed/stuck) unless status filter asks for them
        is_failed = paper_status.startswith("failed") or (paper_status == "extracting" and not pid)
        if is_failed and status is None:
            continue  # Hide failed papers by default
        if is_failed and status and status != paper_status:
            continue

        ext_meta = ext_lookup.get(pid, {})

        paper = {
            "paper_id": pid,
            "status": paper_status,
            "original_filename": info.get("original_filename", ""),
            "started_at": info.get("started_at"),
            "completed_at": info.get("completed_at"),
            "duration_seconds": info.get("duration_seconds"),
            "error": info.get("error"),
            "retry_count": info.get("retry_count", 0),
            "year": ext_meta.get("year"),
            "journal": ext_meta.get("journal", ""),
            "doi": ext_meta.get("doi", ""),
            "theme": ext_meta.get("theme", ""),
            "paper_assignment": ext_meta.get("paper_assignment", ""),
            "relevance_tier": ext_meta.get("relevance_tier", ""),
            "weighted_score": ext_meta.get("weighted_score", ""),
        }

        # Apply filters
        if search:
            q = search.lower()
            if not (
                q in pid.lower()
                or q in paper.get("original_filename", "").lower()
                or q in paper.get("journal", "").lower()
                or q in paper.get("theme", "").lower()
            ):
                continue
        if theme and paper.get("theme", "").lower() != theme.lower():
            continue
        if status and paper_status != status:
            continue
        if relevance and paper.get("relevance_tier", "").lower() != relevance.lower():
            continue

        results.append(paper)

    # Sort: completed first, then by paper_id
    results.sort(key=lambda p: (0 if p["status"] == "complete" else 1, p["paper_id"] or "zzz"))
    return results


def get_gaps(
    coverage: str | None = None,
    gap_type: str | None = None,
    assignment: str | None = None,
) -> list[dict]:
    """List all gaps from pipeline state with optional filtering."""
    state = _load_state()
    gap_tracker = state.get("gap_tracker", [])

    results = []
    for gap in gap_tracker:
        if coverage and gap.get("coverage_level", "").lower() != coverage.lower():
            continue
        if gap_type and gap.get("gap_type", "").lower() != gap_type.lower():
            continue
        if assignment and gap.get("paper_assignment", "").lower() != assignment.lower():
            continue
        results.append(gap)

    return results
