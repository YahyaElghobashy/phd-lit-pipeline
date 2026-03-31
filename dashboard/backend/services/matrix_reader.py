"""
Dashboard — Matrix Reader Service
Reads GAP_MATRIX and GAP_EVIDENCE data from the Google Sheet or cached state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Add pipeline dir so we can import pipeline modules
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))


def _read_matrix_from_sheet() -> dict:
    """Read GAP_MATRIX tab from the original Google Sheet via gspread."""
    try:
        from populator import authenticate, retry_on_api_error
        from config import SPREADSHEET_ID, GAP_MATRIX_TAB

        client = authenticate()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        ws = spreadsheet.worksheet(GAP_MATRIX_TAB)
        all_data = ws.get_all_values()

        if not all_data or len(all_data) < 2:
            return {"gaps": [], "paper_ids": []}

        headers = all_data[0]
        # Columns: Gap_ID | Pct_Remaining | Gap_State | Paper1 | Paper2 | ...
        paper_ids = headers[3:]  # Everything after the first 3 fixed columns

        gaps = []
        for row in all_data[1:]:
            if not row or not row[0]:
                continue
            gap_id = row[0]
            pct_remaining = _parse_pct(row[1] if len(row) > 1 else "100")
            gap_state = row[2] if len(row) > 2 else "Open"

            papers = {}
            for i, pid in enumerate(paper_ids):
                col_idx = i + 3
                if col_idx < len(row) and row[col_idx]:
                    pct = _parse_pct(row[col_idx])
                    if pct > 0:
                        papers[pid] = pct

            gaps.append({
                "gap_id": gap_id,
                "pct_remaining": pct_remaining,
                "gap_state": gap_state,
                "papers": papers,
            })

        return {"gaps": gaps, "paper_ids": paper_ids}

    except Exception:
        return {"gaps": [], "paper_ids": []}


def _read_evidence_from_sheet(gap_id: Optional[str] = None) -> list[dict]:
    """Read GAP_EVIDENCE tab, optionally filtered by gap_id."""
    try:
        from populator import authenticate
        from config import SPREADSHEET_ID, GAP_EVIDENCE_TAB

        client = authenticate()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        ws = spreadsheet.worksheet(GAP_EVIDENCE_TAB)
        all_data = ws.get_all_values()

        if not all_data or len(all_data) < 2:
            return []

        headers = all_data[0]
        results = []
        for row in all_data[1:]:
            if not row or not row[0]:
                continue
            entry = dict(zip(headers, row))

            if gap_id and entry.get("Gap_ID") != gap_id:
                continue

            results.append({
                "gap_id": entry.get("Gap_ID", ""),
                "paper_id": entry.get("Paper_ID", ""),
                "pct_eliminated": _parse_pct(entry.get("Pct_Eliminated", "0")),
                "pct_remaining_before": _parse_pct(entry.get("Pct_Remaining_Before", "100")),
                "pct_remaining_after": _parse_pct(entry.get("Pct_Remaining_After", "100")),
                "aspect_addressed": entry.get("Aspect_Addressed", ""),
                "what_still_remains": entry.get("What_Still_Remains", ""),
                "assessed_by": entry.get("Assessed_By", ""),
                "assessed_at": entry.get("Assessed_At", ""),
                "source": entry.get("Source", ""),
                # Module 6: Confidence scoring
                "confidence_methodological": _parse_pct(entry.get("Confidence_Methodological", "0")),
                "confidence_sample": _parse_pct(entry.get("Confidence_Sample", "0")),
                "confidence_variables": _parse_pct(entry.get("Confidence_Variables", "0")),
                "confidence_directness": _parse_pct(entry.get("Confidence_Directness", "0")),
                "confidence_overall": _parse_pct(entry.get("Confidence_Overall", "0")),
                "confidence_tier": entry.get("Confidence_Tier", ""),
            })

        return results

    except Exception:
        return []


def _parse_pct(value: str) -> float:
    """Parse a percentage string like '65%' or '65' to a float."""
    if not value:
        return 0.0
    try:
        return float(str(value).replace("%", "").strip())
    except (ValueError, TypeError):
        return 0.0


def get_matrix_data() -> dict:
    """
    Read GAP_MATRIX data for dashboard visualization.
    Returns: {gaps: [...], summary: {...}, paper_ids: [...]}
    """
    data = _read_matrix_from_sheet()
    gaps = data.get("gaps", [])

    # Compute summary
    # Check "partially" BEFORE "resolved" since "Partially Resolved" contains both
    summary = {"open": 0, "investigating": 0, "partial": 0, "resolved": 0}
    for gap in gaps:
        state = gap.get("gap_state", "Open").lower()
        if "partially" in state:
            summary["partial"] += 1
        elif "resolved" in state:
            summary["resolved"] += 1
        elif "investigation" in state:
            summary["investigating"] += 1
        else:
            summary["open"] += 1

    return {
        "gaps": gaps,
        "summary": summary,
        "paper_ids": data.get("paper_ids", []),
    }


def get_evidence(gap_id: str) -> list[dict]:
    """Read GAP_EVIDENCE entries for a specific gap."""
    return _read_evidence_from_sheet(gap_id=gap_id)


def get_matrix_summary() -> dict:
    """Get just the summary counts (lightweight)."""
    data = get_matrix_data()
    return data["summary"]


def get_gaps_with_matrix_state() -> list[dict]:
    """
    Merge gap_tracker data from pipeline_state.json with GAP_MATRIX state.
    Returns gaps enriched with pct_remaining and gap_state.
    """
    from .state_reader import get_gaps as get_base_gaps

    base_gaps = get_base_gaps()
    matrix_data = _read_matrix_from_sheet()

    # Build lookup from matrix
    matrix_lookup = {}
    for g in matrix_data.get("gaps", []):
        matrix_lookup[g["gap_id"]] = {
            "pct_remaining": g["pct_remaining"],
            "gap_state": g["gap_state"],
        }

    # Merge
    enriched = []
    for gap in base_gaps:
        gid = gap.get("gap_id", "")
        matrix_info = matrix_lookup.get(gid, {})
        enriched.append({
            "gap_id": gid,
            "gap_statement": gap.get("gap_statement", ""),
            "gap_type": gap.get("gap_type", ""),
            "severity": gap.get("severity", ""),
            "pct_remaining": matrix_info.get("pct_remaining", 100),
            "gap_state": matrix_info.get("gap_state", "Open"),
            "coverage_level": gap.get("coverage_level", ""),
            "paper_assignment": gap.get("paper_assignment", ""),
        })

    return enriched
