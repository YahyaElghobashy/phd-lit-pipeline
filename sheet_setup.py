"""
PhD Literature Discovery Pipeline — Sheet Setup
==================================================
Programmatically creates the Automated Extraction Google Sheet:
- Clones tab structure from the original sheet (same headers)
- Removes GAP_TRACKER and GAP_COVERAGE_MAP tabs
- Adds GAP_NOVELTY tab with discovery-specific schema
- Stores the new sheet ID in discovery_config.py
"""
from __future__ import annotations

import time

import gspread
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

from populator import authenticate, retry_on_api_error, normalize_header
from discovery_config import (
    ORIGINAL_SPREADSHEET_ID,
    AUTO_SHEET_TABS,
)
from schemas import COLUMNS

console = Console()

# Tabs to skip from the original sheet (we don't need gap tracking in the auto sheet)
SKIP_TABS = {"GAP_TRACKER", "GAP_COVERAGE_MAP"}

# Tabs from original that we DO clone (with their headers)
CLONE_TABS = [
    "1_IDENTIFICATION",
    "2_RESEARCH_DESIGN",
    "3_VARIABLES",
    "4_METHODOLOGY",
    "5_SAMPLE",
    "6_THEORY",
    "7_FINDINGS",
    "8_GAPS_LIMITATIONS",
    "9_RELEVANCE",
    "10_CLASSIFICATION",
    "11_CONNECTIONS",
    "12_BOARD_CHARS",
]


@retry_on_api_error()
def _read_original_headers(client: gspread.Client) -> dict[str, list[str]]:
    """Read actual headers from each tab of the original sheet."""
    console.print("  [dim]Reading headers from original sheet...[/]")
    original = client.open_by_key(ORIGINAL_SPREADSHEET_ID)
    headers = {}
    for tab_name in CLONE_TABS:
        try:
            ws = original.worksheet(tab_name)
            row1 = ws.row_values(1)
            headers[tab_name] = row1
            console.print(f"    ✓ {tab_name}: {len(row1)} columns")
            time.sleep(1)  # Rate limit
        except gspread.WorksheetNotFound:
            # Fall back to schemas.py
            console.print(f"    ⚠ {tab_name} not found in original, using schemas.py")
            headers[tab_name] = COLUMNS.get(tab_name, [])
    return headers


@retry_on_api_error()
def _read_master_view_headers(client: gspread.Client) -> list[str]:
    """Read MASTER_VIEW headers from original sheet."""
    try:
        original = client.open_by_key(ORIGINAL_SPREADSHEET_ID)
        ws = original.worksheet("MASTER_VIEW")
        return ws.row_values(1)
    except gspread.WorksheetNotFound:
        return ["PAPER_ID"]


@retry_on_api_error()
def _read_summary_headers(client: gspread.Client) -> list[str]:
    """Read Literature_Review_Summary headers from original sheet."""
    try:
        original = client.open_by_key(ORIGINAL_SPREADSHEET_ID)
        ws = original.worksheet("Literature_Review_Summary")
        return ws.row_values(1)
    except gspread.WorksheetNotFound:
        return ["PAPER_ID", "Summary", "Abstract"]


