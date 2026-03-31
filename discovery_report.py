"""
PhD Literature Discovery Pipeline — Run Reports
==================================================
Generates comprehensive JSON run reports and provides a --status
command with Rich terminal display for reviewing pipeline state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from discovery_config import (
    DISCOVERY_REPORTS_DIR,
    DISCOVERIES_DIR,
    PDF_DOWNLOAD_DIR,
    AUTO_SPREADSHEET_ID,
)

console = Console()


# ─── DISCOVERY RUN REPORT ─────────────────────────────────

class DiscoveryRunReport:
    """
    Collects pipeline step results during a --run invocation
    and writes a timestamped JSON to reports/.

    Pattern matches main.py's RunReport but captures discovery-specific data:
    gaps, queries, search results, dedup, downloads, extractions, novelty.
    """

    def __init__(self, args: dict | None = None):
        self.run_id = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.args = args or {}

        # Per-step data
        self.gaps: list[dict] = []
        self.queries: list[dict] = []
        self.search_results: list[dict] = []
        self.duplicates_filtered: int = 0
        self.new_papers: list[dict] = []
        self.downloads: list[dict] = []
        self.extractions: list[dict] = []
        self.novelty: list[dict] = []

        # Step timings
        self._step_timings: dict[str, float] = {}
        self._step_start: float | None = None

    # ─── Step timing helpers ──────────────────────────────

    def start_step(self, step_name: str):
        """Mark the start of a pipeline step."""
        import time
        self._step_start = time.time()
        self._step_timings[step_name] = 0

    def end_step(self, step_name: str):
        """Mark the end of a pipeline step."""
        import time
        if self._step_start is not None:
            self._step_timings[step_name] = round(time.time() - self._step_start, 1)
            self._step_start = None

    # ─── Data collectors ──────────────────────────────────

    def record_gaps(self, gaps: list[dict]):
        """Record gaps found in Step 1."""
        self.gaps = [
            {"gap_id": g.get("gap_id", ""), "gap_type": g.get("gap_type", ""), "statement": g.get("gap_statement", "")[:100]}
            for g in gaps
        ]

    def record_queries(self, query_results: list[dict]):
        """Record generated queries from Step 2."""
        for qr in query_results:
            gap_id = qr.get("gap_id", "")
            for q in qr.get("queries", []):
                self.queries.append({
                    "gap_id": gap_id,
                    "query": q.get("query", ""),
                    "angle": q.get("angle", ""),
                })

    def record_search(self, papers: list[dict]):
        """Record raw search results from Step 3."""
        self.search_results = [
            {
                "title": p.get("title", "")[:80],
                "DOI": p.get("DOI", ""),
                "Year": p.get("Year", ""),
                "is_oa": p.get("is_oa", "No"),
                "Citation_Count": p.get("Citation_Count", "0"),
            }
            for p in papers
        ]

    def record_dedup(self, new_papers: list[dict], n_duplicates: int):
        """Record dedup results from Step 4."""
        self.duplicates_filtered = n_duplicates
        self.new_papers = [
            {
                "title": p.get("title", "")[:80],
                "DOI": p.get("DOI", ""),
                "is_oa": p.get("is_oa", "No"),
            }
            for p in new_papers
        ]

    def record_download(self, paper_id: str, title: str, status: str, path: str = ""):
        """Record a single download result."""
        self.downloads.append({
            "paper_id": paper_id,
            "title": title[:80],
            "status": status,  # "downloaded", "no_pdf", "failed"
            "path": path,
        })

    def record_extraction(self, paper_id: str, status: str, relevance_tier: str = "",
                          relevance_score: str = ""):
        """Record a single extraction result."""
        self.extractions.append({
            "paper_id": paper_id,
            "status": status,  # "extracted", "failed"
            "relevance_tier": relevance_tier,
            "relevance_score": relevance_score,
        })

    def record_novelty(self, paper_id: str, assessments: list[dict]):
        """Record novelty assessment results for one paper."""
        summary = {"paper_id": paper_id, "total_gaps": len(assessments)}
        # Count by impact level
        for level in ["NOT ADDRESSED", "PARTIALLY ADDRESSED", "SUBSTANTIALLY COVERED", "DIRECTLY TACKLED"]:
            summary[level.lower().replace(" ", "_")] = sum(
                1 for a in assessments if a.get("impact_level", "") == level
            )
        # Count gaps still valid
        summary["gaps_still_valid"] = sum(1 for a in assessments if a.get("gap_still_valid") == "Yes")
        summary["gaps_partially_valid"] = sum(1 for a in assessments if a.get("gap_still_valid") == "Partially")
        summary["gaps_no_longer_valid"] = sum(1 for a in assessments if a.get("gap_still_valid") == "No")
        self.novelty.append(summary)

    # ─── Save report ──────────────────────────────────────

    def save(self) -> Path:
        """Write the report JSON to reports/ directory."""
        DISCOVERY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        started = datetime.fromisoformat(self.started_at)
        finished = datetime.now(timezone.utc)

        report = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": finished.isoformat(),
            "duration_seconds": round((finished - started).total_seconds(), 1),
            "args": self.args,
            "summary": {
                "gaps_processed": len(self.gaps),
                "queries_generated": len(self.queries),
                "search_results": len(self.search_results),
                "duplicates_filtered": self.duplicates_filtered,
                "new_papers": len(self.new_papers),
                "pdfs_downloaded": sum(1 for d in self.downloads if d["status"] == "downloaded"),
                "no_pdf": sum(1 for d in self.downloads if d["status"] == "no_pdf"),
                "extractions_completed": sum(1 for e in self.extractions if e["status"] == "extracted"),
                "extractions_failed": sum(1 for e in self.extractions if e["status"] == "failed"),
                "novelty_papers_assessed": len(self.novelty),
            },
            "step_timings": self._step_timings,
            "gaps": self.gaps,
            "queries": self.queries,
            "downloads": self.downloads,
            "extractions": self.extractions,
            "novelty": self.novelty,
        }

        path = DISCOVERY_REPORTS_DIR / f"discovery_{self.run_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return path


# ─── STATUS DISPLAY ────────────────────────────────────────

def show_pipeline_status():
    """
    Display comprehensive pipeline status: state, discoveries,
    downloads, extractions, and novelty coverage.
    """
    from discovery_state import DiscoveryState
    from discovery_config import DISCOVERY_STATE_FILE

    # ─── State ────────────────────────────────────────────
    state = DiscoveryState()
    stats = state.data["run_stats"]

    content = Text()
    content.append("DISCOVERY PIPELINE STATUS\n\n", style="bold magenta")

    last_run = state.data.get("last_run", "Never")
    if last_run and last_run != "Never":
        try:
            dt = datetime.fromisoformat(last_run)
            last_run = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass
    content.append(f"Last run: {last_run}\n", style="dim")
    content.append(f"State file: {DISCOVERY_STATE_FILE}\n\n", style="dim")

    # Stats table
    content.append("Run Statistics\n", style="bold cyan")
    content.append(f"  Gaps processed:      {stats.get('total_gaps', 0)}\n")
    content.append(f"  Queries executed:     {stats.get('total_queries', 0)}\n")
    content.append(f"  Total search results: {stats.get('total_results', 0)}\n")
    content.append(f"  Unique new papers:    {stats.get('unique_new', 0)}\n")
    content.append(f"  PDFs downloaded:      {stats.get('downloaded', 0)}\n")
    content.append(f"  Metadata-only:        {stats.get('no_pdf', 0)}\n")
    content.append(f"  Failed downloads:     {stats.get('failed_download', 0)}\n")

    console.print(Panel(content, border_style="magenta", box=box.DOUBLE))

    # ─── File counts ──────────────────────────────────────
    content2 = Text()
    content2.append("File Inventory\n\n", style="bold cyan")

    # Discoveries
    disc_files = list(DISCOVERIES_DIR.glob("*.json")) if DISCOVERIES_DIR.exists() else []
    extraction_files = [f for f in disc_files if "_metadata" not in f.name]
    metadata_files = [f for f in disc_files if "_metadata" in f.name]
    content2.append(f"  📁 discoveries/\n")
    content2.append(f"     Extraction JSONs:  {len(extraction_files)}\n")
    content2.append(f"     Metadata-only:     {len(metadata_files)}\n")

    # PDFs
    pdf_files = list(PDF_DOWNLOAD_DIR.glob("*.pdf")) if PDF_DOWNLOAD_DIR.exists() else []
    content2.append(f"\n  📁 Automated Extraction/\n")
    content2.append(f"     PDF files:         {len(pdf_files)}\n")
    total_size_mb = sum(f.stat().st_size for f in pdf_files) / (1024 * 1024) if pdf_files else 0
    content2.append(f"     Total size:        {total_size_mb:.1f} MB\n")

    # Reports
    report_files = list(DISCOVERY_REPORTS_DIR.glob("discovery_*.json")) if DISCOVERY_REPORTS_DIR.exists() else []
    content2.append(f"\n  📁 reports/\n")
    content2.append(f"     Discovery reports: {len(report_files)}\n")

    console.print(Panel(content2, border_style="cyan", box=box.ROUNDED))

    # ─── Resume state ────────────────────────────────────
    gaps_done = len(state.data.get("gaps_processed", []))
    queries_done = len(state.data.get("queries_searched", []))
    papers_seen = len(state.data.get("papers_seen", []))
    papers_dl = len(state.data.get("papers_downloaded", {}))
    papers_ext = len(state.data.get("papers_extracted", {}))

    content3 = Text()
    content3.append("Resume State\n\n", style="bold cyan")
    content3.append(f"  Gaps completed:       {gaps_done}\n")
    content3.append(f"  Queries completed:    {queries_done}\n")
    content3.append(f"  Papers seen (dedup):  {papers_seen}\n")
    content3.append(f"  Papers downloaded:    {papers_dl}\n")
    content3.append(f"  Papers extracted:     {papers_ext}\n")

    console.print(Panel(content3, border_style="green", box=box.ROUNDED))

    # ─── Recent reports ──────────────────────────────────
    if report_files:
        report_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        console.print("\n[bold]Recent Run Reports:[/]")
        for rf in report_files[:5]:
            try:
                with open(rf) as f:
                    rdata = json.load(f)
                dur = rdata.get("duration_seconds", 0)
                mins = int(dur // 60)
                secs = int(dur % 60)
                s = rdata.get("summary", {})
                console.print(
                    f"  📋 {rf.name}  |  "
                    f"{s.get('gaps_processed', 0)} gaps, "
                    f"{s.get('new_papers', 0)} new, "
                    f"{s.get('pdfs_downloaded', 0)} PDFs, "
                    f"{s.get('extractions_completed', 0)} extracted  |  "
                    f"{mins}m {secs}s"
                )
            except Exception:
                console.print(f"  📋 {rf.name}  [dim](unreadable)[/]")

    # ─── Extraction details table ────────────────────────
    if extraction_files:
        console.print("\n")
        table = Table(
            title="Discovered Paper Extractions",
            box=box.ROUNDED,
            show_lines=False,
            title_style="bold magenta",
            header_style="bold cyan",
        )
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Paper ID", max_width=40, overflow="fold")
        table.add_column("Relevance", width=12, justify="center")
        table.add_column("Tier", width=18)
        table.add_column("Theme", max_width=25, overflow="fold")

        for i, ef in enumerate(sorted(extraction_files), 1):
            try:
                with open(ef) as f:
                    ext = json.load(f)
                pid = ext.get("paper_id", ef.stem)
                rel = ext.get("9_RELEVANCE", {})
                cls = ext.get("10_CLASSIFICATION", {})
                table.add_row(
                    str(i),
                    pid,
                    str(rel.get("Weighted_Score", "?")),
                    rel.get("Relevance_Tier", "?"),
                    cls.get("Primary_Theme", "?"),
                )
            except Exception:
                table.add_row(str(i), ef.stem, "?", "?", "?")

        console.print(table)

    # ─── Auto sheet link ─────────────────────────────────
    if AUTO_SPREADSHEET_ID:
        console.print(
            f"\n  [bold]Auto Sheet:[/] [link=https://docs.google.com/spreadsheets/d/{AUTO_SPREADSHEET_ID}]"
            f"https://docs.google.com/spreadsheets/d/{AUTO_SPREADSHEET_ID}[/link]"
        )
    console.print()


def show_report_detail(report_path: Path):
    """Display detailed contents of a single run report."""
    with open(report_path) as f:
        report = json.load(f)

    dur = report.get("duration_seconds", 0)
    mins = int(dur // 60)
    secs = int(dur % 60)
    summary = report.get("summary", {})

    # Header
    content = Text()
    content.append(f"DISCOVERY RUN REPORT: {report.get('run_id', '?')}\n\n", style="bold magenta")
    content.append(f"Started:  {report.get('started_at', '?')}\n")
    content.append(f"Finished: {report.get('finished_at', '?')}\n")
    content.append(f"Duration: {mins}m {secs}s\n\n")

    # Args
    args = report.get("args", {})
    if args:
        content.append("Arguments\n", style="bold cyan")
        for k, v in args.items():
            content.append(f"  {k}: {v}\n")
        content.append("\n")

    # Summary
    content.append("Summary\n", style="bold cyan")
    content.append(f"  Gaps processed:        {summary.get('gaps_processed', 0)}\n")
    content.append(f"  Queries generated:     {summary.get('queries_generated', 0)}\n")
    content.append(f"  Search results:        {summary.get('search_results', 0)}\n")
    content.append(f"  Duplicates filtered:   {summary.get('duplicates_filtered', 0)}\n")
    content.append(f"  New papers:            {summary.get('new_papers', 0)}\n")
    content.append(f"  PDFs downloaded:       {summary.get('pdfs_downloaded', 0)}\n")
    content.append(f"  No PDF available:      {summary.get('no_pdf', 0)}\n")
    content.append(f"  Extractions OK:        {summary.get('extractions_completed', 0)}\n")
    content.append(f"  Extractions failed:    {summary.get('extractions_failed', 0)}\n")
    content.append(f"  Novelty assessed:      {summary.get('novelty_papers_assessed', 0)}\n")

    # Step timings
    timings = report.get("step_timings", {})
    if timings:
        content.append("\nStep Timings\n", style="bold cyan")
        for step, seconds in timings.items():
            content.append(f"  {step}: {seconds:.1f}s\n")

    console.print(Panel(content, border_style="magenta", box=box.DOUBLE))

    # Downloads table
    downloads = report.get("downloads", [])
    if downloads:
        table = Table(title="Downloads", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Paper ID", max_width=35, overflow="fold")
        table.add_column("Status", width=12)
        table.add_column("Title", max_width=50, overflow="fold")
        for d in downloads:
            style = "green" if d["status"] == "downloaded" else "yellow" if d["status"] == "no_pdf" else "red"
            table.add_row(d.get("paper_id", "?"), d["status"], d.get("title", "?"), style=style)
        console.print(table)

    # Extractions table
    extractions = report.get("extractions", [])
    if extractions:
        table = Table(title="Extractions", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Paper ID", max_width=35, overflow="fold")
        table.add_column("Status", width=12)
        table.add_column("Relevance", width=10)
        table.add_column("Tier", width=18)
        for e in extractions:
            style = "green" if e["status"] == "extracted" else "red"
            table.add_row(
                e.get("paper_id", "?"), e["status"],
                e.get("relevance_score", "?"), e.get("relevance_tier", "?"),
                style=style,
            )
        console.print(table)

    # Novelty summary
    novelty = report.get("novelty", [])
    if novelty:
        table = Table(title="Novelty Assessment", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Paper ID", max_width=35, overflow="fold")
        table.add_column("Gaps", width=6, justify="right")
        table.add_column("Not Addr", width=10, justify="right")
        table.add_column("Partial", width=10, justify="right")
        table.add_column("Subst.", width=10, justify="right")
        table.add_column("Tackled", width=10, justify="right")
        table.add_column("Still Valid", width=12, justify="right")
        for n in novelty:
            table.add_row(
                n.get("paper_id", "?"),
                str(n.get("total_gaps", 0)),
                str(n.get("not_addressed", 0)),
                str(n.get("partially_addressed", 0)),
                str(n.get("substantially_covered", 0)),
                str(n.get("directly_tackled", 0)),
                str(n.get("gaps_still_valid", 0)),
            )
        console.print(table)


def list_reports() -> list[Path]:
    """List all discovery run report files, newest first."""
    if not DISCOVERY_REPORTS_DIR.exists():
        return []
    reports = sorted(DISCOVERY_REPORTS_DIR.glob("discovery_*.json"),
                     key=lambda f: f.stat().st_mtime, reverse=True)
    return reports
