"""
PhD Literature Extraction Pipeline — Google Sheets Populator
=============================================================
Writes extraction data to the Google Sheet, one tab per section.
Reads actual sheet headers at runtime to ensure correct column alignment.

Optimized for minimal API calls:
- Next-row positions are cached and incremented locally after each write
- GAP_TRACKER updates are batched into a single read + single write
- New gap rows are batched into one multi-row update
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from functools import wraps

import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config import (
    SPREADSHEET_ID,
    SCOPES,
    TOKEN_FILE,
    CLIENT_SECRET_FILE,
    SHEETS_WRITE_DELAY,
    SHEETS_MAX_RETRIES,
    SHEETS_RETRY_BASE_DELAY,
)
from schemas import EXTRACTION_SECTIONS


# ─── FIELD NAME NORMALIZATION ────────────────────────────────
# Sheet headers may have suffixes like "(25%)" or "(1-5)".
# We strip these to match our JSON field names.

def _col_letter(col_num: int) -> str:
    """Convert 1-based column number to letter(s). 1=A, 26=Z, 27=AA."""
    result = ""
    while col_num > 0:
        col_num, remainder = divmod(col_num - 1, 26)
        result = chr(65 + remainder) + result
    return result


def normalize_header(header: str) -> str:
    """
    Normalize a sheet header to match JSON field names.
    e.g., "Topic_Alignment (25%)" -> "Topic_Alignment"
          "Severity (1-5)" -> "Severity"
          "" -> ""
    """
    h = header.strip()
    # Remove trailing parenthetical like " (25%)" or " (1-5)"
    if "(" in h:
        h = h[:h.rfind("(")].strip()
    return h


# ─── RETRY DECORATOR ────────────────────────────────────────

def retry_on_api_error(max_retries=SHEETS_MAX_RETRIES, base_delay=SHEETS_RETRY_BASE_DELAY):
    """Retry Google Sheets API calls with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    retryable = any(x in error_str for x in [
                        "429", "rate limit", "quota",
                        "500", "503", "service unavailable",
                        "timeout", "timed out",
                        "transport", "connection",
                        "broken pipe", "reset by peer",
                    ])
                    if not retryable:
                        raise
                    delay = base_delay * (2 ** attempt)
                    print(f"     ⚠️  {func.__name__} retry {attempt + 1}/{max_retries} in {delay:.0f}s: {e}")
                    time.sleep(delay)
            raise last_error
        return wrapper
    return decorator


# ─── AUTHENTICATION ──────────────────────────────────────────

