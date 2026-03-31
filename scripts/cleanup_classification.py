#!/usr/bin/env python3
"""
Cleanup 10_CLASSIFICATION tab — standardize ALL binary/Yes-No columns.

Columns affected (all should be Yes/No):
  - Use_Case_Theory (E)
  - Use_Case_Methodology (F)
  - Use_Case_Variables (G)
  - Use_Case_Measurement (H)
  - Use_Case_Context (I)
  - Use_Case_Gaps (J)
  - Use_Case_H_Support (K)
  - Use_Case_H_Contradict (L)
  - Informs_Our_IV (N)
  - Informs_Our_DV (O)
  - Suggests_Moderators (P)
  - Suggests_Mediators (Q)
  - Suggests_Controls (R)

Mapping:
  TRUE/true/1/yes/Yes → "Yes"
  FALSE/false/0/no/No/empty → "No"
  Any descriptive text → "Yes" (preserving original in Classification_Notes)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add pipeline root to path
PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))

from config import SPREADSHEET_ID
from populator import authenticate

TAB_NAME = "10_CLASSIFICATION"

# ALL columns that should be binary Yes/No
BINARY_COLUMNS = [
    # Use_Case columns (E-L)
    "Use_Case_Theory",
    "Use_Case_Methodology",
    "Use_Case_Variables",
    "Use_Case_Measurement",
    "Use_Case_Context",
    "Use_Case_Gaps",
    "Use_Case_H_Support",
    "Use_Case_H_Contradict",
    # Informs/Suggests columns (N-R)
    "Informs_Our_IV",
    "Informs_Our_DV",
    "Suggests_Moderators",
    "Suggests_Mediators",
    "Suggests_Controls",
]

# Values that map to Yes
YES_VALUES = {"true", "yes", "1", "y"}
# Values that map to No
NO_VALUES = {"false", "no", "0", "n", ""}


def standardize_value(val: str) -> tuple[str, str | None]:
    """
    Returns (standardized_value, note_if_non_standard).
    Any non-empty descriptive text is treated as "Yes" (the field is relevant)
    with the original value preserved in notes.
    """
    clean = val.strip()
    lower = clean.lower()

    if lower in YES_VALUES:
        return "Yes", None
    if lower in NO_VALUES:
        return "No", None

    # Explicit "no" matches
    if "no" == lower or "false" == lower:
        return "No", None

    # Any non-empty descriptive text means the field IS relevant → "Yes"
    # Preserve the descriptive text in notes
    if clean:
        return "Yes", clean

    return "No", None


def main():
    print("🔧 Authenticating with Google Sheets...")
    gc = authenticate()
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(TAB_NAME)

    print(f"📄 Reading {TAB_NAME} tab...")
    all_values = ws.get_all_values()

    if not all_values:
        print("❌ Tab is empty!")
        return

    headers = all_values[0]
    rows = all_values[1:]

    print(f"   {len(rows)} data rows, {len(headers)} columns")
    print(f"   Headers: {headers}")

    # Find column indices for binary columns
    col_indices: dict[str, int] = {}
    for col_name in BINARY_COLUMNS:
        if col_name in headers:
            col_indices[col_name] = headers.index(col_name)
        else:
            print(f"   ⚠️  Column '{col_name}' not found in headers")

    if not col_indices:
        print("❌ No binary columns found!")
        return

    print(f"   Found {len(col_indices)}/{len(BINARY_COLUMNS)} binary columns")

    # Check if Notes column already exists
    notes_col_name = "Classification_Notes"
    if notes_col_name in headers:
        notes_col_idx = headers.index(notes_col_name)
        print(f"   Notes column exists at index {notes_col_idx}")
    else:
        notes_col_idx = len(headers)
        headers.append(notes_col_name)
        print(f"   Adding '{notes_col_name}' column at index {notes_col_idx}")

    # Process rows
    import gspread

    cells_to_update = []
    changes = 0
    notes_added = 0

    for row_idx, row in enumerate(rows):
        # Extend row if needed for notes column
        while len(row) <= notes_col_idx:
            row.append("")

        row_notes = []

        for col_name, col_idx in col_indices.items():
            if col_idx >= len(row):
                continue

            original = row[col_idx]
            standardized, note = standardize_value(original)

            if standardized != original:
                sheet_row = row_idx + 2  # +1 for 0-index, +1 for header
                sheet_col = col_idx + 1  # +1 for 0-index
                cells_to_update.append(gspread.Cell(sheet_row, sheet_col, standardized))
                changes += 1

            if note:
                row_notes.append(f"{col_name}={note}")

        if row_notes:
            # Merge with any existing notes
            existing_notes = row[notes_col_idx].strip() if notes_col_idx < len(row) else ""
            new_notes = " | ".join(row_notes)
            if existing_notes:
                # Replace old notes entirely (re-running the script)
                combined = new_notes
            else:
                combined = new_notes
            sheet_row = row_idx + 2
            sheet_col = notes_col_idx + 1
            cells_to_update.append(gspread.Cell(sheet_row, sheet_col, combined))
            notes_added += 1

    print(f"\n📊 Summary:")
    print(f"   {changes} cells to standardize to Yes/No")
    print(f"   {notes_added} rows will have descriptive notes preserved")

    if not cells_to_update:
        print("   ✅ All values already standardized!")
        return

    # Add header for notes column if new
    if notes_col_name not in all_values[0]:
        cells_to_update.append(gspread.Cell(1, notes_col_idx + 1, notes_col_name))

    print(f"\n📝 Updating {len(cells_to_update)} cells...")
    ws.update_cells(cells_to_update)
    print("   ✅ Done!")

    # Show sample of changes
    print("\n📋 Sample changes:")
    shown = 0
    for cell in cells_to_update:
        if cell.row > 1 and shown < 10:
            paper_id = rows[cell.row - 2][0] if cell.row - 2 < len(rows) else "?"
            col_name = headers[cell.col - 1] if cell.col - 1 < len(headers) else f"col{cell.col}"
            val_preview = cell.value[:60] if len(cell.value) > 60 else cell.value
            print(f"   Row {cell.row} ({paper_id[:35]}): {col_name} → '{val_preview}'")
            shown += 1


if __name__ == "__main__":
    main()
