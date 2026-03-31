"""
PhD Literature Extraction Pipeline — State Manager
====================================================
Tracks per-paper status in pipeline_state.json for stop/resume.
"""
from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import STATE_FILE, DATE_FORMAT


class PipelineState:
    """Persistent state tracker for the extraction pipeline."""

    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.data = self._load()

    # ─── PERSISTENCE ────────────────────────────────────────

    def _load(self) -> dict:
        """Load existing state or create fresh."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)
        return self._fresh_state()

    def _fresh_state(self) -> dict:
        return {
            "last_run": None,
            "total_papers_processed": 0,
            "papers": {},
            "gap_tracker": [],
            "stats": {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "skipped": 0,
                "by_relevance": {},
                "by_theme": {},
            },
        }

    def save(self):
        """Write state to disk."""
        self.data["last_run"] = datetime.now(timezone.utc).isoformat()
        with open(self.state_file, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ─── PAPER STATUS ───────────────────────────────────────

    def _paper_key(self, pdf_path: str | Path) -> str:
        """Normalize path to string key."""
        return str(Path(pdf_path).resolve())

    def get_status(self, pdf_path: str | Path) -> str | None:
        """Get current status of a paper."""
        key = self._paper_key(pdf_path)
        paper = self.data["papers"].get(key)
        return paper["status"] if paper else None

    def get_paper(self, pdf_path: str | Path) -> dict | None:
        """Get full paper record."""
        key = self._paper_key(pdf_path)
        return self.data["papers"].get(key)

    def _ensure_paper(self, pdf_path: str | Path) -> dict:
        """Get or create paper record."""
        key = self._paper_key(pdf_path)
        if key not in self.data["papers"]:
            self.data["papers"][key] = {
                "status": "pending",
                "paper_id": None,
                "original_filename": Path(pdf_path).name,
                "extraction_file": None,
                "started_at": None,
                "extracted_at": None,
                "populated_at": None,
                "completed_at": None,
                "renamed_to": None,
                "duration_seconds": None,
                "error": None,
                "retry_count": 0,
            }
        return self.data["papers"][key]

    def mark_extracting(self, pdf_path: str | Path):
        """Mark paper as currently being extracted."""
        paper = self._ensure_paper(pdf_path)
        paper["status"] = "extracting"
        paper["started_at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def mark_extracted(self, pdf_path: str | Path, extraction_file: str, paper_id: str):
        """Mark paper as extracted (JSON saved locally)."""
        paper = self._ensure_paper(pdf_path)
        paper["status"] = "extracted"
        paper["extraction_file"] = str(extraction_file)
        paper["paper_id"] = paper_id
        paper["extracted_at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def mark_populating(self, pdf_path: str | Path):
        """Mark paper as being populated to Google Sheets."""
        paper = self._ensure_paper(pdf_path)
        paper["status"] = "populating"
        self.save()

    def mark_populated(self, pdf_path: str | Path):
        """Mark paper as populated in Google Sheets."""
        paper = self._ensure_paper(pdf_path)
        paper["status"] = "populated"
        paper["populated_at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def mark_complete(self, pdf_path: str | Path, renamed_to: str | None = None):
        """Mark paper as fully complete."""
        paper = self._ensure_paper(pdf_path)
        paper["status"] = "complete"
        paper["completed_at"] = datetime.now(timezone.utc).isoformat()
        if renamed_to:
            paper["renamed_to"] = str(renamed_to)
        # Calculate duration
        if paper.get("started_at"):
            start = datetime.fromisoformat(paper["started_at"])
            end = datetime.now(timezone.utc)
            paper["duration_seconds"] = int((end - start).total_seconds())
        self.data["total_papers_processed"] = sum(
            1 for p in self.data["papers"].values() if p["status"] == "complete"
        )
        self.save()

    def mark_failed(self, pdf_path: str | Path, reason: str, error: str = ""):
        """Mark paper as failed."""
        paper = self._ensure_paper(pdf_path)
        paper["status"] = f"failed_{reason}"
        paper["error"] = error[:500] if error else reason
        paper["retry_count"] = paper.get("retry_count", 0) + 1
        self.save()

    # ─── QUERIES ────────────────────────────────────────────

    def is_complete(self, pdf_path: str | Path) -> bool:
        """Check if a paper is already fully processed."""
        return self.get_status(pdf_path) == "complete"

    def needs_population(self, pdf_path: str | Path) -> bool:
        """Check if paper was extracted but not yet populated."""
        status = self.get_status(pdf_path)
        return status in ("extracted", "extracted_not_populated")

    def get_completed_count(self) -> int:
        return sum(1 for p in self.data["papers"].values() if p["status"] == "complete")

    def get_failed_count(self) -> int:
        return sum(1 for p in self.data["papers"].values() if p["status"].startswith("failed"))

    # ─── GAP TRACKER ────────────────────────────────────────

    def get_gaps(self) -> list[dict]:
        """Get current gap tracker state."""
        return self.data.get("gap_tracker", [])

    def update_gaps(self, gaps: list[dict]):
        """Replace gap tracker with updated list."""
        self.data["gap_tracker"] = gaps
        self.save()

    def get_unresolved_gaps(self) -> list[dict]:
        """Get gaps that haven't been directly tackled."""
        return [
            g for g in self.get_gaps()
            if g.get("coverage_level", "NOT ADDRESSED") != "DIRECTLY TACKLED"
        ]

    # ─── STATS ──────────────────────────────────────────────

    def update_stats(self, paper_id: str, relevance_tier: str, theme: str):
        """Update running stats after a paper completes."""
        stats = self.data["stats"]
        stats["completed"] = self.get_completed_count()
        stats["failed"] = self.get_failed_count()

        # By relevance
        stats.setdefault("by_relevance", {})
        stats["by_relevance"][relevance_tier] = stats["by_relevance"].get(relevance_tier, 0) + 1

        # By theme
        stats.setdefault("by_theme", {})
        stats["by_theme"][theme] = stats["by_theme"].get(theme, 0) + 1

        self.save()

    # ─── SIGINT HANDLER ─────────────────────────────────────

    def register_shutdown_handler(self):
        """Register graceful Ctrl+C handler that saves state."""
        original_handler = signal.getsignal(signal.SIGINT)

        def handler(signum, frame):
            print("\n\n  ⚠️  Ctrl+C detected — saving state...")
            self.save()
            completed = self.get_completed_count()
            total = len(self.data["papers"])
            print(f"  💾 State saved. {completed}/{total} papers completed.")
            print(f"  📁 State file: {self.state_file}")
            print("  Re-run to resume from where you left off.\n")
            sys.exit(0)

        signal.signal(signal.SIGINT, handler)
