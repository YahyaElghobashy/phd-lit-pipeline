"""
Codegen — Generate discovery_config.py updates
================================================
Uses regex to update spreadsheet IDs, API mailto, and sheet tabs
in discovery_config.py.
"""
from __future__ import annotations

import re
from pathlib import Path

from codegen.config_loader import ResearchConfig, load_config


def generate(config: ResearchConfig, config_path: str = "discovery_config.py") -> None:
    """
    Update discovery_config.py in-place:
      - Replace ORIGINAL_SPREADSHEET_ID
      - Replace AUTO_SPREADSHEET_ID
      - Replace API_MAILTO
      - Replace AUTO_SHEET_TABS list
    """
    path = Path(config_path)
    content = path.read_text(encoding="utf-8")

    # 1. ORIGINAL_SPREADSHEET_ID
    content = re.sub(
        r'(ORIGINAL_SPREADSHEET_ID\s*=\s*)"[^"]*"',
        f'\\1"{config.google_sheets.spreadsheet_id}"',
        content,
    )

    # 2. AUTO_SPREADSHEET_ID
    content = re.sub(
        r'(AUTO_SPREADSHEET_ID\s*=\s*)"[^"]*"',
        f'\\1"{config.google_sheets.auto_spreadsheet_id}"',
        content,
    )

    # 3. API_MAILTO
    content = re.sub(
        r'(API_MAILTO\s*=\s*)"[^"]*"',
        f'\\1"{config.api.mailto}"',
        content,
    )

    # 4. AUTO_SHEET_TABS list
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
    tabs.extend(["MASTER_VIEW", "Literature_Review_Summary"])

    tab_lines = ",\n".join(f'    "{t}"' for t in tabs)
    new_tabs_block = f"AUTO_SHEET_TABS = [\n{tab_lines},\n]"

    content = re.sub(
        r'AUTO_SHEET_TABS\s*=\s*\[.*?\]',
        new_tabs_block,
        content,
        flags=re.DOTALL,
    )

    path.write_text(content, encoding="utf-8")
    print(f"Updated {path.resolve()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Update discovery_config.py from research config")
    parser.add_argument("--config", default="research_config.yaml", help="Path to research_config.yaml")
    parser.add_argument("--target", default="discovery_config.py", help="Path to discovery_config.py")
    args = parser.parse_args()

    cfg = load_config(args.config)
    generate(cfg, args.target)