def create_auto_sheet(dry_run: bool = False) -> str:
    """
    Create the Automated Extraction Google Sheet.

    Returns:
        The new spreadsheet ID.
    """
    console.print()
    content = Text()
    content.append("AUTOMATED EXTRACTION SHEET SETUP\n", style="bold magenta")
    content.append("Creating new Google Sheet for discovery pipeline\n", style="dim")
    console.print(Panel(content, border_style="magenta", box=box.DOUBLE))
    console.print()

    client = authenticate()

    # Step 1: Read headers from original
    original_headers = _read_original_headers(client)
    time.sleep(1)
    master_headers = _read_master_view_headers(client)
    time.sleep(1)
    summary_headers = _read_summary_headers(client)

    if dry_run:
        console.print("[yellow]DRY RUN — would create sheet with these tabs:[/]")
        for tab in AUTO_SHEET_TABS:
            cols = len(original_headers.get(tab, []))
            console.print(f"  • {tab} ({cols} cols)")
        console.print(f"  [dim]Note: Gap analysis now uses GAP_MATRIX in the original sheet[/]")
        return ""

    # Step 2: Create new spreadsheet
    # Try gspread.create first (uses Drive API). If Drive API is not enabled,
    # fall back to Sheets API v4 which can also create spreadsheets.
    console.print("[bold blue]Creating spreadsheet...[/]")
    try:
        spreadsheet = client.create("PhD Auto-Discovery Extraction")
        sheet_id = spreadsheet.id
    except Exception as e:
        if "403" in str(e) and "drive" in str(e).lower():
            console.print("[yellow]Drive API not enabled. Creating via Sheets API v4...[/]")
            from google.oauth2.credentials import Credentials as OAuthCreds
            from google.auth.transport.requests import Request as AuthRequest
            from googleapiclient.discovery import build as build_service
            from config import TOKEN_FILE, SCOPES

            creds = OAuthCreds.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(AuthRequest())
            sheets_service = build_service("sheets", "v4", credentials=creds)
            body = {"properties": {"title": "PhD Auto-Discovery Extraction"}}
            result = sheets_service.spreadsheets().create(body=body).execute()
            sheet_id = result["spreadsheetId"]
            spreadsheet = client.open_by_key(sheet_id)
        else:
            raise
    console.print(f"  ✅ Created: [link=https://docs.google.com/spreadsheets/d/{sheet_id}]{sheet_id}[/link]")

    # Step 3: Create tabs with headers
    # The default "Sheet1" will be renamed to the first tab
    first_tab = True
    for tab_name in CLONE_TABS:
        headers = original_headers.get(tab_name, COLUMNS.get(tab_name, []))
        if first_tab:
            # Rename default sheet
            ws = spreadsheet.sheet1
            ws.update_title(tab_name)
            first_tab = False
        else:
            ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=max(len(headers), 26))

        # Write headers
        if headers:
            ws.update(range_name='A1', values=[headers])

        console.print(f"  ✓ {tab_name} ({len(headers)} cols)")
        time.sleep(1.5)  # Rate limit

    # MASTER_VIEW tab
    ws = spreadsheet.add_worksheet(title="MASTER_VIEW", rows=1000, cols=max(len(master_headers), 10))
    if master_headers:
        ws.update(range_name='A1', values=[master_headers])
    console.print(f"  ✓ MASTER_VIEW ({len(master_headers)} cols)")
    time.sleep(1.5)

    # Literature_Review_Summary tab
    ws = spreadsheet.add_worksheet(title="Literature_Review_Summary", rows=1000, cols=max(len(summary_headers), 10))
    if summary_headers:
        ws.update(range_name='A1', values=[summary_headers])
    console.print(f"  ✓ Literature_Review_Summary ({len(summary_headers)} cols)")
    time.sleep(1.5)

    # Note: GAP_NOVELTY tab removed — gap analysis now uses GAP_MATRIX in original sheet

    # Step 4: Share sheet (make accessible)
    console.print("\n[bold blue]Sheet created successfully![/]")
    console.print(f"  📊 URL: https://docs.google.com/spreadsheets/d/{sheet_id}")
    console.print(f"  🔑 ID: {sheet_id}")

    # Step 5: Update discovery_config.py with the new ID
    _update_config_sheet_id(sheet_id)

    return sheet_id


def _update_config_sheet_id(sheet_id: str):
    """Update AUTO_SPREADSHEET_ID in discovery_config.py."""
    import re
    from pathlib import Path

    config_path = Path(__file__).parent / "discovery_config.py"
    content = config_path.read_text()

    # Replace the AUTO_SPREADSHEET_ID line
    new_content = re.sub(
        r'AUTO_SPREADSHEET_ID = "[^"]*"',
        f'AUTO_SPREADSHEET_ID = "{sheet_id}"',
        content,
    )

    if new_content != content:
        config_path.write_text(new_content)
        console.print(f"  ✅ Updated discovery_config.py with AUTO_SPREADSHEET_ID")
    else:
        console.print(f"  ⚠️  Could not update discovery_config.py automatically")
        console.print(f"     Set AUTO_SPREADSHEET_ID = \"{sheet_id}\"")


def verify_auto_sheet(sheet_id: str) -> bool:
    """Verify the auto sheet exists and has correct structure."""
    console.print(f"\n[bold blue]Verifying sheet {sheet_id}...[/]")
    client = authenticate()

    try:
        spreadsheet = client.open_by_key(sheet_id)
    except gspread.SpreadsheetNotFound:
        console.print("[red]Sheet not found![/]")
        return False

    # Check all expected tabs exist
    existing_tabs = {ws.title for ws in spreadsheet.worksheets()}
    expected_tabs = set(AUTO_SHEET_TABS)
    missing = expected_tabs - existing_tabs
    extra = existing_tabs - expected_tabs

    if missing:
        console.print(f"  ❌ Missing tabs: {missing}")
        return False

    console.print(f"  ✅ All {len(expected_tabs)} tabs present")
    if extra:
        console.print(f"  ℹ️  Extra tabs: {extra}")

    # Verify no GAP_TRACKER or GAP_COVERAGE_MAP
    for forbidden in ["GAP_TRACKER", "GAP_COVERAGE_MAP"]:
        if forbidden in existing_tabs:
            console.print(f"  ❌ Forbidden tab found: {forbidden}")
            return False

    console.print("  ✅ No GAP_TRACKER/GAP_COVERAGE_MAP tabs (correct)")
    console.print("[bold green]Verification passed![/]")
    return True


if __name__ == "__main__":
    import sys
    if "--dry-run" in sys.argv:
        create_auto_sheet(dry_run=True)
    else:
        sheet_id = create_auto_sheet()
        if sheet_id:
            verify_auto_sheet(sheet_id)
