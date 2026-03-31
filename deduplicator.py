"""
PhD Literature Discovery Pipeline — Deduplicator
===================================================
Checks candidate papers against BOTH sheets (original + auto) for duplicates.
Uses DOI exact match + fuzzy title matching (SequenceMatcher > 0.85).
"""
from __future__ import annotations

import time
from difflib import SequenceMatcher
from typing import Optional

import gspread

from populator import authenticate, retry_on_api_error, normalize_header
from discovery_config import ORIGINAL_SPREADSHEET_ID, AUTO_SPREADSHEET_ID

from rich.console import Console

console = Console()


class Deduplicator:
    """
    Deduplicates candidate papers against existing sheets.

    Checks:
    1. DOI exact match (normalized)
    2. Fuzzy title match (SequenceMatcher ratio > threshold)

    Against:
    - Original sheet's 1_IDENTIFICATION tab
    - Auto extraction sheet's 1_IDENTIFICATION tab (if it exists)
    """

    FUZZY_THRESHOLD = 0.85

    def __init__(self, auto_sheet_id: str = ""):
        self._client: Optional[gspread.Client] = None
        self._original_sheet_id = ORIGINAL_SPREADSHEET_ID
        self._auto_sheet_id = auto_sheet_id or AUTO_SPREADSHEET_ID
        # Cached existing paper data: list of (doi, title, paper_id)
        self._existing_papers: list[tuple[str, str, str]] = []
        self._loaded = False

    def _ensure_connected(self):
        if self._client is None:
            self._client = authenticate()

    @retry_on_api_error()
    def _load_sheet_papers(self, sheet_id: str) -> list[tuple[str, str, str]]:
        """
        Load (DOI, title, paper_id) tuples from a sheet's 1_IDENTIFICATION tab.
        Returns empty list if sheet/tab doesn't exist.
        """
        self._ensure_connected()
        try:
            spreadsheet = self._client.open_by_key(sheet_id)
            ws = spreadsheet.worksheet("1_IDENTIFICATION")
        except (gspread.SpreadsheetNotFound, gspread.WorksheetNotFound):
            return []

        all_values = ws.get_all_values()
        if not all_values:
            return []

        # Find headers (row 1)
        headers = [normalize_header(h) for h in all_values[0]]

        # Find column indices
        doi_col = None
        title_col = None
        pid_col = None
        for i, h in enumerate(headers):
            h_lower = h.lower().strip()
            if h_lower == "doi":
                doi_col = i
            elif h_lower == "full_citation_apa7":
                title_col = i  # We'll extract title from citation
            elif h_lower == "paper_id":
                pid_col = i

        papers = []
        for row in all_values[1:]:
            doi = row[doi_col].strip().lower() if doi_col is not None and doi_col < len(row) else ""
            # Strip doi.org prefix for matching
            for prefix in ["https://doi.org/", "http://doi.org/"]:
                if doi.startswith(prefix):
                    doi = doi[len(prefix):]

            title = ""
            if title_col is not None and title_col < len(row):
                title = row[title_col].strip().lower()

            pid = row[pid_col].strip() if pid_col is not None and pid_col < len(row) else ""
            if doi or title:
                papers.append((doi, title, pid))

        return papers

    def load_existing(self):
        """Load all existing papers from both sheets."""
        console.print("  [dim]Loading existing papers for deduplication...[/]")

        # Load from original sheet
        original = self._load_sheet_papers(self._original_sheet_id)
        console.print(f"  [dim]  Original sheet: {len(original)} papers[/]")

        # Load from auto sheet (if configured)
        auto = []
        if self._auto_sheet_id:
            auto = self._load_sheet_papers(self._auto_sheet_id)
            console.print(f"  [dim]  Auto sheet: {len(auto)} papers[/]")

        self._existing_papers = original + auto
        self._loaded = True
        console.print(f"  [dim]  Total existing: {len(self._existing_papers)} papers[/]")

    def _normalize_doi(self, doi: str) -> str:
        """Normalize DOI for comparison."""
        if not doi:
            return ""
        doi = doi.strip().lower()
        for prefix in ["https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"]:
            if doi.startswith(prefix):
                doi = doi[len(prefix):]
        return doi

    def is_duplicate(self, paper: dict) -> tuple[bool, str]:
        """
        Check if a paper is a duplicate.

        Args:
            paper: Normalized paper dict (from api_clients)

        Returns:
            (is_dup, reason) — e.g. (True, "DOI match: 10.1234/xyz")
        """
        if not self._loaded:
            self.load_existing()

        candidate_doi = self._normalize_doi(paper.get("DOI", ""))
        candidate_title = paper.get("title", "").strip().lower()

        # 1. DOI exact match
        if candidate_doi:
            for existing_doi, _, pid in self._existing_papers:
                if existing_doi and existing_doi == candidate_doi:
                    return True, f"DOI match: {candidate_doi} (existing: {pid})"

        # 2. Fuzzy title match
        if candidate_title and len(candidate_title) > 10:
            for _, existing_title, pid in self._existing_papers:
                if not existing_title or len(existing_title) < 10:
                    continue
                ratio = SequenceMatcher(None, candidate_title, existing_title).ratio()
                if ratio > self.FUZZY_THRESHOLD:
                    return True, f"Title match ({ratio:.2f}): '{candidate_title[:50]}...' ≈ existing {pid}"

        return False, ""

    def filter_new(self, papers: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Filter a list of papers, returning (new_papers, duplicates).

        Args:
            papers: List of normalized paper dicts

        Returns:
            (new_papers, duplicate_papers) — duplicates have 'dup_reason' key added
        """
        if not self._loaded:
            self.load_existing()

        new_papers = []
        duplicates = []

        for paper in papers:
            is_dup, reason = self.is_duplicate(paper)
            if is_dup:
                paper["dup_reason"] = reason
                duplicates.append(paper)
            else:
                new_papers.append(paper)

        return new_papers, duplicates
