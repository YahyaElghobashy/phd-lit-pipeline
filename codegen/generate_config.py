"""
Codegen — Generate config.py updates
======================================
Uses regex to update SPREADSHEET_ID and SHEET_TABS in config.py.
"""
from __future__ import annotations

import re
from pathlib import Path

from codegen.config_loader import ResearchConfig, load_config


def generate(config: ResearchConfig, config_path: str = "config.py") -> None:
    """
    Update config.py in-place:
      - Replace SPREADSHEET_ID value
      - Replace SHEET_TABS list
    """
    path = Path(config_path)
    content = path.read_text(encoding="utf-8")

    # 1. Replace SPREADSHEET_ID
    new_sid = config.google_sheets.spreadsheet_id
    content = re.sub(
        r'(SPREADSHEET_ID\s*=\s*)"[^"]*"',
        f'\\1"{new_sid}"',
        content,
    )

    # 2. Build SHEET_TABS list from extraction sections + custom sections + static tails
    tabs = [
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
    ]
    for sec in config.custom_sections:
        tabs.append(sec.id)
    tabs.extend(["GAP_TRACKER", "MASTER_VIEW", "Literature_Review_Summary"])

    tab_lines = ",\n".join(f'    "{t}"' for t in tabs)
    new_tabs_block = f"SHEET_TABS = [\n{tab_lines},\n]"

    content = re.sub(
        r'SHEET_TABS\s*=\s*\[.*?\]',
        new_tabs_block,
        content,
        flags=re.DOTALL,
    )

    path.write_text(content, encoding="utf-8")
    print(f"Updated {path.resolve()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Update config.py from research config")
    parser.add_argument("--config", default="research_config.yaml", help="Path to research_config.yaml")
    parser.add_argument("--target", default="config.py", help="Path to config.py")
    args = parser.parse_args()

    cfg = load_config(args.config)
    generate(cfg, args.target)
