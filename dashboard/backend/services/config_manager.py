"""
Dashboard — Config Manager Service
Reads/writes research_config.yaml and manages local pipeline files.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = PIPELINE_DIR / "research_config.yaml"

# Add pipeline dir so we can import codegen, config, etc.
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))


def get_config() -> dict:
    """Read research_config.yaml and return as dict."""
    if not CONFIG_PATH.exists():
        return {"error": "research_config.yaml not found", "path": str(CONFIG_PATH)}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def update_config(data: dict) -> dict:
    """Merge updates into research_config.yaml and save."""
    current = get_config()
    if "error" in current:
        # No existing config — use data as the full config
        current = data
    else:
        # Deep merge top-level keys
        current.update(data)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return current


def regenerate_files() -> dict:
    """Run codegen generators to regenerate pipeline files from config."""
    try:
        from codegen.config_loader import load_config

        config = load_config(CONFIG_PATH)
        return {
            "status": "ok",
            "message": "Config validated successfully",
            "project_title": config.project.title,
            "papers_count": len(config.papers),
            "sections_count": len(config.custom_sections),
        }
    except FileNotFoundError:
        return {"status": "error", "message": "research_config.yaml not found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_local_files() -> list[dict]:
    """Browse extractions/, discoveries/, reports/ directories."""
    results: list[dict] = []
    categories = ["extractions", "discoveries", "reports"]

    for category in categories:
        dir_path = PIPELINE_DIR / category
        if not dir_path.exists():
            continue
        for file_path in sorted(dir_path.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(PIPELINE_DIR)
                stat = file_path.stat()
                results.append({
                    "path": str(rel),
                    "category": category,
                    "name": file_path.name,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })

    return results


def delete_file(rel_path: str) -> bool:
    """Delete a file by relative path, with path traversal protection."""
    # Resolve the target path
    target = (PIPELINE_DIR / rel_path).resolve()

    # Path traversal protection: must be within PIPELINE_DIR
    if not str(target).startswith(str(PIPELINE_DIR.resolve())):
        raise ValueError("Path traversal detected — access denied")

    # Only allow deletions from safe directories
    safe_dirs = ["extractions", "discoveries", "reports"]
    rel_resolved = target.relative_to(PIPELINE_DIR.resolve())
    top_dir = rel_resolved.parts[0] if rel_resolved.parts else ""
    if top_dir not in safe_dirs:
        raise ValueError(f"Deletion only allowed in: {', '.join(safe_dirs)}")

    if target.exists() and target.is_file():
        target.unlink()
        return True
    return False


def get_sheets_info() -> list[dict]:
    """Get tab names + row counts from the Google Sheet."""
    try:
        import gspread
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        from config import SPREADSHEET_ID, SCOPES, TOKEN_FILE

        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds.expired:
            creds.refresh(Request())

        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)

        tabs: list[dict] = []
        for ws in sh.worksheets():
            tabs.append({
                "title": ws.title,
                "row_count": ws.row_count,
                "col_count": ws.col_count,
            })

        return tabs
    except Exception as e:
        return [{"error": str(e)}]
