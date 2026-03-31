"""
PhD Literature Discovery Pipeline — State Manager
====================================================
Tracks discovery pipeline state for stop/resume capability.
"""
from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from discovery_config import DISCOVERY_STATE_FILE


class DiscoveryState:
    """Persistent state tracker for the discovery pipeline."""

    def __init__(self, state_file: Path = DISCOVERY_STATE_FILE):
        self.state_file = state_file
        self.data = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)
        return self._fresh()

    def _fresh(self) -> dict:
        return {
            "last_run": None,
            "gaps_processed": [],        # Gap IDs whose queries have been searched
            "queries_searched": [],      # Query strings already executed
            "papers_seen": [],           # DOIs already evaluated (dedup cache)
            "papers_downloaded": {},     # paper_id -> {path, status}
            "papers_extracted": {},      # paper_id -> {json_path, status}
            "run_stats": {
                "total_gaps": 0,
                "total_queries": 0,
                "total_results": 0,
                "unique_new": 0,
                "downloaded": 0,
                "no_pdf": 0,
                "failed_download": 0,
            },
        }

    def save(self):
        self.data["last_run"] = datetime.now(timezone.utc).isoformat()
        with open(self.state_file, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ─── Gap tracking ────────────────────────────────────────

    def is_gap_processed(self, gap_id: str) -> bool:
        return gap_id in self.data["gaps_processed"]

    def mark_gap_processed(self, gap_id: str):
        if gap_id not in self.data["gaps_processed"]:
            self.data["gaps_processed"].append(gap_id)
            self.save()

    # ─── Query tracking ──────────────────────────────────────

    def is_query_searched(self, query: str) -> bool:
        return query in self.data["queries_searched"]

    def mark_query_searched(self, query: str):
        if query not in self.data["queries_searched"]:
            self.data["queries_searched"].append(query)
            self.save()

    # ─── Paper tracking ──────────────────────────────────────

    def is_paper_seen(self, doi: str) -> bool:
        return doi.lower() in [d.lower() for d in self.data["papers_seen"]]

    def mark_paper_seen(self, doi: str):
        if doi and doi not in self.data["papers_seen"]:
            self.data["papers_seen"].append(doi)

    def mark_downloaded(self, paper_id: str, path: str):
        self.data["papers_downloaded"][paper_id] = {
            "path": path,
            "status": "downloaded",
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def mark_extracted(self, paper_id: str, json_path: str):
        self.data["papers_extracted"][paper_id] = {
            "json_path": json_path,
            "status": "extracted",
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def is_downloaded(self, paper_id: str) -> bool:
        return paper_id in self.data["papers_downloaded"]

    def is_extracted(self, paper_id: str) -> bool:
        return paper_id in self.data["papers_extracted"]

    # ─── Stats ────────────────────────────────────────────────

    def update_stats(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.data["run_stats"]:
                self.data["run_stats"][k] = v
        self.save()

    def increment_stat(self, key: str, amount: int = 1):
        if key in self.data["run_stats"]:
            self.data["run_stats"][key] += amount
            self.save()

    # ─── Reset ────────────────────────────────────────────────

    def reset(self):
        self.data = self._fresh()
        self.save()

    # ─── SIGINT handler ──────────────────────────────────────

    def register_shutdown_handler(self):
        def handler(signum, frame):
            print("\n\n  ⚠️  Ctrl+C detected — saving discovery state...")
            self.save()
            stats = self.data["run_stats"]
            print(f"  💾 State saved. {stats['downloaded']} PDFs downloaded, "
                  f"{stats['unique_new']} unique papers found.")
            print(f"  📁 State file: {self.state_file}")
            print("  Re-run to resume from where you left off.\n")
            sys.exit(0)

        signal.signal(signal.SIGINT, handler)
