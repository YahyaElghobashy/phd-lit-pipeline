#!/usr/bin/env python3
"""
Migration Script: GAP_COVERAGE_MAP + GAP_NOVELTY -> GAP_MATRIX
================================================================
One-time migration that:
1. Creates GAP_MATRIX tab in the original sheet
2. Creates GAP_EVIDENCE tab in the original sheet
3. Populates Gap_ID column from GAP_TRACKER
4. Back-populates from existing GAP_COVERAGE_MAP data (approximate percentages)
5. Merges GAP_NOVELTY data from the auto sheet
6. Computes initial Pct_Remaining and Gap_State

Usage:
    python3 scripts/migrate_to_gap_matrix.py --dry-run    # Preview
    python3 scripts/migrate_to_gap_matrix.py              # Execute
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

from populator import authenticate, retry_on_api_error
from config import SPREADSHEET_ID, SHEETS_WRITE_DELAY
from discovery_config import AUTO_SPREADSHEET_ID
from gap_matrix_analyzer import (
    GAP_MATRIX_TAB, GAP_EVIDENCE_TAB, GAP_EVIDENCE_COLUMNS,
    RESOLVED_THRESHOLD, _derive_gap_state,
)

console = Console()

# ─── IMPACT LEVEL -> APPROXIMATE PERCENTAGE ─────────────────
# Used to convert old GAP_COVERAGE_MAP categorical levels to %
IMPACT_TO_PCT = {
    "DIRECTLY TACKLED": 80,
    "SUBSTANTIALLY COVERED": 45,
    "PARTIALLY ADDRESSED": 15,
    "NOT ADDRESSED": 0,
}

# Same mapping for GAP_NOVELTY impact levels
NOVELTY_IMPACT_TO_PCT = {
    "DIRECTLY TACKLED": 80,
    "SUBSTANTIALLY COVERED": 45,
    "PARTIALLY ADDRESSED": 15,
    "NOT ADDRESSED": 0,
}


@retry_on_api_error()
def _read_gap_ids(client) -> list[dict]:
    """Read gap IDs and statements from GAP_TRACKER."""
    sheet = client.open_by_key(SPREADSHEET_ID)
    ws = sheet.worksheet("GAP_TRACKER")
    rows = ws.get_all_records()
    gaps = []
    for row in rows:
        gid = str(row.get("Gap_ID", "")).strip()
        if gid:
            gaps.append({
                "gap_id": gid,
                "gap_type": str(row.get("Gap_Type", "")),
                "gap_statement": str(row.get("Gap_Statement", "")),
            })
    return gaps


@retry_on_api_error()
def _read_coverage_map(client) -> list[dict]:
    """Read existing GAP_COVERAGE_MAP rows."""
    sheet = client.open_by_key(SPREADSHEET_ID)
    try:
        ws = sheet.worksheet("GAP_COVERAGE_MAP")
    except Exception:
        console.print("  [yellow]GAP_COVERAGE_MAP tab not found — skipping[/]")
        return []

    rows = ws.get_all_records()
    entries = []
    for row in rows:
        pid = str(row.get("PAPER_ID", "")).strip()
        gid = str(row.get("Gap_ID", "")).strip()
        level = str(row.get("Coverage_Level", "NOT ADDRESSED")).strip()
        if pid and gid:
            entries.append({"paper_id": pid, "gap_id": gid, "level": level})
    return entries


@retry_on_api_error()
def _read_novelty_map(client) -> list[dict]:
    """Read existing GAP_NOVELTY rows from auto sheet."""
    try:
        sheet = client.open_by_key(AUTO_SPREADSHEET_ID)
        ws = sheet.worksheet("GAP_NOVELTY")
    except Exception:
        console.print("  [yellow]GAP_NOVELTY tab not found in auto sheet — skipping[/]")
        return []

    rows = ws.get_all_records()
    entries = []
    for row in rows:
        pid = str(row.get("PAPER_ID", "")).strip()
        gid = str(row.get("Gap_ID", "")).strip()
        level = str(row.get("Impact_Level", "NOT ADDRESSED")).strip()
        if pid and gid:
            entries.append({"paper_id": pid, "gap_id": gid, "level": level})
    return entries


def _compute_matrix(
    gap_ids: list[str],
    coverage_entries: list[dict],
    novelty_entries: list[dict],
) -> dict:
    """
    Compute initial matrix values from existing coverage + novelty data.
    Returns: {
        "paper_ids": [...],
        "scores": {(gid, pid): pct_str},
        "pct_remaining": {gid: float},
    }
    """
    # Merge all entries, dedup by (paper_id, gap_id) — coverage takes priority
    all_entries = {}
    for e in novelty_entries:
        key = (e["gap_id"], e["paper_id"])
        pct = NOVELTY_IMPACT_TO_PCT.get(e["level"], 0)
        if pct > 0:
            all_entries[key] = pct

    for e in coverage_entries:
        key = (e["gap_id"], e["paper_id"])
        pct = IMPACT_TO_PCT.get(e["level"], 0)
        if pct > 0:
            all_entries[key] = pct  # Overwrite novelty if both exist

    # Collect paper IDs in order of first appearance
    paper_ids_seen = {}
    for (gid, pid), pct in sorted(all_entries.items()):
        if pid not in paper_ids_seen:
            paper_ids_seen[pid] = len(paper_ids_seen)
    paper_ids = list(paper_ids_seen.keys())

    # Compute cumulative Pct_Remaining per gap
    # Process papers in order; each paper's effect is applied sequentially
    pct_remaining = {gid: 100.0 for gid in gap_ids}
    scores = {}

    for pid in paper_ids:
        for gid in gap_ids:
            key = (gid, pid)
            if key in all_entries:
                raw_pct = all_entries[key]
                # Scale the raw percentage to be relative to what remains
                # Since old data was absolute, we approximate:
                # If gap has 100% remaining and paper scored 45%, that's 45% of 100% = 45%
                # If gap has 55% remaining and paper scored 15%, that's ~15% of 55% ≈ 8.25%
                # For migration, we use the raw_pct as % of remaining
                actual_eliminated = pct_remaining[gid] * (raw_pct / 100)
                pct_remaining[gid] = max(0, pct_remaining[gid] - actual_eliminated)
                scores[key] = f"{raw_pct}%"

    # Round remaining
    for gid in gap_ids:
        pct_remaining[gid] = round(pct_remaining[gid], 1)

    return {
        "paper_ids": paper_ids,
        "scores": scores,
        "pct_remaining": pct_remaining,
    }


@retry_on_api_error()
def _create_matrix_tab(client, gap_ids: list[str], matrix_data: dict) -> None:
    """Create and populate the GAP_MATRIX tab."""
    sheet = client.open_by_key(SPREADSHEET_ID)

    # Delete existing tab if present
    try:
        existing = sheet.worksheet(GAP_MATRIX_TAB)
        sheet.del_worksheet(existing)
        console.print(f"  [yellow]Deleted existing {GAP_MATRIX_TAB} tab[/]")
        time.sleep(2)
    except Exception:
        pass

    n_cols = 3 + len(matrix_data["paper_ids"])  # Gap_ID, Pct_Remaining, Gap_State + papers
    ws = sheet.add_worksheet(
        title=GAP_MATRIX_TAB,
        rows=max(len(gap_ids) + 1, 10),
        cols=max(n_cols, 10),
    )
    time.sleep(1)

    # Build header row
    header = ["Gap_ID", "Pct_Remaining", "Gap_State"] + matrix_data["paper_ids"]

    # Build data rows
    rows = [header]
    for gid in gap_ids:
        pct = matrix_data["pct_remaining"].get(gid, 100.0)
        state = _derive_gap_state(pct)
        row = [gid, f"{pct:.1f}%", state]
        for pid in matrix_data["paper_ids"]:
            score = matrix_data["scores"].get((gid, pid), "")
            row.append(score)
        rows.append(row)

    # Batch write
    ws.update(range_name="A1", values=rows)
    console.print(f"  [green]GAP_MATRIX tab created: {len(gap_ids)} gaps x {len(matrix_data['paper_ids'])} papers[/]")


@retry_on_api_error()
def _create_evidence_tab(client) -> None:
    """Create the GAP_EVIDENCE tab with headers."""
    sheet = client.open_by_key(SPREADSHEET_ID)

    # Delete existing if present
    try:
        existing = sheet.worksheet(GAP_EVIDENCE_TAB)
        sheet.del_worksheet(existing)
        console.print(f"  [yellow]Deleted existing {GAP_EVIDENCE_TAB} tab[/]")
        time.sleep(2)
    except Exception:
        pass

    ws = sheet.add_worksheet(
        title=GAP_EVIDENCE_TAB,
        rows=1000,
        cols=len(GAP_EVIDENCE_COLUMNS),
    )
    time.sleep(1)

    ws.update(range_name="A1", values=[GAP_EVIDENCE_COLUMNS])
    console.print(f"  [green]GAP_EVIDENCE tab created ({len(GAP_EVIDENCE_COLUMNS)} columns)[/]")


def migrate(dry_run: bool = False):
    """Run the full migration."""
    content = Text()
    content.append("MIGRATE TO GAP_MATRIX\n\n", style="bold magenta")
    content.append("Replaces GAP_COVERAGE_MAP + GAP_NOVELTY with unified GAP_MATRIX\n", style="dim")
    if dry_run:
        content.append("\nDRY RUN — no changes will be made\n", style="yellow bold")
    console.print(Panel(content, border_style="magenta", box=box.DOUBLE))
    console.print()

    console.print("[bold blue]Step 1: Authenticating...[/]")
    client = authenticate()

    console.print("[bold blue]Step 2: Reading GAP_TRACKER...[/]")
    gaps = _read_gap_ids(client)
    gap_ids = [g["gap_id"] for g in gaps]
    console.print(f"  Found {len(gaps)} gaps")

    console.print("[bold blue]Step 3: Reading GAP_COVERAGE_MAP...[/]")
    time.sleep(1)
    coverage = _read_coverage_map(client)
    console.print(f"  Found {len(coverage)} coverage entries")
    # Count non-trivial
    non_zero_cov = sum(1 for e in coverage if IMPACT_TO_PCT.get(e["level"], 0) > 0)
    console.print(f"  Non-trivial entries: {non_zero_cov}")

    console.print("[bold blue]Step 4: Reading GAP_NOVELTY...[/]")
    time.sleep(1)
    novelty = _read_novelty_map(client)
    console.print(f"  Found {len(novelty)} novelty entries")
    non_zero_nov = sum(1 for e in novelty if NOVELTY_IMPACT_TO_PCT.get(e["level"], 0) > 0)
    console.print(f"  Non-trivial entries: {non_zero_nov}")

    console.print("[bold blue]Step 5: Computing matrix...[/]")
    matrix_data = _compute_matrix(gap_ids, coverage, novelty)
    console.print(f"  Papers: {len(matrix_data['paper_ids'])}")
    console.print(f"  Non-zero cells: {len(matrix_data['scores'])}")

    # State distribution
    state_counts = {}
    for gid in gap_ids:
        pct = matrix_data["pct_remaining"].get(gid, 100.0)
        state = _derive_gap_state(pct)
        state_counts[state] = state_counts.get(state, 0) + 1
    console.print(f"  State distribution: {state_counts}")

    if dry_run:
        console.print("\n[yellow]DRY RUN complete. No changes made.[/]")
        console.print(f"  Would create GAP_MATRIX: {len(gap_ids)} rows x {3 + len(matrix_data['paper_ids'])} cols")
        console.print(f"  Would create GAP_EVIDENCE: {len(GAP_EVIDENCE_COLUMNS)} columns")
        return

    console.print("[bold blue]Step 6: Creating GAP_MATRIX tab...[/]")
    time.sleep(2)
    _create_matrix_tab(client, gap_ids, matrix_data)

    console.print("[bold blue]Step 7: Creating GAP_EVIDENCE tab...[/]")
    time.sleep(2)
    _create_evidence_tab(client)

    console.print("\n[bold green]Migration complete![/]")
    console.print(f"  GAP_MATRIX: {len(gap_ids)} gaps x {len(matrix_data['paper_ids'])} papers")
    console.print(f"  GAP_EVIDENCE: ready for new assessments")
    console.print(f"\n  [dim]Old tabs (GAP_COVERAGE_MAP, GAP_NOVELTY) preserved for reference.[/]")
    console.print(f"  [dim]Delete them manually once you've verified the migration.[/]\n")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    migrate(dry_run=dry)
