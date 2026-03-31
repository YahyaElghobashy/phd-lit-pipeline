"""
Dashboard — Drive Manager Service
Google Drive folder operations for the pipeline.
"""
from __future__ import annotations

import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent

if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))


def _get_drive_service():
    """Authenticate and return a Google Drive service via gspread's credentials."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    from config import SCOPES, TOKEN_FILE

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired:
        creds.refresh(Request())

    return build("drive", "v3", credentials=creds)


def list_folders() -> list[dict]:
    """List folders in the PhD Literature Review Drive folder."""
    try:
        service = _get_drive_service()
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name, createdTime, modifiedTime)",
            orderBy="name",
            pageSize=100,
        ).execute()

        folders = results.get("files", [])
        return [
            {
                "id": f["id"],
                "name": f["name"],
                "created": f.get("createdTime", ""),
                "modified": f.get("modifiedTime", ""),
            }
            for f in folders
        ]
    except Exception as e:
        return [{"error": str(e)}]


def create_folder_structure(project_name: str) -> dict:
    """Create a standard folder structure for a new research project in Drive."""
    try:
        service = _get_drive_service()

        # Create the main project folder
        folder_meta = {
            "name": project_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        main_folder = service.files().create(
            body=folder_meta, fields="id, name"
        ).execute()
        main_id = main_folder["id"]

        # Create subfolders
        subfolders = ["PDFs", "Extractions", "Reports", "Notes"]
        created = [{"name": project_name, "id": main_id, "type": "root"}]

        for sub in subfolders:
            sub_meta = {
                "name": sub,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [main_id],
            }
            sub_folder = service.files().create(
                body=sub_meta, fields="id, name"
            ).execute()
            created.append({"name": sub, "id": sub_folder["id"], "type": "subfolder"})

        return {
            "status": "ok",
            "project_name": project_name,
            "folders_created": len(created),
            "folders": created,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