def authenticate() -> gspread.Client:
    """OAuth2 auth with auto-refresh."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("     🔄 Token expired, refreshing...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"     ⚠️  Token refresh failed ({e}), re-authenticating...")
                creds = None

        if not creds:
            from google_auth_oauthlib.flow import InstalledAppFlow
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"OAuth client secret not found at {CLIENT_SECRET_FILE}. "
                    "Copy client_secret.json to the pipeline directory."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return gspread.authorize(creds)


# ─── FIELDS THAT SHOULD BE FORMULAS (not AI-computed) ────────
# These fields should be left empty so the Google Sheet calculates them.
# The sheet owner sets up the formulas in the header or via data validation.

FORMULA_FIELDS = {
    "Weighted_Score",    # Calculated from 6 dimension scores in 9_RELEVANCE
    "Relevance_Tier",    # Calculated from Weighted_Score in 9_RELEVANCE
    "Priority_Score",    # Calculated from Severity, Feasibility, Novelty in GAP_TRACKER
}


# ─── SHEET POPULATOR ─────────────────────────────────────────

class SheetPopulator:
    """Writes extraction data to the Google Sheet, aligned by header names."""

    def __init__(self, on_status: callable = None):
        self.on_status = on_status or (lambda msg: print(f"     → {msg}"))
        self._client = None
        self._spreadsheet = None
        self._worksheets = {}       # tab_name -> worksheet
        self._header_cache = {}     # tab_name -> list[str] (raw headers)
        self._header_map_cache = {} # tab_name -> dict[normalized_name -> col_index (0-based)]
        self._next_row_cache = {}   # tab_name -> int (next empty row number)

    def _ensure_connected(self):
        """Lazy connect to Google Sheets."""
        if self._client is None:
            self.on_status("Connecting to Google Sheets...")
            self._client = authenticate()
            self._spreadsheet = self._client.open_by_key(SPREADSHEET_ID)
            self.on_status("Connected.")

    def _get_worksheet(self, tab_name: str) -> gspread.Worksheet:
        """Get or cache a worksheet by tab name."""
        if tab_name not in self._worksheets:
            self._ensure_connected()
            self._worksheets[tab_name] = self._spreadsheet.worksheet(tab_name)
        return self._worksheets[tab_name]

    @retry_on_api_error()
    def _read_headers(self, tab_name: str) -> list[str]:
        """Read row 1 headers from a tab. Cached after first read."""
        if tab_name not in self._header_cache:
            ws = self._get_worksheet(tab_name)
            self._header_cache[tab_name] = ws.row_values(1)
        return self._header_cache[tab_name]

    def _get_header_map(self, tab_name: str) -> dict[str, int]:
        """
        Build normalized_header_name -> column_index (0-based) mapping.
        Handles empty headers (like col A in 7_FINDINGS where PAPER_ID goes).
        """
        if tab_name not in self._header_map_cache:
            raw_headers = self._read_headers(tab_name)
            mapping = {}
            for idx, header in enumerate(raw_headers):
                norm = normalize_header(header)
                if norm:
                    mapping[norm] = idx
                elif idx == 0:
                    # Empty first column header — this is the PAPER_ID column
                    mapping["PAPER_ID"] = idx
            self._header_map_cache[tab_name] = mapping
        return self._header_map_cache[tab_name]

    @retry_on_api_error()
    def _check_duplicate(self, tab_name: str, paper_id: str) -> bool:
        """Check if PAPER_ID already exists in the PAPER_ID column."""
        ws = self._get_worksheet(tab_name)
        header_map = self._get_header_map(tab_name)
        pid_col = header_map.get("PAPER_ID", 0)
        col_values = ws.col_values(pid_col + 1)  # col_values is 1-indexed
        return paper_id in col_values

    def _get_next_row(self, tab_name: str) -> int:
        """
        Get the next empty row for a tab. Reads from sheet on first call,
        then increments locally — eliminates 2 API reads per write.
        """
        if tab_name not in self._next_row_cache:
            ws = self._get_worksheet(tab_name)
            raw_headers = self._read_headers(tab_name)
            num_cols = len(raw_headers)
            self._next_row_cache[tab_name] = self._find_next_empty_row(ws, num_cols)
        return self._next_row_cache[tab_name]

    def _advance_next_row(self, tab_name: str):
        """Increment cached next-row after a successful write."""
        if tab_name in self._next_row_cache:
            self._next_row_cache[tab_name] += 1

    def invalidate_next_row(self, tab_name: str):
        """Force re-read of next row position (use after external writes)."""
        self._next_row_cache.pop(tab_name, None)

    @retry_on_api_error()
    def _write_row_by_headers(self, tab_name: str, data: dict):
        """
        Write a row to a tab, aligned by matching data keys to sheet headers.
        Values go into the correct column regardless of position.
        Uses cached next-row position to avoid repeated reads.
        """
        ws = self._get_worksheet(tab_name)
        raw_headers = self._read_headers(tab_name)
        header_map = self._get_header_map(tab_name)

        row = [""] * len(raw_headers)

        for field_name, value in data.items():
            # Skip formula fields — let the sheet calculate them
            if field_name in FORMULA_FIELDS:
                continue

            col_idx = header_map.get(field_name)
            if col_idx is not None:
                # Convert non-string types
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                elif value is None:
                    value = ""
                else:
                    value = str(value)
                row[col_idx] = value

        next_row = self._get_next_row(tab_name)
        num_cols = len(raw_headers)
        end_col_letter = _col_letter(num_cols)
        cell_range = f"A{next_row}:{end_col_letter}{next_row}"
        ws.update(cell_range, [row], value_input_option="USER_ENTERED")
        self._advance_next_row(tab_name)

    @retry_on_api_error()
    def _find_next_empty_row(self, ws: gspread.Worksheet, num_cols: int) -> int:
        """Find the first empty row after the header row."""
        # Get all values in column B (usually has data even if col A is empty-headered)
        # Fall back to col A if col B is shorter
        col_b = ws.col_values(2) if num_cols >= 2 else []
        col_a = ws.col_values(1)
        max_len = max(len(col_a), len(col_b))
        return max_len + 1

    def populate_paper(self, paper_id: str, extraction: dict) -> bool:
        """
        Write one paper's extraction data to all 12 data tabs + MASTER_VIEW.
        Returns True if all writes succeed.
        """
        self._ensure_connected()

        # Check for duplicate in first tab
        if self._check_duplicate("1_IDENTIFICATION", paper_id):
            self.on_status(f"Paper {paper_id} already exists in sheet — skipping")
            return True

        success = True

        for section_key in EXTRACTION_SECTIONS:
            section_data = extraction.get(section_key, {})
            if not isinstance(section_data, dict):
                self.on_status(f"Skipping {section_key}: not a dict")
                continue

            # Ensure PAPER_ID is set
            section_data["PAPER_ID"] = paper_id

            try:
                self._write_row_by_headers(section_key, section_data)
                self.on_status(f"  ✅ {section_key}")
            except Exception as e:
                self.on_status(f"  ❌ {section_key}: {e}")
                success = False

            time.sleep(SHEETS_WRITE_DELAY)

        # Write to MASTER_VIEW (just PAPER_ID in column A)
        try:
            self._write_row_by_headers("MASTER_VIEW", {"PAPER_ID": paper_id})
            self.on_status(f"  ✅ MASTER_VIEW")
        except Exception as e:
            self.on_status(f"  ❌ MASTER_VIEW: {e}")
            success = False

        return success

    def update_gap_tracker(self, gap_analysis: dict, paper_id: str) -> bool:
        """
        Update GAP_TRACKER tab:
        - Batch-update existing gaps (single read + single write)
        - Batch-append new gaps (single multi-row write)
        """
        self._ensure_connected()

        existing_updates = gap_analysis.get("existing_gaps_updated", [])
        new_gaps = gap_analysis.get("new_gaps_identified", [])

        if not existing_updates and not new_gaps:
            return True

        success = True

        # ── BATCH UPDATE EXISTING GAPS ──────────────────────
        # One read of the entire sheet, build all cell updates, one write.
        if existing_updates:
            try:
                success = self._batch_update_existing_gaps(existing_updates, paper_id)
            except Exception as e:
                self.on_status(f"  ❌ GAP_TRACKER batch update: {e}")
                success = False

        # ── BATCH APPEND NEW GAPS ───────────────────────────
        # Build all rows, write them in a single multi-row update.
        if new_gaps:
            try:
                ok = self._batch_append_new_gaps(new_gaps, paper_id)
                if not ok:
                    success = False
            except Exception as e:
                self.on_status(f"  ❌ GAP_TRACKER batch append: {e}")
                success = False

        return success

    @retry_on_api_error()
    def _batch_update_existing_gaps(self, updates: list[dict], paper_id: str) -> bool:
        """
        Read GAP_TRACKER once, build all cell edits, write once.
        Reduces N gaps × 3 API calls → 1 read + 1 write = 2 calls total.
        """
        ws = self._get_worksheet("GAP_TRACKER")
        header_map = self._get_header_map("GAP_TRACKER")

        # Single read: get all data from the sheet
        all_data = ws.get_all_values()
        if not all_data:
            return True

        # Build gap_id -> row_index mapping from column A
        gap_id_col = 0  # Gap_ID is always col A
        gap_row_map = {}
        for row_idx, row in enumerate(all_data):
            if row_idx == 0:
                continue  # skip header
            if row and row[gap_id_col].strip():
                gap_row_map[row[gap_id_col].strip()] = row_idx  # 0-based

        cov_col = header_map.get("Coverage_Level")
        covering_col = header_map.get("Covering_Paper_IDs")
        notes_col = header_map.get("Coverage_Notes")

        cells_to_update = []

        for update in updates:
            gap_id = update.get("gap_id", "").strip()
            if not gap_id:
                continue

            row_idx_0 = gap_row_map.get(gap_id)
            if row_idx_0 is None:
                self.on_status(f"  ⚠️  Gap {gap_id} not found in sheet")
                continue

            sheet_row = row_idx_0 + 1  # gspread Cell is 1-indexed
            row_data = all_data[row_idx_0]

            if cov_col is not None:
                cells_to_update.append(
                    gspread.Cell(sheet_row, cov_col + 1, update.get("new_coverage_level", ""))
                )

            if covering_col is not None:
                existing_val = row_data[covering_col] if covering_col < len(row_data) else ""
                new_val = f"{existing_val}, {paper_id}".strip(", ") if existing_val else paper_id
                cells_to_update.append(
                    gspread.Cell(sheet_row, covering_col + 1, new_val)
                )

            if notes_col is not None:
                cells_to_update.append(
                    gspread.Cell(sheet_row, notes_col + 1, update.get("coverage_notes", ""))
                )

            self.on_status(f"  🔄 GAP_TRACKER updated: {gap_id}")

        if cells_to_update:
            ws.update_cells(cells_to_update, value_input_option="USER_ENTERED")
            time.sleep(SHEETS_WRITE_DELAY)

        return True

    @retry_on_api_error()
    def _batch_append_new_gaps(self, new_gaps: list[dict], paper_id: str) -> bool:
        """
        Build all new gap rows and write them in a single multi-row update.
        Reduces N gaps × 3 API calls → 1 write = 1 call total.
        """
        ws = self._get_worksheet("GAP_TRACKER")
        raw_headers = self._read_headers("GAP_TRACKER")
        header_map = self._get_header_map("GAP_TRACKER")
        num_cols = len(raw_headers)

        rows_to_write = []

        for new_gap in new_gaps:
            gap_id = new_gap.get("gap_id", "")
            if not gap_id:
                continue

            gap_data = {
                "Gap_ID": gap_id,
                "Gap_Type": new_gap.get("gap_type", ""),
                "Gap_Statement": new_gap.get("gap_statement", ""),
                "Severity": str(new_gap.get("severity", "")),
                "Feasibility": str(new_gap.get("feasibility", "")),
                "Novelty": str(new_gap.get("novelty", "")),
                "Source_Paper_IDs": paper_id,
                "Paper_Assignment": new_gap.get("paper_assignment", ""),
                "Potential_Hypothesis": new_gap.get("potential_hypothesis", ""),
                "Variables_Needed": new_gap.get("variables_needed", ""),
                "Methodology_Needed": new_gap.get("methodology_needed", ""),
                "Data_Available": new_gap.get("data_available", ""),
                "Status": new_gap.get("status", "Identified"),
                "Notes": "",
                "Coverage_Level": new_gap.get("coverage_level", "NOT ADDRESSED"),
                "Covering_Paper_IDs": "",
                "Coverage_Notes": "",
            }

            row = [""] * num_cols
            for field_name, value in gap_data.items():
                if field_name in FORMULA_FIELDS:
                    continue
                col_idx = header_map.get(field_name)
                if col_idx is not None:
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value, ensure_ascii=False)
                    elif value is None:
                        value = ""
                    else:
                        value = str(value)
                    row[col_idx] = value

            rows_to_write.append(row)
            self.on_status(f"  ➕ GAP_TRACKER new: {gap_id}")

        if not rows_to_write:
            return True

        # Get the starting row (one read)
        start_row = self._get_next_row("GAP_TRACKER")
        end_row = start_row + len(rows_to_write) - 1
        end_col_letter = _col_letter(num_cols)
        cell_range = f"A{start_row}:{end_col_letter}{end_row}"

        ws.update(cell_range, rows_to_write, value_input_option="USER_ENTERED")

        # Update cached next-row position
        self._next_row_cache["GAP_TRACKER"] = end_row + 1

        time.sleep(SHEETS_WRITE_DELAY)
        return True
