"""
PhD Literature Extraction Pipeline — Sheet Factory
=====================================================
Programmatically creates Google Sheets and Drive folders from a ResearchConfig.
Used by setup_wizard.py to bootstrap a new research project.

Functions:
  - create_main_sheet(config)   → Creates the main extraction spreadsheet
  - create_auto_sheet(config)   → Creates the automated discovery spreadsheet
  - create_local_folders(base)  → Creates local directory structure
  - create_drive_folders(config)→ Creates Google Drive folder hierarchy
  - update_config_sheet_ids()   → Patches research_config.yaml with new IDs
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import gspread
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

from populator import authenticate, retry_on_api_error
from codegen.config_loader import ResearchConfig
from schemas import COLUMNS, EXTRACTION_SECTIONS

console = Console()


# ─── TAB DEFINITIONS ────────────────────────────────────────

# Standard extraction section tabs (from schemas.py)
_STANDARD_SECTION_TABS = list(EXTRACTION_SECTIONS)

# Gap analysis tabs (main sheet only)
_GAP_TABS = ["GAP_TRACKER", "GAP_MATRIX", "GAP_EVIDENCE"]

# Shared utility tabs
_UTILITY_TABS = ["MASTER_VIEW", "Literature_Review_Summary"]

# GAP_MATRIX gets a minimal seed header; real columns are added per-paper
_GAP_MATRIX_SEED_HEADERS = [
    "Gap_ID", "Gap_Statement", "Pct_Remaining", "Status",
]

_MASTER_VIEW_HEADERS = [
    "PAPER_ID", "Title", "Year", "Relevance_Tier", "Primary_Theme",
    "Paper_Assignment", "Weighted_Score",
]

_SUMMARY_HEADERS = [
    "PAPER_ID", "Summary", "Abstract", "Key_Contribution",
    "Relevance_Score", "Primary_Theme",
]


# ─── HELPERS ────────────────────────────────────────────────


def _get_section_tabs(config: ResearchConfig) -> list[str]:
    """Return ordered list of section tab names (standard + custom)."""
    tabs = list(_STANDARD_SECTION_TABS)
    for cs in config.custom_sections:
        tabs.append(cs.id)
    return tabs


def _get_headers_for_tab(tab_name: str, config: ResearchConfig) -> list[str]:
    """Return column headers for a given tab name."""
    # Check schemas.py COLUMNS dict first
    if tab_name in COLUMNS:
        return list(COLUMNS[tab_name])

    # Check custom sections
    for cs in config.custom_sections:
        if cs.id == tab_name:
            return ["PAPER_ID"] + [col.name for col in cs.columns]

    # Special tabs
    if tab_name == "GAP_MATRIX":
        return list(_GAP_MATRIX_SEED_HEADERS)
    if tab_name == "MASTER_VIEW":
        return list(_MASTER_VIEW_HEADERS)
    if tab_name == "Literature_Review_Summary":
        return list(_SUMMARY_HEADERS)

    # Fallback: just PAPER_ID
    return ["PAPER_ID"]


@retry_on_api_error()
def _create_spreadsheet(client: gspread.Client, title: str) -> gspread.Spreadsheet:
    """Create a new Google Spreadsheet, handling Drive API fallback."""
    try:
        spreadsheet = client.create(title)
        return spreadsheet
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
            body = {"properties": {"title": title}}
            result = sheets_service.spreadsheets().create(body=body).execute()
            sheet_id = result["spreadsheetId"]
            return client.open_by_key(sheet_id)
        raise


@retry_on_api_error()
def _add_tab_with_headers(
    spreadsheet: gspread.Spreadsheet,
    tab_name: str,
    headers: list[str],
    is_first: bool = False,
) -> None:
    """Add a worksheet with headers, or rename Sheet1 if first tab."""
    if is_first:
        ws = spreadsheet.sheet1
        ws.update_title(tab_name)
    else:
        ws = spreadsheet.add_worksheet(
            title=tab_name,
            rows=1000,
            cols=max(len(headers), 26),
        )

    if headers:
        ws.update(range_name="A1", values=[headers])


# ─── MAIN SHEET CREATION ────────────────────────────────────


def create_main_sheet(config: ResearchConfig, dry_run: bool = False) -> str:
    """
    Create main extraction sheet. Returns spreadsheet ID.

    Sheet name: "{config.project.short_title} -- Literature Extraction"

    Tabs created (in order):
      1. All extraction section tabs (standard 1-11/12 + custom sections)
      2. GAP_TRACKER
      3. GAP_MATRIX
      4. GAP_EVIDENCE
      5. MASTER_VIEW
      6. Literature_Review_Summary

    Headers come from schemas.py COLUMNS dict.
    Rate limit: time.sleep(1.5) between tab creations.
    """
    sheet_title = f"{config.project.short_title} — Literature Extraction"

    # Build ordered tab list
    section_tabs = _get_section_tabs(config)
    all_tabs = section_tabs + _GAP_TABS + _UTILITY_TABS

    console.print()
    content = Text()
    content.append("MAIN EXTRACTION SHEET\n", style="bold cyan")
    content.append(f"Title: {sheet_title}\n", style="dim")
    content.append(f"Tabs: {len(all_tabs)}\n", style="dim")
    console.print(Panel(content, border_style="cyan", box=box.DOUBLE))
    console.print()

    if dry_run:
        console.print("[yellow]DRY RUN — would create sheet with these tabs:[/]")
        for tab in all_tabs:
            headers = _get_headers_for_tab(tab, config)
            console.print(f"  - {tab} ({len(headers)} cols)")
        return ""

    # Authenticate and create
    client = authenticate()
    console.print("[bold blue]Creating spreadsheet...[/]")
    spreadsheet = _create_spreadsheet(client, sheet_title)
    sheet_id = spreadsheet.id
    console.print(
        f"  [green]Created:[/] [link=https://docs.google.com/spreadsheets/d/{sheet_id}]{sheet_id}[/link]"
    )

    # Create tabs
    first_tab = True
    for tab_name in all_tabs:
        headers = _get_headers_for_tab(tab_name, config)
        _add_tab_with_headers(spreadsheet, tab_name, headers, is_first=first_tab)
        first_tab = False
        console.print(f"  [green]>[/] {tab_name} ({len(headers)} cols)")
        time.sleep(1.5)

    console.print()
    console.print(f"[bold green]Main sheet ready![/]")
    console.print(f"  URL: https://docs.google.com/spreadsheets/d/{sheet_id}")
    console.print(f"  ID:  {sheet_id}")

    return sheet_id


# ─── AUTO SHEET CREATION ────────────────────────────────────


def create_auto_sheet(config: ResearchConfig, dry_run: bool = False) -> str:
    """
    Create automated extraction sheet (for discovery pipeline).
    Returns spreadsheet ID.

    Sheet name: "{config.project.short_title} -- Auto Discovery"

    Same extraction tabs as main sheet, plus MASTER_VIEW and Literature_Review_Summary.
    NO GAP_TRACKER, GAP_MATRIX, or GAP_EVIDENCE (those stay in main sheet).
    """
    sheet_title = f"{config.project.short_title} — Auto Discovery"

    # Build ordered tab list: sections + utility (no gap tabs)
    section_tabs = _get_section_tabs(config)
    all_tabs = section_tabs + _UTILITY_TABS

    console.print()
    content = Text()
    content.append("AUTO DISCOVERY SHEET\n", style="bold magenta")
    content.append(f"Title: {sheet_title}\n", style="dim")
    content.append(f"Tabs: {len(all_tabs)}\n", style="dim")
    content.append("No GAP_TRACKER / GAP_MATRIX / GAP_EVIDENCE\n", style="dim yellow")
    console.print(Panel(content, border_style="magenta", box=box.DOUBLE))
    console.print()

    if dry_run:
        console.print("[yellow]DRY RUN — would create sheet with these tabs:[/]")
        for tab in all_tabs:
            headers = _get_headers_for_tab(tab, config)
            console.print(f"  - {tab} ({len(headers)} cols)")
        return ""

    # Authenticate and create
    client = authenticate()
    console.print("[bold blue]Creating spreadsheet...[/]")
    spreadsheet = _create_spreadsheet(client, sheet_title)
    sheet_id = spreadsheet.id
    console.print(
        f"  [green]Created:[/] [link=https://docs.google.com/spreadsheets/d/{sheet_id}]{sheet_id}[/link]"
    )

    # Create tabs
    first_tab = True
    for tab_name in all_tabs:
        headers = _get_headers_for_tab(tab_name, config)
        _add_tab_with_headers(spreadsheet, tab_name, headers, is_first=first_tab)
        first_tab = False
        console.print(f"  [green]>[/] {tab_name} ({len(headers)} cols)")
        time.sleep(1.5)

    console.print()
    console.print(f"[bold green]Auto sheet ready![/]")
    console.print(f"  URL: https://docs.google.com/spreadsheets/d/{sheet_id}")
    console.print(f"  ID:  {sheet_id}")

    return sheet_id


# ─── LOCAL FOLDERS ───────────────────────────────────────────


def create_local_folders(base_dir: Path) -> list[str]:
    """
    Create standard pipeline directories under base_dir.

    Creates:
      - extractions/
      - discoveries/
      - reports/
      - pipeline_data/

    Returns list of created (or already-existing) directory paths.
    """
    base_dir = Path(base_dir)
    folder_names = ["extractions", "discoveries", "reports", "pipeline_data"]
    created = []

    for name in folder_names:
        folder = base_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        created.append(str(folder))
        status = "created" if not folder.exists() else "exists"
        console.print(f"  [green]>[/] {folder}  [dim]({status})[/]")

    return created


# ─── GOOGLE DRIVE FOLDERS ───────────────────────────────────


def create_drive_folders(config: ResearchConfig) -> dict:
    """
    Create Google Drive folder structure:

      {short_title}/
        +-- Papers/
        +-- Automated Extraction/
        +-- Extractions/
        +-- Reports/

    Returns {folder_name: folder_id}.
    Uses google-api-python-client (googleapiclient.discovery) for Drive API.
    Auth: reuse the OAuth2 credentials from populator.authenticate() flow.
    """
    from google.oauth2.credentials import Credentials as OAuthCreds
    from google.auth.transport.requests import Request as AuthRequest
    from googleapiclient.discovery import build as build_service
    from config import TOKEN_FILE, SCOPES

    console.print()
    content = Text()
    content.append("GOOGLE DRIVE FOLDERS\n", style="bold green")
    content.append(f"Root: {config.project.short_title}/\n", style="dim")
    console.print(Panel(content, border_style="green", box=box.DOUBLE))
    console.print()

    # Authenticate with Drive API
    creds = OAuthCreds.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(AuthRequest())

    drive = build_service("drive", "v3", credentials=creds)

    def _create_folder(name: str, parent_id: str | None = None) -> str:
        """Create a Drive folder, return its ID."""
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = drive.files().create(body=metadata, fields="id").execute()
        return folder["id"]

    # Create root folder
    root_name = config.project.short_title
    root_id = _create_folder(root_name)
    console.print(f"  [green]>[/] {root_name}/  [dim](root)[/]")
    time.sleep(0.5)

    result = {root_name: root_id}

    # Create subfolders
    subfolders = ["Papers", "Automated Extraction", "Extractions", "Reports"]
    for sub in subfolders:
        sub_id = _create_folder(sub, parent_id=root_id)
        result[sub] = sub_id
        console.print(f"  [green]>[/]   {sub}/")
        time.sleep(0.5)

    console.print()
    console.print("[bold green]Drive folders created![/]")
    console.print(
        f"  [link=https://drive.google.com/drive/folders/{root_id}]Open in Drive[/link]"
    )

    return result


# ─── CONFIG UPDATER ──────────────────────────────────────────


def update_config_sheet_ids(config_path: str, main_id: str, auto_id: str) -> None:
    """
    Update research_config.yaml with the new spreadsheet IDs.

    Patches the google_sheets.spreadsheet_id and google_sheets.auto_spreadsheet_id
    fields in the YAML file.
    """
    from codegen.config_loader import load_config, save_config

    config_path = Path(config_path)
    if not config_path.exists():
        console.print(f"[red]Config file not found: {config_path}[/]")
        return

    config = load_config(config_path)

    updated = False
    if main_id:
        config.google_sheets.spreadsheet_id = main_id
        updated = True
    if auto_id:
        config.google_sheets.auto_spreadsheet_id = auto_id
        updated = True

    if updated:
        save_config(config, config_path)
        console.print(f"  [green]>[/] Updated {config_path.name}")
        if main_id:
            console.print(f"    spreadsheet_id = {main_id}")
        if auto_id:
            console.print(f"    auto_spreadsheet_id = {auto_id}")
    else:
        console.print("  [dim]No IDs to update[/]")


# ─── CLI ENTRY POINT ────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Create Google Sheets and Drive folders from research config"
    )
    parser.add_argument(
        "--config",
        default="research_config.yaml",
        help="Path to research_config.yaml",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--main-only", action="store_true", help="Create main sheet only")
    parser.add_argument("--auto-only", action="store_true", help="Create auto sheet only")
    parser.add_argument("--drive", action="store_true", help="Also create Drive folders")
    parser.add_argument("--local", action="store_true", help="Also create local folders")

    args = parser.parse_args()

    from codegen.config_loader import load_config

    cfg = load_config(args.config)

    main_id = ""
    auto_id = ""

    if not args.auto_only:
        main_id = create_main_sheet(cfg, dry_run=args.dry_run)

    if not args.main_only:
        auto_id = create_auto_sheet(cfg, dry_run=args.dry_run)

    if args.local:
        console.print("\n[bold blue]Creating local folders...[/]")
        create_local_folders(Path("."))

    if args.drive and not args.dry_run:
        create_drive_folders(cfg)

    if not args.dry_run and (main_id or auto_id):
        console.print("\n[bold blue]Updating config...[/]")
        update_config_sheet_ids(args.config, main_id, auto_id)
