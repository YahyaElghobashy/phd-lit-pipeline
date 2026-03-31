#!/usr/bin/env python3
"""
PhD Literature Extraction Pipeline — Orchestrator
===================================================
Crawls a folder of research paper PDFs, extracts structured academic data
via Claude Code CLI, populates a Google Sheet, and tracks research gaps.

Usage:
    python main.py                    # Process all unprocessed PDFs
    python main.py --dry-run          # Scan and show queue, no processing
    python main.py --paper "Adams"    # Process a single paper by name match
    python main.py --skip-sheets      # Extract only, skip Google Sheets
    python main.py --reprocess "X"    # Re-extract a paper even if done
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config import PDF_ROOT, EXTRACTED_SUFFIX, PIPELINE_DIR, EXTRACTIONS_DIR, REPORTS_DIR
from state_manager import PipelineState
from extractor import PaperExtractor
from gap_analyzer import GapAnalyzer
from terminal_ui import PipelineDisplay, console


# ─── PDF DISCOVERY ──────────────────────────────────────────

def discover_pdfs(root: Path) -> list[Path]:
    """
    Recursively find all PDF files under root at any depth.
    Skips files ending with extracted suffix and files inside pipeline dir.
    """
    pdfs = []
    pipeline_dir = PIPELINE_DIR.resolve()

    for pdf in root.rglob("*"):
        if not pdf.is_file():
            continue
        if pdf.suffix.lower() != ".pdf":
            continue
        if pdf.name.endswith(EXTRACTED_SUFFIX):
            continue
        try:
            pdf.resolve().relative_to(pipeline_dir)
            continue
        except ValueError:
            pass
        pdfs.append(pdf)

    pdfs.sort(key=lambda p: (p.parent.name.lower(), p.name.lower()))
    return pdfs


def count_extracted(root: Path) -> int:
    """Count already-processed PDFs."""
    count = 0
    pipeline_dir = PIPELINE_DIR.resolve()
    for pdf in root.rglob("*"):
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            continue
        try:
            pdf.resolve().relative_to(pipeline_dir)
            continue
        except ValueError:
            pass
        if pdf.name.endswith(EXTRACTED_SUFFIX):
            count += 1
    return count


# ─── PDF RENAMING ───────────────────────────────────────────

def rename_pdf(pdf_path: Path, extraction: dict) -> Path | None:
    """
    Rename PDF to: <Title> — YYYY-MM-DD — Extracted.pdf
    Returns new path, or None if rename fails.
    """
    try:
        # Get title from extraction
        ident = extraction.get("1_IDENTIFICATION", {})
        title = ident.get("Full_Citation_APA7", "")

        # Try to extract a short title (first 80 chars of citation)
        if title:
            # Take up to the year or first 80 chars
            short = title[:80].rstrip(". ")
        else:
            paper_id = extraction.get("paper_id", "Unknown")
            short = paper_id

        # Sanitize for filename
        safe_title = "".join(c if c.isalnum() or c in " _-,()" else " " for c in short)
        safe_title = " ".join(safe_title.split())  # collapse whitespace

        date_str = datetime.now().strftime("%Y-%m-%d")
        new_name = f"{safe_title} — {date_str} — Extracted.pdf"

        new_path = pdf_path.parent / new_name

        # Handle name collision
        counter = 2
        while new_path.exists():
            new_name = f"{safe_title} ({counter}) — {date_str} — Extracted.pdf"
            new_path = pdf_path.parent / new_name
            counter += 1

        pdf_path.rename(new_path)
        return new_path
    except Exception as e:
        console.print(f"  ⚠️  Rename failed: {e}", style="yellow")
        return None


# ─── ARGUMENT PARSING ──────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="PhD Literature Extraction Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Scan and display queue without processing")
    parser.add_argument("--paper", type=str, default=None, help="Process a single paper matching this substring")
    parser.add_argument("--skip-sheets", action="store_true", help="Extract only, skip Google Sheets population")
    parser.add_argument("--reprocess", type=str, default=None, help="Re-extract a specific paper even if done")
    parser.add_argument("--backfill-summary", action="store_true", help="Backfill Literature_Review_Summary for all extracted papers")
    parser.add_argument("--backfill-abstracts", action="store_true", help="Extract verbatim abstracts from PDFs and update Google Sheet")
    return parser.parse_args()


# ─── RUN REPORT ────────────────────────────────────────────

class RunReport:
    """Collects per-paper results and writes a timestamped JSON report."""

    def __init__(self, args):
        self.run_id = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.args = {
            "paper": args.paper,
            "skip_sheets": args.skip_sheets,
            "reprocess": args.reprocess,
            "dry_run": args.dry_run,
        }
        self.papers: list[dict] = []
        self.skipped: int = 0

    def add_success(self, filename: str, subfolder: str, paper_id: str,
                    duration_seconds: float, extraction: dict):
        rel = extraction.get("9_RELEVANCE", {})
        cls = extraction.get("10_CLASSIFICATION", {})
        self.papers.append({
            "filename": filename,
            "subfolder": subfolder,
            "paper_id": paper_id,
            "status": "complete",
            "duration_seconds": round(duration_seconds, 1),
            "relevance_tier": rel.get("Relevance_Tier", ""),
            "theme": cls.get("Primary_Theme", ""),
        })

    def add_failure(self, filename: str, subfolder: str, duration_seconds: float,
                    failure_stage: str, failure_reason: str,
                    error_details: str = "", attempts: list[dict] | None = None):
        self.papers.append({
            "filename": filename,
            "subfolder": subfolder,
            "paper_id": None,
            "status": "failed",
            "failure_stage": failure_stage,
            "failure_reason": failure_reason,
            "error_details": error_details[:500],
            "duration_seconds": round(duration_seconds, 1),
            "attempt_count": len(attempts) if attempts else 1,
            "attempts": attempts or [],
        })

    def add_skip(self):
        self.skipped += 1

    def save(self) -> Path:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        started = datetime.fromisoformat(self.started_at)
        finished = datetime.now(timezone.utc)
        report = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": finished.isoformat(),
            "duration_seconds": round((finished - started).total_seconds(), 1),
            "args": self.args,
            "total_queued": len(self.papers) + self.skipped,
            "completed": sum(1 for p in self.papers if p["status"] == "complete"),
            "failed": sum(1 for p in self.papers if p["status"] == "failed"),
            "skipped": self.skipped,
            "papers": self.papers,
        }
        path = REPORTS_DIR / f"run_{self.run_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return path


# ─── BACKFILL ABSTRACTS ───────────────────────────────────

def _backfill_abstracts(display):
    """Extract verbatim abstracts from PDFs and update extraction JSONs + Google Sheet."""
    import os
    import subprocess
    from config import CLAUDE_CLI, CLAUDE_MODEL, SUMMARY_TAB

    extraction_files = sorted(EXTRACTIONS_DIR.glob("*.json"))
    if not extraction_files:
        console.print("  No extraction files found.", style="yellow")
        return

    # Find papers missing Verbatim_Abstract
    to_backfill = []
    for ext_file in extraction_files:
        with open(ext_file) as f:
            data = json.load(f)
        if data.get("Verbatim_Abstract"):
            continue
        to_backfill.append((ext_file, data))

    if not to_backfill:
        console.print("  All papers already have verbatim abstracts.", style="green")
        return

    console.print(f"  Found {len(to_backfill)} papers missing verbatim abstracts.\n")

    # Connect to Google Sheets
    from populator import SheetPopulator
    pop = SheetPopulator(on_status=display.status_callback)
    pop._ensure_connected()
    ws = pop._get_worksheet(SUMMARY_TAB)
    headers = pop._read_headers(SUMMARY_TAB)
    header_map = {h: i for i, h in enumerate(headers)}
    abstract_col = header_map.get("Abstract")
    pid_col = header_map.get("PAPER_ID")

    if abstract_col is None or pid_col is None:
        console.print("  Could not find Abstract or PAPER_ID column in sheet.", style="red")
        return

    # Build PAPER_ID → row number map from sheet
    all_pids = ws.col_values(pid_col + 1)  # 1-indexed
    pid_to_row = {}
    for row_idx, pid in enumerate(all_pids):
        if row_idx == 0:  # header
            continue
        if pid:
            pid_to_row[pid] = row_idx + 1  # 1-indexed sheet row

    # Find PDFs (already renamed with "Extracted" suffix)
    all_pdfs = list(PDF_ROOT.rglob("*.pdf"))

    succeeded = 0
    failed = 0

    for ext_file, data in to_backfill:
        paper_id = data.get("paper_id", "unknown")
        console.print(f"  [{succeeded + failed + 1}/{len(to_backfill)}] {paper_id}...", end=" ")

        # Find the corresponding PDF
        pdf_match = None
        # Try matching by paper_id parts in filename
        id_parts = paper_id.lower().replace("_", " ").split()
        for pdf in all_pdfs:
            name_lower = pdf.name.lower()
            if all(part in name_lower for part in id_parts[:2]):
                pdf_match = pdf
                break

        if not pdf_match:
            console.print("PDF not found, skipping", style="yellow")
            failed += 1
            continue

        # Send minimal prompt to Claude CLI
        prompt = (
            f'Read the PDF at "{pdf_match.resolve()}" and extract ONLY the verbatim abstract. '
            f'Return a JSON object with exactly one key: {{"Verbatim_Abstract": "<exact abstract text>"}}. '
            f'Copy the abstract word-for-word. No markdown, no explanation.'
        )
        cmd = [
            CLAUDE_CLI,
            "-p", prompt,
            "--output-format", "json",
            "--model", CLAUDE_MODEL,
            "--max-turns", "2",
            "--allowedTools", "Read",
            "--no-session-persistence",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                cwd=str(PDF_ROOT),
                env={**os.environ, "CLAUDE_CODE_HEADLESS": "1"},
            )
            if result.returncode != 0:
                console.print(f"CLI error (code {result.returncode})", style="red")
                failed += 1
                continue

            # Parse output
            output = result.stdout.strip()
            envelope = json.loads(output)
            if isinstance(envelope, dict) and "result" in envelope:
                inner = envelope["result"]
                if isinstance(inner, str):
                    inner = json.loads(inner)
            elif isinstance(envelope, dict):
                inner = envelope
            else:
                console.print("unexpected output format", style="red")
                failed += 1
                continue

            abstract_text = inner.get("Verbatim_Abstract", "")
            if not abstract_text:
                console.print("empty abstract returned", style="yellow")
                failed += 1
                continue

            # Save to extraction JSON
            data["Verbatim_Abstract"] = abstract_text
            with open(ext_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Update Google Sheet
            sheet_row = pid_to_row.get(paper_id)
            if sheet_row:
                from populator import retry_on_api_error
                cell = f"{chr(65 + abstract_col)}{sheet_row}"
                ws.update(cell, [[abstract_text]], value_input_option="USER_ENTERED")
                console.print("done (JSON + Sheet)", style="green")
            else:
                console.print("done (JSON only, not in sheet)", style="green")

            succeeded += 1
            time.sleep(1)  # rate limit

        except subprocess.TimeoutExpired:
            console.print("timeout", style="red")
            failed += 1
        except (json.JSONDecodeError, KeyError) as e:
            console.print(f"parse error: {e}", style="red")
            failed += 1

    console.print(f"\n  Backfill complete: {succeeded} succeeded, {failed} failed")


# ─── MAIN ──────────────────────────────────────────────────

def main():
    args = parse_args()
    display = PipelineDisplay()

    # Discover PDFs
    pdfs = discover_pdfs(PDF_ROOT)
    already_processed = count_extracted(PDF_ROOT)

    # Filter by --paper or --reprocess
    if args.paper:
        search = args.paper.lower()
        pdfs = [p for p in pdfs if search in p.name.lower()]
        if not pdfs:
            console.print(f"  ❌ No PDF found matching '{args.paper}'", style="red")
            sys.exit(1)

    if args.reprocess:
        search = args.reprocess.lower()
        pdfs = [p for p in pdfs if search in p.name.lower()]
        if not pdfs:
            console.print(f"  ❌ No PDF found matching '{args.reprocess}'", style="red")
            sys.exit(1)

    # Dry run mode
    if args.dry_run:
        display.show_dry_run(PDF_ROOT, pdfs, already_processed)
        return

    # Backfill summary mode
    if args.backfill_summary:
        from populator import SheetPopulator
        from summary_writer import SummaryWriter
        pop = SheetPopulator(on_status=display.status_callback)
        sw = SummaryWriter(pop)
        console.print("  📊 Backfilling Literature_Review_Summary...")
        result = sw.backfill_missing()
        console.print(f"  Done: {result['written']} written, {result['skipped']} skipped, {result['failed']} failed")
        return

    # Backfill verbatim abstracts mode
    if args.backfill_abstracts:
        _backfill_abstracts(display)
        return

    # ─── PROCESSING MODE ────────────────────────────────────
    state = PipelineState()
    state.register_shutdown_handler()
    extractor = PaperExtractor()
    gap_analyzer = GapAnalyzer(initial_gaps=state.get_gaps())

    # Lazy-loaded populator and summary writer (only if needed)
    populator = None
    summary_writer = None

    # Handle --reprocess: clear state for matched papers
    if args.reprocess:
        for pdf in pdfs:
            paper = state.get_paper(pdf)
            if paper:
                paper["status"] = "pending"
        state.save()

    display.show_header(PDF_ROOT, len(pdfs), already_processed, skip_sheets=args.skip_sheets)

    run_start = time.time()
    completed_this_run = 0
    failed_this_run = 0
    report = RunReport(args)

    for i, pdf_path in enumerate(pdfs, 1):
        # Skip already-complete papers
        if state.is_complete(pdf_path) and not args.reprocess:
            console.print(f"  ⏭️  [{i}/{len(pdfs)}] Skipping (done): {pdf_path.name}", style="dim")
            report.add_skip()
            continue

        subfolder = ""
        try:
            subfolder = str(pdf_path.parent.relative_to(PDF_ROOT))
        except ValueError:
            pass

        display.show_paper_start(i, len(pdfs), pdf_path.name, subfolder)
        paper_start = time.time()

        # ─── EXTRACTION ─────────────────────────────────────

        # Check if already extracted (needs only population)
        paper_record = state.get_paper(pdf_path)
        extraction = None

        if state.needs_population(pdf_path) and paper_record and paper_record.get("extraction_file"):
            # Load existing extraction
            ext_file = paper_record["extraction_file"]
            if Path(ext_file).exists():
                console.print(f"  📂 Loading existing extraction from {Path(ext_file).name}")
                with open(ext_file) as f:
                    extraction = json.load(f)
            else:
                console.print(f"  ⚠️  Extraction file missing, re-extracting...")

        if extraction is None:
            state.mark_extracting(pdf_path)

            # Run extraction with spinner
            progress, task_id = display.create_extraction_spinner()
            with progress:
                extraction = extractor.extract(
                    pdf_path=pdf_path,
                    gap_state=gap_analyzer.get_unresolved(),
                    paper_index=i,
                    total_papers=len(pdfs),
                    on_status=lambda msg: progress.update(task_id, description=f"[bold blue]{msg}"),
                )
            console.print()

        if extraction is None:
            paper_duration = time.time() - paper_start
            state.mark_failed(pdf_path, "extraction", "Claude CLI extraction failed")
            failed_this_run += 1

            # Build failure reason from extractor diagnostics
            last_info = extractor.last_failure_info or {}
            failure_reason = last_info.get("reason", "Unknown extraction failure")
            error_details = last_info.get("details", "")
            report.add_failure(
                filename=pdf_path.name,
                subfolder=subfolder,
                duration_seconds=paper_duration,
                failure_stage="extraction",
                failure_reason=failure_reason,
                error_details=error_details,
                attempts=extractor.last_attempts,
            )
            display.show_paper_failed(i, len(pdfs), pdf_path.name, failure_reason)
            continue

        paper_id = extraction.get("paper_id", "unknown")
        extraction_file = extraction.get("_extraction_file", "")
        state.mark_extracted(pdf_path, extraction_file, paper_id)

        display.show_extraction_result(True, paper_id, extraction)

        # ─── GAP ANALYSIS ───────────────────────────────────

        gap_analysis = extraction.get("gap_analysis", {})
        gap_summary = gap_analyzer.merge_paper_gaps(paper_id, gap_analysis)
        warnings = gap_analyzer.cross_validate(paper_id, extraction, gap_analysis)
        state.update_gaps(gap_analyzer.to_list())

        display.show_gap_update(gap_summary, warnings)

        # ─── GOOGLE SHEETS ──────────────────────────────────

        if not args.skip_sheets:
            if populator is None:
                from populator import SheetPopulator
                populator = SheetPopulator(on_status=display.status_callback)

            state.mark_populating(pdf_path)
            console.print("\n  📊 Populating Google Sheets...")

            ok = populator.populate_paper(paper_id, extraction)
            if ok:
                ok2 = populator.update_gap_tracker(gap_analysis, paper_id)

                # Write summary row
                if summary_writer is None:
                    from summary_writer import SummaryWriter
                    summary_writer = SummaryWriter(populator)
                summary_writer.write_summary(paper_id, extraction, gap_analysis)

                state.mark_populated(pdf_path)

                # ─── GAP MATRIX ANALYSIS (inline, replaces old background spawn) ──
                try:
                    from gap_matrix_analyzer import GapMatrixAnalyzer
                    matrix_analyzer = GapMatrixAnalyzer()
                    console.print("  🔬 Running gap matrix analysis...")
                    matrix_result = matrix_analyzer.analyze_paper(paper_id, extraction, source="main")
                    n_written = matrix_result.get("written", 0)
                    n_resolved = len(matrix_result.get("gaps_newly_resolved", []))
                    if n_written > 0:
                        console.print(f"  ✅ Gap matrix: {n_written} evidence rows, {n_resolved} gaps newly resolved")
                    else:
                        console.print("  📊 Gap matrix: no new evidence (paper not relevant to open gaps)")
                except Exception as e:
                    console.print(f"  ⚠️  Gap matrix analysis failed: {e}", style="yellow")

                # ─── RETROACTIVE GAP ANALYSIS ──────────────────────
                # Check if Papers 1..N-1 already address this paper's new gaps
                try:
                    new_gap_ids = gap_summary.get("new_gap_ids", [])
                    if new_gap_ids:
                        from gap_matrix_analyzer import GapMatrixAnalyzer as _GMA
                        retro_analyzer = _GMA()
                        retro_result = retro_analyzer.retroactive_analyze(
                            new_gap_ids=new_gap_ids,
                            current_paper_id=paper_id,
                        )
                        retro_written = retro_result.get("evidence_written", 0)
                        if retro_written > 0:
                            console.print(
                                f"  ✅ Retroactive: {retro_written} evidence rows from prior papers"
                            )
                except Exception as e:
                    console.print(f"  ⚠️  Retroactive analysis failed (non-fatal): {e}", style="yellow")
            else:
                console.print("  ⚠️  Some Sheets writes failed", style="yellow")

        # ─── RENAME PDF ─────────────────────────────────────

        new_path = rename_pdf(pdf_path, extraction)
        state.mark_complete(pdf_path, str(new_path) if new_path else None)

        # ─── UPDATE STATS ───────────────────────────────────

        rel = extraction.get("9_RELEVANCE", {})
        theme = extraction.get("10_CLASSIFICATION", {}).get("Primary_Theme", "Unknown")
        tier = rel.get("Relevance_Tier", "Unknown")
        state.update_stats(paper_id, tier, theme)

        paper_duration = time.time() - paper_start
        report.add_success(
            filename=pdf_path.name,
            subfolder=subfolder,
            paper_id=paper_id,
            duration_seconds=paper_duration,
            extraction=extraction,
        )

        completed_this_run += 1
        display.show_paper_complete(i, len(pdfs), paper_id, str(new_path) if new_path else None)

    # ─── SAVE RUN REPORT ────────────────────────────────────
    report_path = report.save()

    # ─── FINAL SUMMARY ─────────────────────────────────────
    elapsed = time.time() - run_start
    display.show_run_summary(
        stats=state.data.get("stats", {}),
        gap_summary=gap_analyzer.get_summary(),
        elapsed=elapsed,
        report_path=report_path,
    )


if __name__ == "__main__":
    main()
