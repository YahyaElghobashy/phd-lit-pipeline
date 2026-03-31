"""
Dashboard — Extraction Reader Service
Reads extraction JSON files from the extractions/ directory.
"""
from __future__ import annotations

import json
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent
EXTRACTIONS_DIR = PIPELINE_DIR / "extractions"

# 12-section keys in display order
SECTIONS = [
    "1_IDENTIFICATION", "2_RESEARCH_DESIGN", "3_VARIABLES",
    "4_METHODOLOGY", "5_SAMPLE", "6_THEORY", "7_FINDINGS",
    "8_GAPS_LIMITATIONS", "9_RELEVANCE", "10_CLASSIFICATION",
    "11_CONNECTIONS", "12_BOARD_CHARS",
]

# Human-readable section names
SECTION_LABELS = {
    "1_IDENTIFICATION": "Identification",
    "2_RESEARCH_DESIGN": "Research Design",
    "3_VARIABLES": "Variables",
    "4_METHODOLOGY": "Methodology",
    "5_SAMPLE": "Sample",
    "6_THEORY": "Theory",
    "7_FINDINGS": "Findings",
    "8_GAPS_LIMITATIONS": "Gaps & Limitations",
    "9_RELEVANCE": "Relevance",
    "10_CLASSIFICATION": "Classification",
    "11_CONNECTIONS": "Connections",
    "12_BOARD_CHARS": "Board Characteristics",
}


def list_extractions() -> list[dict]:
    """List all extraction summaries (lightweight, no full sections)."""
    if not EXTRACTIONS_DIR.exists():
        return []

    results = []
    for f in sorted(EXTRACTIONS_DIR.glob("*.json")):
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
            pid = data.get("paper_id", f.stem)
            ident = data.get("1_IDENTIFICATION", {})
            rel = data.get("9_RELEVANCE", {})
            cls = data.get("10_CLASSIFICATION", {})
            design = data.get("2_RESEARCH_DESIGN", {})

            results.append({
                "paper_id": pid,
                "filename": f.name,
                "title": ident.get("Full_Citation_APA7", "")[:120],
                "authors": ident.get("Authors", ""),
                "year": ident.get("Year"),
                "journal": ident.get("Journal", ""),
                "journal_tier": ident.get("Journal_Tier", ""),
                "paper_type": ident.get("Paper_Type", ""),
                "doi": ident.get("DOI", ""),
                "theme": cls.get("Primary_Theme", ""),
                "paper_assignment": cls.get("Paper_Assignment", ""),
                "relevance_tier": rel.get("Relevance_Tier", ""),
                "weighted_score": rel.get("Weighted_Score", ""),
                "one_sentence_summary": design.get("One_Sentence_Summary", ""),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return results


def get_extraction(paper_id: str) -> dict | None:
    """Get full extraction data for a single paper."""
    if not EXTRACTIONS_DIR.exists():
        return None

    target = EXTRACTIONS_DIR / f"{paper_id}.json"
    if target.exists():
        with open(target, "r") as f:
            data = json.load(f)
        # Add section metadata
        data["_sections"] = SECTIONS
        data["_section_labels"] = SECTION_LABELS
        return data

    # Fallback: search by paper_id field inside files
    for f in EXTRACTIONS_DIR.glob("*.json"):
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
            if data.get("paper_id") == paper_id:
                data["_sections"] = SECTIONS
                data["_section_labels"] = SECTION_LABELS
                return data
        except (json.JSONDecodeError, KeyError):
            continue

    return None
