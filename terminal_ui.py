"""
PhD Literature Extraction Pipeline — Terminal UI
==================================================
Rich terminal display for pipeline progress.
"""
from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.text import Text
from rich import box


console = Console()


class PipelineDisplay:
    """Rich terminal UI for the extraction pipeline."""

    def __init__(self):
        self._start_time = time.time()

    def show_header(self, root: Path, total_pdfs: int, already_done: int, skip_sheets: bool = False):
        """Display pipeline header banner."""
        content = Text()
        content.append("PhD LITERATURE EXTRACTION PIPELINE\n", style="bold cyan")
        content.append("PhD Research Literature Review Pipeline\n\n", style="dim")
        content.append(f"📂 Folder: {root}\n")
        content.append(f"📄 PDFs found: {total_pdfs} unprocessed\n")
        content.append(f"✅ Already done: {already_done}\n")
        content.append(f"📋 Queue: {total_pdfs} papers\n")
        if skip_sheets:
            content.append("⚠️  Google Sheets: SKIPPED\n", style="yellow")

        console.print(Panel(content, border_style="cyan", box=box.DOUBLE))
        console.print()

    def show_paper_start(self, index: int, total: int, filename: str, subfolder: str = ""):
        """Show which paper is being processed."""
        console.rule(f"[bold cyan]Paper {index}/{total}", style="cyan")
        console.print(f"  📄 {filename}", style="bold")
        if subfolder and subfolder != ".":
            console.print(f"  📁 {subfolder}", style="dim")
        console.print()

    def create_extraction_spinner(self) -> tuple:
        """Create a progress spinner for extraction. Returns (progress, task_id)."""
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        )
        task = progress.add_task("Extracting via Claude Code...", total=None)
        return progress, task

    def show_extraction_result(self, success: bool, paper_id: str, extraction: dict | None):
        """Show extraction result."""
        if not success or extraction is None:
            console.print("  ❌ Extraction FAILED", style="bold red")
            return

        rel = extraction.get("9_RELEVANCE", {})
        score = rel.get("Weighted_Score", "?")
        tier = rel.get("Relevance_Tier", "?")
        theme = extraction.get("10_CLASSIFICATION", {}).get("Primary_Theme", "?")
        assignment = extraction.get("10_CLASSIFICATION", {}).get("Paper_Assignment", "?")

        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()
        table.add_row("Paper ID", paper_id)
        table.add_row("Relevance", f"{score} ({tier})")
        table.add_row("Theme", theme)
        table.add_row("Assignment", assignment)

        # Board chars summary
        board = extraction.get("12_BOARD_CHARS", {})
        examined = sum(1 for k, v in board.items() if v == "Yes" and k.endswith("_Examined"))
        table.add_row("Board Chars", f"{examined}/18 examined")

        console.print(Panel(table, title="[green]Extraction Complete", border_style="green"))

    def show_population_progress(self, tab_name: str, tab_index: int, total_tabs: int, success: bool):
        """Show Sheets population progress for each tab."""
        icon = "✅" if success else "❌"
        console.print(f"  {icon} [{tab_index}/{total_tabs}] {tab_name}")

    def show_gap_update(self, summary: dict, warnings: list[str]):
        """Show gap tracker update summary."""
        new = summary.get("new", 0)
        updated = summary.get("updated", 0)
        if new or updated:
            console.print(f"  📊 Gaps: {new} new, {updated} updated")
        for w in warnings:
            console.print(f"  ⚠️  {w}", style="yellow")

    def show_paper_complete(self, index: int, total: int, paper_id: str, renamed_to: str | None = None):
        """One-line completion summary."""
        if renamed_to:
            console.print(f"  📝 Renamed → {Path(renamed_to).name}", style="dim")
        console.print()

    def show_paper_failed(self, index: int, total: int, filename: str, reason: str):
        """Show paper failure."""
        console.print(f"  ❌ [{index}/{total}] FAILED: {filename}", style="bold red")
        console.print(f"     Reason: {reason}", style="red")
        console.print()

    def show_run_summary(self, stats: dict, gap_summary: dict, elapsed: float,
                         report_path: Path | None = None):
        """Final pipeline run summary."""
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        content = Text()
        content.append("PIPELINE COMPLETE\n\n", style="bold green")

        completed = stats.get("completed", 0)
        failed = stats.get("failed", 0)
        content.append(f"Papers processed: {completed}\n")
        content.append(f"Papers failed: {failed}\n")
        content.append(f"Time elapsed: {mins}m {secs}s\n")
        if completed > 0:
            avg = elapsed / completed
            content.append(f"Avg time per paper: {int(avg // 60)}m {int(avg % 60)}s\n")
        content.append("\n")

        # By relevance
        by_rel = stats.get("by_relevance", {})
        if by_rel:
            content.append("BY RELEVANCE: ", style="bold")
            parts = [f"{k}={v}" for k, v in sorted(by_rel.items())]
            content.append(", ".join(parts) + "\n")

        # By theme
        by_theme = stats.get("by_theme", {})
        if by_theme:
            content.append("BY THEME: ", style="bold")
            parts = [f"{k}={v}" for k, v in sorted(by_theme.items())]
            content.append(", ".join(parts) + "\n")

        content.append("\n")

        # Gap summary
        total_gaps = gap_summary.get("total", 0)
        unresolved = gap_summary.get("unresolved", 0)
        content.append(f"GAPS: {total_gaps} total ({unresolved} unresolved)\n", style="bold")
        by_cov = gap_summary.get("by_coverage", {})
        if by_cov:
            for level in ["NOT ADDRESSED", "PARTIALLY ADDRESSED", "SUBSTANTIALLY COVERED", "DIRECTLY TACKLED"]:
                count = by_cov.get(level, 0)
                if count:
                    content.append(f"  {level}: {count}\n")

        if report_path:
            content.append(f"\n📋 Run report: {report_path}\n", style="bold cyan")

        console.print(Panel(content, border_style="green", box=box.DOUBLE))

    def show_dry_run(self, root: Path, pdfs: list[Path], already_done: int):
        """Display dry-run summary with Rich formatting."""
        self.show_header(root, len(pdfs), already_done)

        if not pdfs:
            console.print("  No unprocessed PDFs found. Nothing to do.\n")
            return

        table = Table(title="Paper Queue", box=box.ROUNDED, show_lines=False)
        table.add_column("#", style="dim", width=4)
        table.add_column("Filename", style="bold")
        table.add_column("Subfolder", style="dim")

        for i, pdf in enumerate(pdfs, 1):
            rel_folder = pdf.parent.relative_to(root) if pdf.parent != root else Path(".")
            table.add_row(str(i), pdf.name, str(rel_folder))

        console.print(table)
        console.print(f"\n  Total: {len(pdfs)} papers to process\n")

    def status_callback(self, msg: str):
        """Generic status callback for use by other modules."""
        console.print(f"     → {msg}")
