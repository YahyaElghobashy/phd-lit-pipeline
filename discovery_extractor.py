"""
PhD Literature Discovery Pipeline — Extraction & Sheet Population
===================================================================
Integrates Claude Opus 4.6 extraction for downloaded PDFs and populates
the Automated Extraction Google Sheet.

Reuses existing PaperExtractor pattern from extractor.py but:
- Saves to discoveries/ instead of extractions/
- Writes to the auto sheet (different spreadsheet ID)
- Marks Extracted_By as "Claude Opus 4.6 (Auto-Discovery)"
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich import box

from extractor import PaperExtractor
from populator import SheetPopulator, authenticate, retry_on_api_error
from schemas import EXTRACTION_SECTIONS, validate_extraction
from discovery_config import (
    AUTO_SPREADSHEET_ID,
    DISCOVERIES_DIR,
)
from config import SHEETS_WRITE_DELAY

console = Console()


# ─── AUTO SHEET POPULATOR ────────────────────────────────────

class AutoSheetPopulator(SheetPopulator):
    """
    SheetPopulator subclass that writes to the Automated Extraction sheet
    instead of the original sheet.
    """

    def __init__(self, sheet_id: str = "", on_status: callable = None):
        super().__init__(on_status=on_status)
        self._auto_sheet_id = sheet_id or AUTO_SPREADSHEET_ID

    def _ensure_connected(self):
        """Connect to the AUTO sheet (not the original)."""
        if self._client is None:
            self.on_status("Connecting to Auto-Discovery sheet...")
            self._client = authenticate()
            if not self._auto_sheet_id:
                raise ValueError(
                    "AUTO_SPREADSHEET_ID not set. Run `python discover.py --setup-sheet` first."
                )
            self._spreadsheet = self._client.open_by_key(self._auto_sheet_id)
            self.on_status("Connected to Auto-Discovery sheet.")


# ─── DISCOVERY EXTRACTOR ─────────────────────────────────────

class DiscoveryExtractor:
    """
    Manages full 12-section extraction of discovered PDFs.

    Uses the existing PaperExtractor for Claude CLI interaction,
    but saves to discoveries/ and populates the auto sheet.
    """

    def __init__(self, auto_sheet_id: str = ""):
        self._extractor = PaperExtractor()
        self._populator = AutoSheetPopulator(
            sheet_id=auto_sheet_id,
            on_status=lambda msg: console.print(f"  [dim]{msg}[/dim]"),
        )
        DISCOVERIES_DIR.mkdir(parents=True, exist_ok=True)

    def extract_and_populate(
        self,
        pdf_path: Path,
        paper_metadata: dict,
        paper_index: int = 1,
        total_papers: int = 1,
    ) -> dict | None:
        """
        Extract structured data from a PDF and populate the auto sheet.

        Args:
            pdf_path: Path to the downloaded PDF
            paper_metadata: API metadata dict (from api_clients)
            paper_index: 1-based index in current batch
            total_papers: Total papers in batch

        Returns:
            Extraction dict or None on failure
        """
        title = paper_metadata.get("title", "")[:50]
        paper_id = paper_metadata.get("paper_id", "unknown")

        console.print(f"\n  [bold cyan]Extracting: {title}...[/]")

        # Step 1: Run extraction via Claude Opus 4.6
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Extracting {paper_id}...", total=None)

            def on_status(msg):
                progress.update(task, description=msg)

            extraction = self._extractor.extract(
                pdf_path=pdf_path,
                gap_state=[],  # No gap state for discovery extractions
                paper_index=paper_index,
                total_papers=total_papers,
                on_status=on_status,
            )

        if extraction is None:
            console.print(f"  [red]Extraction failed for {paper_id}[/]")
            if self._extractor.last_failure_info:
                reason = self._extractor.last_failure_info.get("reason", "Unknown")
                console.print(f"  [dim]Reason: {reason}[/dim]")
            return None

        # Step 2: Override metadata with auto-discovery markers
        pid = extraction.get("paper_id", paper_id)
        if "1_IDENTIFICATION" in extraction:
            ident = extraction["1_IDENTIFICATION"]
            ident["Extracted_By"] = "Claude Opus 4.6 (Auto-Discovery)"
            ident["Date_Extracted"] = datetime.now().strftime("%Y-%m-%d")
            # Fill in API metadata if extraction left fields empty
            if not ident.get("DOI") and paper_metadata.get("DOI"):
                ident["DOI"] = paper_metadata["DOI"]
            if not ident.get("Citation_Count") and paper_metadata.get("Citation_Count"):
                ident["Citation_Count"] = paper_metadata["Citation_Count"]
            if not ident.get("Search_Query_Source") and paper_metadata.get("Search_Query_Source"):
                ident["Search_Query_Source"] = paper_metadata["Search_Query_Source"]

        # Step 3: Save extraction JSON to discoveries/
        json_path = self._save_discovery(extraction, pid)
        extraction["_extraction_file"] = str(json_path)
        console.print(f"  [green]✓ Saved: {json_path.name}[/]")

        # Step 4: Populate auto sheet
        console.print(f"  [blue]Populating Auto-Discovery sheet...[/]")
        try:
            success = self._populator.populate_paper(pid, extraction)
            if success:
                console.print(f"  [green]✓ All 12 tabs populated[/]")
            else:
                console.print(f"  [yellow]⚠ Some tabs failed to populate[/]")
        except Exception as e:
            console.print(f"  [red]Sheet population error: {e}[/]")

        # Show relevance score
        rel = extraction.get("9_RELEVANCE", {})
        score = rel.get("Weighted_Score", "?")
        tier = rel.get("Relevance_Tier", "?")
        console.print(f"  [bold]Relevance: {score} ({tier})[/]")

        return extraction

    def extract_from_text(
        self,
        text: str,
        paper_metadata: dict,
        paper_index: int = 1,
        total_papers: int = 1,
    ) -> dict | None:
        """
        Extract structured data from full text (not a PDF).

        Writes text to a temporary file, then passes it to the standard
        extraction pipeline — Claude's Read tool handles .txt files just fine.
        Cleans up the temp file after extraction.

        Args:
            text: Full text of the paper
            paper_metadata: API metadata dict
            paper_index: 1-based index in current batch
            total_papers: Total papers in batch

        Returns:
            Extraction dict or None on failure
        """
        paper_id = paper_metadata.get("paper_id", "unknown")
        safe_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in paper_id)
        text_path = DISCOVERIES_DIR / f"{safe_id}_fulltext.txt"

        try:
            # Write full text to temp file
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(text)

            console.print(f"  [dim]Wrote {len(text):,} chars to {text_path.name}[/]")

            # Run standard extraction on the text file
            return self.extract_and_populate(
                pdf_path=text_path,
                paper_metadata=paper_metadata,
                paper_index=paper_index,
                total_papers=total_papers,
            )
        finally:
            # Clean up temp file
            if text_path.exists():
                text_path.unlink()

    def _save_discovery(self, extraction: dict, paper_id: str) -> Path:
        """Save extraction JSON to discoveries/ directory."""
        safe_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in paper_id)
        filepath = DISCOVERIES_DIR / f"{safe_id}.json"

        counter = 2
        while filepath.exists():
            filepath = DISCOVERIES_DIR / f"{safe_id}_{counter}.json"
            counter += 1

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(extraction, f, indent=2, ensure_ascii=False)

        return filepath

    def extract_batch(
        self,
        papers_with_paths: list[tuple[dict, Path]],
    ) -> dict:
        """
        Extract and populate a batch of papers.

        Args:
            papers_with_paths: List of (paper_metadata, pdf_path) tuples

        Returns:
            {"extracted": N, "failed": N, "extractions": [dict, ...]}
        """
        results = {"extracted": 0, "failed": 0, "extractions": []}
        total = len(papers_with_paths)

        for i, (paper, pdf_path) in enumerate(papers_with_paths, 1):
            console.rule(f"[bold cyan]Paper {i}/{total}", style="cyan")
            console.print(f"  📄 {pdf_path.name}")
            console.print(f"  📝 {paper.get('title', '')[:60]}...")
            console.print()

            extraction = self.extract_and_populate(
                pdf_path=pdf_path,
                paper_metadata=paper,
                paper_index=i,
                total_papers=total,
            )

            if extraction:
                results["extracted"] += 1
                results["extractions"].append(extraction)
            else:
                results["failed"] += 1

        return results


def show_extraction_summary(results: dict):
    """Display extraction batch summary."""
    content = Text()
    content.append("EXTRACTION SUMMARY\n\n", style="bold green")
    content.append(f"✅ Extracted: {results['extracted']}\n")
    content.append(f"❌ Failed: {results['failed']}\n")

    if results["extractions"]:
        content.append("\nRelevance breakdown:\n")
        tiers = {}
        for ext in results["extractions"]:
            tier = ext.get("9_RELEVANCE", {}).get("Relevance_Tier", "Unknown")
            tiers[tier] = tiers.get(tier, 0) + 1
        for tier, count in sorted(tiers.items()):
            content.append(f"  {tier}: {count}\n")

    console.print(Panel(content, border_style="green", box=box.ROUNDED))
