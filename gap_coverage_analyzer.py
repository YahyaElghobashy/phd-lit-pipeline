#!/usr/bin/env python3
"""
PhD Literature Extraction Pipeline — Gap Coverage Analyzer
============================================================
Standalone module that evaluates every research gap against each paper's
extraction data. Spawns dedicated Claude CLI sessions for gap interrogation.

This is a GAP CRITIQUE, not a paper critique. Each gap is interrogated:
"Has this paper's evidence narrowed or closed you?"

Usage:
    python3 gap_coverage_analyzer.py                          # Analyze all missing
    python3 gap_coverage_analyzer.py --paper "Adams"          # One paper vs all gaps (substring)
    python3 gap_coverage_analyzer.py --paper-id "He_2019..."  # Exact paper_id (used by main.py automation)
    python3 gap_coverage_analyzer.py --dry-run                # Show what needs analysis
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import (
    CLAUDE_CLI,
    CLAUDE_MODEL,
    EXTRACTIONS_DIR,
    PIPELINE_DIR,
    GAP_COVERAGE_TAB,
    GAP_ANALYSIS_TIMEOUT,
    GAP_ANALYSIS_MAX_RETRIES,
    GAP_ANALYSIS_RETRY_DELAY,
    GAP_BATCH_SIZE,
    SHEETS_WRITE_DELAY,
)
from populator import SheetPopulator, retry_on_api_error

console = Console()


# ─── SYSTEM PROMPT ──────────────────────────────────────────

SYSTEM_PROMPT = """You are a research gap evaluator for a PhD dissertation: "Women on Boards: An International Study in Governance and Wealth Creation."

Your task: Given a paper's evidence and a list of research gaps, INTERROGATE each gap. You are NOT reviewing the paper — you are judging whether each gap survives this paper's evidence.

For each gap, determine:

1. coverage_level — How much does this paper diminish this gap?
   - "NOT ADDRESSED" — paper has no relevance to this gap
   - "PARTIALLY ADDRESSED" — paper touches the topic but significant aspects remain open
   - "SUBSTANTIALLY COVERED" — paper directly investigates the core of this gap
   - "DIRECTLY TACKLED" — paper fully resolves this gap with strong evidence

2. coverage_justification — WHY this level? Reference specific findings from the paper.

3. what_remains_open — What aspects of this gap does this paper NOT resolve?

4. methodological_advance — Does this paper's methodology contribute to closing this gap?

5. our_opportunity — What does this paper's treatment (or lack thereof) of this gap mean for our PhD?

CRITICAL RULES:
- Be CONSERVATIVE. Most papers will be "NOT ADDRESSED" for most gaps.
- "PARTIALLY ADDRESSED" requires DIRECTLY relevant findings, not tangential overlap.
- "SUBSTANTIALLY COVERED" requires the paper to have tested the exact relationship the gap describes.
- "DIRECTLY TACKLED" requires comprehensive resolution with robust methodology.
- For "NOT ADDRESSED" gaps, write 1 sentence in coverage_justification explaining why.
- For "NOT ADDRESSED" gaps, what_remains_open = "All aspects remain open.", methodological_advance = "None.", our_opportunity = "".
- Return ONLY a valid JSON array. No markdown wrapping, no code fences, no explanation."""


# ─── GAP COVERAGE ANALYZER ─────────────────────────────────

class GapCoverageAnalyzer:
    """Evaluates every gap against each paper's extraction data."""

    def __init__(self, on_status: callable = None):
        self._pop = SheetPopulator(on_status=on_status or (lambda msg: console.print(f"  {msg}")))
        self._tab = GAP_COVERAGE_TAB

    # ── Public API ──────────────────────────────────────────

    def analyze_paper(self, paper_id: str, extraction: dict) -> dict:
        """
        Evaluate one paper against all gaps. Write results to GAP_COVERAGE_MAP.
        Automatically batches if gap count exceeds GAP_BATCH_SIZE.
        Returns stats: {"written": N, "skipped": N, "failed": N}
        """
        self._pop._ensure_connected()

        gaps = self._get_all_gaps()
        if not gaps:
            console.print("  [yellow]No gaps found in GAP_TRACKER[/yellow]")
            return {"written": 0, "skipped": 0, "failed": 0}

        existing = self._get_existing_coverage()
        missing_gaps = [g for g in gaps if (paper_id, g["gap_id"]) not in existing]

        if not missing_gaps:
            console.print(f"  [dim]All {len(gaps)} gaps already evaluated for {paper_id}[/dim]")
            return {"written": 0, "skipped": len(gaps), "failed": 0}

        console.print(
            f"  Evaluating {len(missing_gaps)} gaps "
            f"({len(gaps) - len(missing_gaps)} already done)"
        )

        paper_context = self._build_paper_context(extraction)

        # Batch gaps if the list is large
        batches = self._make_batches(gaps)
        all_assessments = []

        for batch_idx, batch in enumerate(batches):
            if len(batches) > 1:
                console.print(f"  Batch {batch_idx + 1}/{len(batches)} ({len(batch)} gaps)")

            gap_list_text = self._build_gap_list(batch)

            assessments = None
            for attempt in range(GAP_ANALYSIS_MAX_RETRIES + 1):
                if attempt > 0:
                    console.print(f"  [yellow]Retry {attempt}/{GAP_ANALYSIS_MAX_RETRIES} in {GAP_ANALYSIS_RETRY_DELAY}s...[/yellow]")
                    time.sleep(GAP_ANALYSIS_RETRY_DELAY)

                assessments = self._run_claude_analysis(paper_id, paper_context, gap_list_text)
                if assessments is not None:
                    break

            if assessments is None:
                console.print(f"  [red]All retries exhausted for {paper_id} (batch {batch_idx + 1})[/red]")
            else:
                all_assessments.extend(assessments)

        if not all_assessments:
            return {"written": 0, "skipped": 0, "failed": len(missing_gaps)}

        result = self._write_coverage_rows(paper_id, all_assessments, missing_gaps, existing)

        # Feedback loop: update GAP_TRACKER verdicts based on aggregated coverage
        analyzed_gap_ids = [g["gap_id"] for g in missing_gaps]
        self._update_gap_tracker_verdicts(analyzed_gap_ids)

        return result

    def analyze_all_missing(self) -> dict:
        """Scan extractions/*.json, analyze papers with missing gap coverage."""
        self._pop._ensure_connected()

        totals = {"written": 0, "skipped": 0, "failed": 0, "papers_processed": 0}

        extraction_files = sorted(EXTRACTIONS_DIR.glob("*.json"))
        if not extraction_files:
            console.print("  [yellow]No extraction files found[/yellow]")
            return totals

        gaps = self._get_all_gaps()
        if not gaps:
            console.print("  [yellow]No gaps found in GAP_TRACKER[/yellow]")
            return totals

        existing = self._get_existing_coverage()
        gap_ids = {g["gap_id"] for g in gaps}

        # Find papers with missing coverage
        papers_to_analyze = []
        for ext_file in extraction_files:
            try:
                with open(ext_file) as f:
                    extraction = json.load(f)
                paper_id = extraction.get("paper_id", "")
                if not paper_id:
                    continue
                missing = [gid for gid in gap_ids if (paper_id, gid) not in existing]
                if missing:
                    papers_to_analyze.append((paper_id, extraction, len(missing)))
            except Exception as e:
                console.print(f"  [red]Error reading {ext_file.name}: {e}[/red]")

        if not papers_to_analyze:
            console.print("  [green]All papers fully analyzed against all gaps[/green]")
            total_skipped = len(extraction_files) * len(gaps)
            totals["skipped"] = total_skipped
            return totals

        console.print(
            f"\n  [bold]Papers to analyze: {len(papers_to_analyze)}[/bold] "
            f"(of {len(extraction_files)} total) × {len(gaps)} gaps\n"
        )

        for i, (paper_id, extraction, n_missing) in enumerate(papers_to_analyze, 1):
            console.print(f"\n  [{i}/{len(papers_to_analyze)}] [bold cyan]{paper_id}[/bold cyan] — {n_missing} gaps to evaluate")
            result = self.analyze_paper(paper_id, extraction)
            totals["written"] += result["written"]
            totals["skipped"] += result["skipped"]
            totals["failed"] += result["failed"]
            totals["papers_processed"] += 1

        return totals

    def dry_run(self) -> None:
        """Show what needs analysis without processing."""
        self._pop._ensure_connected()

        extraction_files = sorted(EXTRACTIONS_DIR.glob("*.json"))
        gaps = self._get_all_gaps()
        existing = self._get_existing_coverage()

        gap_ids = {g["gap_id"] for g in gaps}
        total_combos = 0
        done_combos = 0

        console.print("\n  [bold]Gap Coverage Analyzer — Dry Run[/bold]\n")
        console.print(f"  Gaps in GAP_TRACKER: {len(gaps)}")
        console.print(f"  Extraction files: {len(extraction_files)}")
        console.print(f"  Existing coverage rows: {len(existing)}\n")

        for ext_file in extraction_files:
            try:
                with open(ext_file) as f:
                    extraction = json.load(f)
                paper_id = extraction.get("paper_id", "")
                if not paper_id:
                    continue

                done = sum(1 for gid in gap_ids if (paper_id, gid) in existing)
                missing = len(gap_ids) - done
                total_combos += len(gap_ids)
                done_combos += done

                status = "[green]complete[/green]" if missing == 0 else f"[yellow]{missing} missing[/yellow]"
                console.print(f"    {paper_id:30s}  {done}/{len(gap_ids)}  {status}")
            except Exception:
                continue

        console.print(f"\n  Total: {done_combos}/{total_combos} evaluated")
        console.print(f"  Remaining: {total_combos - done_combos} combinations\n")

    # ── Sheet I/O ───────────────────────────────────────────

    @retry_on_api_error()
    def _get_all_gaps(self) -> list[dict]:
        """Read all gaps from GAP_TRACKER sheet."""
        ws = self._pop._get_worksheet("GAP_TRACKER")
        rows = ws.get_all_records()
        gaps = []
        for row in rows:
            gap_id = str(row.get("Gap_ID", "")).strip()
            if not gap_id:
                continue
            gaps.append({
                "gap_id": gap_id,
                "gap_type": str(row.get("Gap_Type", "")),
                "gap_statement": str(row.get("Gap_Statement", "")),
                "severity": str(row.get("Severity", "")),
                "status": str(row.get("Status", "")),
            })
        return gaps

    @retry_on_api_error()
    def _get_existing_coverage(self) -> set[tuple[str, str]]:
        """Read existing (PAPER_ID, Gap_ID) pairs from GAP_COVERAGE_MAP."""
        ws = self._pop._get_worksheet(self._tab)
        header_map = self._pop._get_header_map(self._tab)

        pid_col = header_map.get("PAPER_ID", 0)
        gid_col = header_map.get("Gap_ID", 1)

        # Read both columns
        all_values = ws.get_all_values()
        pairs = set()
        for row in all_values[1:]:  # skip header
            if len(row) > max(pid_col, gid_col):
                pid = row[pid_col].strip()
                gid = row[gid_col].strip()
                if pid and gid:
                    pairs.add((pid, gid))
        return pairs

    def _write_coverage_rows(
        self,
        paper_id: str,
        assessments: list[dict],
        missing_gaps: list[dict],
        existing: set[tuple[str, str]],
    ) -> dict:
        """Write assessment rows to GAP_COVERAGE_MAP. Only writes missing pairs."""
        stats = {"written": 0, "skipped": 0, "failed": 0}

        # Index assessments by gap_id (deduplicate, keep first)
        assessment_map = {}
        for a in assessments:
            gid = a.get("gap_id", "")
            if gid and gid not in assessment_map:
                assessment_map[gid] = a

        missing_gap_ids = {g["gap_id"] for g in missing_gaps}

        # Warn about gaps Claude didn't return
        returned_ids = set(assessment_map.keys())
        missed = missing_gap_ids - returned_ids
        if missed:
            console.print(f"  [yellow]Warning: Claude did not return assessments for {len(missed)} gaps: {', '.join(sorted(missed)[:5])}...[/yellow]")
            stats["failed"] += len(missed)

        for gap_id, assessment in assessment_map.items():
            if (paper_id, gap_id) in existing:
                stats["skipped"] += 1
                continue
            if gap_id not in missing_gap_ids:
                stats["skipped"] += 1
                continue

            row_data = {
                "PAPER_ID": paper_id,
                "Gap_ID": gap_id,
                "Coverage_Level": assessment.get("coverage_level", "NOT ADDRESSED"),
                "Coverage_Justification": assessment.get("coverage_justification", ""),
                "What_Remains_Open": assessment.get("what_remains_open", ""),
                "Methodological_Advance": assessment.get("methodological_advance", ""),
                "Our_Opportunity": assessment.get("our_opportunity", ""),
            }

            try:
                self._pop._write_row_by_headers(self._tab, row_data)
                stats["written"] += 1
                time.sleep(SHEETS_WRITE_DELAY)
            except Exception as e:
                console.print(f"  [red]Write failed for {gap_id}: {e}[/red]")
                stats["failed"] += 1

        # Show coverage distribution
        levels = {}
        for a in assessment_map.values():
            lvl = a.get("coverage_level", "NOT ADDRESSED")
            levels[lvl] = levels.get(lvl, 0) + 1
        dist = ", ".join(f"{k}: {v}" for k, v in sorted(levels.items()))
        console.print(f"  Coverage: {dist}")
        console.print(f"  Written: {stats['written']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}")

        return stats

    # ── Gap Tracker Feedback Loop ────────────────────────────

    @staticmethod
    def _coverage_rank(level: str) -> int:
        """Rank coverage levels for comparison. Higher = more covered."""
        return {"NOT ADDRESSED": 0, "PARTIALLY ADDRESSED": 1,
                "SUBSTANTIALLY COVERED": 2, "DIRECTLY TACKLED": 3}.get(level, 0)

    @staticmethod
    def _status_rank(status: str) -> int:
        """Rank statuses so we never downgrade."""
        return {"Identified": 0, "Under Investigation": 1,
                "Partially Resolved": 2, "Resolved": 3}.get(status, 0)

    @retry_on_api_error()
    def _update_gap_tracker_verdicts(self, gap_ids: list[str]) -> None:
        """
        Aggregate coverage from GAP_COVERAGE_MAP and update GAP_TRACKER:
        Coverage_Level, Covering_Paper_IDs, Coverage_Notes, Status, Severity, Novelty.
        Never downgrades status or increases scores.
        """
        if not gap_ids:
            return

        gap_id_set = set(gap_ids)

        # ── Step 1: Read all coverage rows ──
        cov_ws = self._pop._get_worksheet(self._tab)
        cov_header_map = self._pop._get_header_map(self._tab)
        cov_all = cov_ws.get_all_values()

        pid_col = cov_header_map.get("PAPER_ID", 0)
        gid_col = cov_header_map.get("Gap_ID", 1)
        lvl_col = cov_header_map.get("Coverage_Level", 2)

        # Build: gap_id → list of (paper_id, coverage_level)
        coverage_by_gap: dict[str, list[tuple[str, str]]] = {}
        for row in cov_all[1:]:  # skip header
            if len(row) <= max(pid_col, gid_col, lvl_col):
                continue
            gid = row[gid_col].strip()
            if gid not in gap_id_set:
                continue
            pid = row[pid_col].strip()
            lvl = row[lvl_col].strip()
            if pid and gid:
                coverage_by_gap.setdefault(gid, []).append((pid, lvl))

        if not coverage_by_gap:
            return

        # ── Step 2: Read GAP_TRACKER ──
        tracker_ws = self._pop._get_worksheet("GAP_TRACKER")
        tracker_header_map = self._pop._get_header_map("GAP_TRACKER")
        tracker_all = tracker_ws.get_all_values()

        if len(tracker_all) < 2:
            return

        # Column indices (0-based)
        t_gid = tracker_header_map.get("Gap_ID", 0)
        t_severity = tracker_header_map.get("Severity", 3)
        t_novelty = tracker_header_map.get("Novelty", 5)
        t_status = tracker_header_map.get("Status", 13)
        t_coverage = tracker_header_map.get("Coverage_Level", 15)
        t_covering_ids = tracker_header_map.get("Covering_Paper_IDs", 16)
        t_coverage_notes = tracker_header_map.get("Coverage_Notes", 17)

        from gspread import Cell
        cells_to_update = []

        for row_idx, row in enumerate(tracker_all[1:], start=2):  # 1-indexed sheet rows
            if len(row) <= t_gid:
                continue
            gid = row[t_gid].strip()
            if gid not in coverage_by_gap:
                continue

            entries = coverage_by_gap[gid]

            # ── Step 2: Aggregate ──
            highest_rank = 0
            highest_level = "NOT ADDRESSED"
            covering_papers = []
            n_direct = 0
            n_substantial = 0
            level_papers: dict[str, list[str]] = {}

            for paper_id, level in entries:
                rank = self._coverage_rank(level)
                if rank > highest_rank:
                    highest_rank = rank
                    highest_level = level
                if rank >= 1:  # PARTIALLY ADDRESSED or above
                    covering_papers.append(paper_id)
                if level == "DIRECTLY TACKLED":
                    n_direct += 1
                elif level == "SUBSTANTIALLY COVERED":
                    n_substantial += 1
                level_papers.setdefault(level, []).append(paper_id)

            # ── Step 3: Derive status and score adjustments ──
            new_status = None
            sev_delta = 0
            nov_delta = 0

            if n_direct >= 2:
                new_status = "Resolved"
                sev_delta = -3
                nov_delta = -3
            elif n_direct == 1:
                new_status = "Partially Resolved"
                sev_delta = -2
                nov_delta = -2
            elif n_substantial >= 3:
                new_status = "Partially Resolved"
                sev_delta = -1
                nov_delta = -2
            elif n_substantial >= 1:
                new_status = "Under Investigation"
                sev_delta = -1
                nov_delta = -1

            # Current values
            current_status = row[t_status].strip() if len(row) > t_status else "Identified"
            try:
                current_severity = int(row[t_severity]) if len(row) > t_severity and row[t_severity].strip() else 3
            except (ValueError, IndexError):
                current_severity = 3
            try:
                current_novelty = int(row[t_novelty]) if len(row) > t_novelty and row[t_novelty].strip() else 3
            except (ValueError, IndexError):
                current_novelty = 3

            # Never downgrade status
            if new_status and self._status_rank(new_status) > self._status_rank(current_status):
                final_status = new_status
            else:
                final_status = current_status
                # If status didn't upgrade, don't apply score deltas
                if new_status and self._status_rank(new_status) <= self._status_rank(current_status):
                    sev_delta = 0
                    nov_delta = 0

            # Apply score adjustments (floor 1, never increase)
            final_severity = max(1, current_severity + sev_delta)
            final_novelty = max(1, current_novelty + nov_delta)

            # Compose coverage notes
            note_parts = [f"{len(entries)} papers evaluated:"]
            for level_name in ["DIRECTLY TACKLED", "SUBSTANTIALLY COVERED", "PARTIALLY ADDRESSED", "NOT ADDRESSED"]:
                papers = level_papers.get(level_name, [])
                if papers:
                    note_parts.append(f"{len(papers)} {level_name} ({', '.join(papers[:3])}{'...' if len(papers) > 3 else ''})")
            notes_str = " ".join(note_parts)
            if sev_delta != 0 or nov_delta != 0:
                notes_str += f" Severity {current_severity}→{final_severity}, Novelty {current_novelty}→{final_novelty}."

            # ── Step 4: Build cell updates ──
            # gspread Cell is 1-indexed for both row and col
            cells_to_update.append(Cell(row=row_idx, col=t_coverage + 1, value=highest_level))
            cells_to_update.append(Cell(row=row_idx, col=t_covering_ids + 1, value=", ".join(covering_papers)))
            cells_to_update.append(Cell(row=row_idx, col=t_coverage_notes + 1, value=notes_str))
            cells_to_update.append(Cell(row=row_idx, col=t_status + 1, value=final_status))
            cells_to_update.append(Cell(row=row_idx, col=t_severity + 1, value=str(final_severity)))
            cells_to_update.append(Cell(row=row_idx, col=t_novelty + 1, value=str(final_novelty)))

        if cells_to_update:
            tracker_ws.update_cells(cells_to_update)
            n_gaps = len(cells_to_update) // 6
            console.print(f"  [green]GAP_TRACKER updated: {n_gaps} gaps verdicts refreshed[/green]")
        else:
            console.print(f"  [dim]No GAP_TRACKER updates needed[/dim]")

    # ── Batching ─────────────────────────────────────────────

    @staticmethod
    def _make_batches(gaps: list[dict]) -> list[list[dict]]:
        """Split gaps into batches of GAP_BATCH_SIZE for large gap lists."""
        if len(gaps) <= GAP_BATCH_SIZE:
            return [gaps]
        return [gaps[i:i + GAP_BATCH_SIZE] for i in range(0, len(gaps), GAP_BATCH_SIZE)]

    # ── Prompt Building ─────────────────────────────────────

    def _build_paper_context(self, extraction: dict) -> str:
        """Compose paper's key sections into prompt text."""
        parts = [f"PAPER: {extraction.get('paper_id', 'unknown')}"]

        # Findings
        f = extraction.get("7_FINDINGS", {})
        if f:
            parts.append("\nFINDINGS:")
            main = f.get("Main_Finding", "")
            if main:
                parts.append(main)
            direction = f.get("Effect_Direction", "")
            if direction:
                parts.append(f"Effect: {direction}")
            coeff = f.get("Coefficient_Beta", "")
            p_val = f.get("P_Value", "")
            if coeff or p_val:
                stat = f"Statistical: {coeff}" if coeff else "Statistical:"
                if p_val:
                    stat += f" (p: {p_val})"
                parts.append(stat)
            mod = f.get("Moderating_Effects_Found", "")
            if mod:
                parts.append(f"Moderating effects: {mod}")
            med = f.get("Mediating_Effects_Found", "")
            if med:
                parts.append(f"Mediating effects: {med}")
            mech = f.get("Mechanisms_Channels_Identified", "")
            if mech:
                parts.append(f"Mechanisms: {mech}")

        # Variables
        v = extraction.get("3_VARIABLES", {})
        if v:
            parts.append("\nVARIABLES:")
            for prefix, label in [("DV1", "DV"), ("DV2", "DV2"),
                                   ("IV1", "IV"), ("IV2", "IV2"), ("IV3", "IV3")]:
                name = v.get(f"{prefix}_Name", "")
                if name:
                    cat = v.get(f"{prefix}_Category", "")
                    meas = v.get(f"{prefix}_Measurement", "")
                    entry = f"{label}: {name}"
                    if cat:
                        entry += f" ({cat})"
                    if meas:
                        entry += f" — {meas}"
                    parts.append(entry)

            for i in [1, 2]:
                name = v.get(f"Moderator{i}_Name", "")
                if name:
                    meas = v.get(f"Moderator{i}_Measurement", "")
                    finding = v.get(f"Moderator{i}_Finding", "")
                    entry = f"Moderator: {name}"
                    if meas:
                        entry += f" — {meas}"
                    if finding:
                        entry += f" [{finding}]"
                    parts.append(entry)

            for i in [1, 2]:
                name = v.get(f"Mediator{i}_Name", "")
                if name:
                    pathway = v.get(f"Mediator{i}_Pathway", "")
                    confirmed = v.get(f"Mediator{i}_Confirmed", "")
                    entry = f"Mediator: {name}"
                    if pathway:
                        entry += f" — {pathway}"
                    if confirmed:
                        entry += f" [confirmed: {confirmed}]"
                    parts.append(entry)

            controls = v.get("Controls_List", "")
            if controls:
                parts.append(f"Controls: {controls}")

        # Methodology
        m = extraction.get("4_METHODOLOGY", {})
        if m:
            parts.append("\nMETHODOLOGY:")
            design = m.get("Research_Design", "")
            est = m.get("Estimation_Primary", "")
            if design or est:
                parts.append(f"{design} — {est}".strip(" — "))
            endo = m.get("Endogeneity_Methods", "")
            if endo:
                parts.append(f"Endogeneity: {endo}")
            robustness = [m.get(f"Robustness_Check_{i}", "") for i in range(1, 5)]
            robustness = [r for r in robustness if r]
            if robustness:
                parts.append(f"Robustness: {', '.join(robustness)}")

        # Sample
        s = extraction.get("5_SAMPLE", {})
        if s:
            parts.append("\nSAMPLE:")
            sample_parts = []
            countries = s.get("Countries", "")
            if countries:
                sample_parts.append(countries)
            n_obs = s.get("N_Observations", "")
            if n_obs:
                sample_parts.append(f"{n_obs} obs")
            start = s.get("Period_Start", "")
            end = s.get("Period_End", "")
            if start and end:
                sample_parts.append(f"{start}–{end}")
            industries = s.get("Industries_Included", "")
            if industries:
                sample_parts.append(industries)
            if sample_parts:
                parts.append(", ".join(sample_parts))

        # Paper's own gap assessment
        gl = extraction.get("8_GAPS_LIMITATIONS", {})
        if gl:
            gap_fields = {
                "OUR_Variable_Gap": "Variable",
                "OUR_Methodological_Gap": "Methodological",
                "OUR_Contextual_Gap": "Contextual",
                "OUR_Mechanism_Gap": "Mechanism",
                "OUR_Theoretical_Gap": "Theoretical",
            }
            gap_lines = []
            for field, label in gap_fields.items():
                val = gl.get(field, "")
                if val:
                    gap_lines.append(f"{label}: {val}")
            if gap_lines:
                parts.append("\nPAPER'S OWN GAP ASSESSMENT:")
                parts.extend(gap_lines)

        return "\n".join(parts)

    def _build_gap_list(self, gaps: list[dict]) -> str:
        """Format all gaps for the prompt."""
        lines = ["RESEARCH GAPS TO EVALUATE:", ""]
        for g in gaps:
            severity = g.get("severity", "?")
            gap_type = g.get("gap_type", "Unknown")
            statement = g.get("gap_statement", "No statement available")
            lines.append(f'{g["gap_id"]} [{gap_type}, Severity {severity}]:')
            lines.append(f'"{statement}"')
            lines.append("")
        return "\n".join(lines)

    # ── Claude CLI ──────────────────────────────────────────

    def _run_claude_analysis(
        self, paper_id: str, paper_context: str, gap_list_text: str
    ) -> list[dict] | None:
        """Spawn Claude CLI, return list of gap assessments."""
        user_prompt = (
            f"{paper_context}\n\n---\n\n{gap_list_text}\n---\n\n"
            "Return JSON array with one object per gap:\n"
            '[{"gap_id": "...", "coverage_level": "...", "coverage_justification": "...", '
            '"what_remains_open": "...", "methodological_advance": "...", "our_opportunity": "..."}]'
        )

        cmd = [
            CLAUDE_CLI,
            "-p", user_prompt,
            "--output-format", "json",
            "--model", CLAUDE_MODEL,
            "--max-turns", "1",
            "--no-session-persistence",
            "--append-system-prompt", SYSTEM_PROMPT,
        ]

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                console=console,
            ) as progress:
                task_id = progress.add_task(f"Analyzing {paper_id}...")

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env={**os.environ, "CLAUDE_CODE_HEADLESS": "1"},
                )

                stdout_lines = []
                stderr_lines = []

                def read_stream(stream, line_list):
                    for line in stream:
                        line_list.append(line)

                stdout_thread = threading.Thread(
                    target=read_stream, args=(process.stdout, stdout_lines), daemon=True
                )
                stderr_thread = threading.Thread(
                    target=read_stream, args=(process.stderr, stderr_lines), daemon=True
                )
                stdout_thread.start()
                stderr_thread.start()

                try:
                    process.wait(timeout=GAP_ANALYSIS_TIMEOUT)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    console.print(f"  [red]TIMEOUT after {GAP_ANALYSIS_TIMEOUT}s[/red]")
                    return None

                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)

            stdout_full = "".join(stdout_lines)
            stderr_full = "".join(stderr_lines)

            if process.returncode != 0:
                console.print(f"  [red]Claude exited with code {process.returncode}[/red]")
                if stderr_full.strip():
                    console.print(f"  [dim]stderr: {stderr_full[:200]}[/dim]")
                return None

            return self._parse_claude_output(stdout_full)

        except FileNotFoundError:
            console.print("  [red]'claude' CLI not found. Is Claude Code installed?[/red]")
            return None
        except Exception as e:
            console.print(f"  [red]Unexpected error: {e}[/red]")
            return None

    def _parse_claude_output(self, stdout: str) -> list[dict] | None:
        """
        Parse Claude CLI JSON output expecting a JSON array.
        --output-format json returns: {"type":"result","result":"<content>","...}
        """
        stdout = stdout.strip()
        if not stdout:
            console.print("  [red]Empty output from Claude CLI[/red]")
            return None

        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            # Try direct array parse
            return self._extract_json_array(stdout)

        # Handle envelope format
        if isinstance(envelope, list):
            return envelope

        if isinstance(envelope, dict) and "result" in envelope:
            result = envelope["result"]
            if isinstance(result, list):
                return result
            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    return self._extract_json_array(result)

        console.print("  [red]Could not find assessment array in Claude output[/red]")
        return None

    def _extract_json_array(self, text: str) -> list[dict] | None:
        """Extract outermost [...] from text using bracket-depth matching."""
        start = text.find("[")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False

        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        result = json.loads(text[start:i + 1])
                        if isinstance(result, list):
                            return result
                    except json.JSONDecodeError:
                        console.print("  [red]Found JSON-like array but couldn't parse it[/red]")
                        return None
        return None


# ─── AUTO-TRIGGER FROM MAIN PIPELINE ────────────────────────

def spawn_for_paper(paper_id: str) -> subprocess.Popen | None:
    """
    Fire-and-forget: launch gap coverage analysis for one paper as a
    detached background process. Called by main.py after each paper's
    sheets population completes.

    Returns the Popen handle (caller does NOT need to wait on it).
    """
    script = str(PIPELINE_DIR / "gap_coverage_analyzer.py")
    try:
        proc = subprocess.Popen(
            ["python3", script, "--paper-id", paper_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # fully detached from parent
        )
        return proc
    except Exception as e:
        console.print(f"  [yellow]Could not spawn gap analyzer for {paper_id}: {e}[/yellow]")
        return None


def _load_extraction_by_paper_id(paper_id: str) -> tuple[str, dict] | None:
    """Find extraction JSON by exact paper_id match."""
    for ext_file in sorted(EXTRACTIONS_DIR.glob("*.json")):
        try:
            with open(ext_file) as f:
                extraction = json.load(f)
            if extraction.get("paper_id", "") == paper_id:
                return (paper_id, extraction)
        except Exception:
            continue
    return None


def _load_extraction_by_substring(search: str) -> tuple[str, dict] | None:
    """Find extraction JSON by substring match on paper_id or filename."""
    search_lower = search.lower()
    for ext_file in sorted(EXTRACTIONS_DIR.glob("*.json")):
        try:
            with open(ext_file) as f:
                extraction = json.load(f)
            pid = extraction.get("paper_id", "")
            if search_lower in pid.lower() or search_lower in ext_file.name.lower():
                return (pid, extraction)
        except Exception:
            continue
    return None


# ─── CLI ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gap Coverage Analyzer")
    parser.add_argument("--paper", type=str, default=None, help="Analyze one paper by name substring (manual use)")
    parser.add_argument("--paper-id", type=str, default=None, help="Analyze one paper by exact paper_id (automation)")
    parser.add_argument("--dry-run", action="store_true", help="Show what needs analysis")
    args = parser.parse_args()

    analyzer = GapCoverageAnalyzer()
    run_start = time.time()

    console.print("\n  [bold]Gap Coverage Analyzer[/bold]")
    console.print("  " + "─" * 50)

    if args.dry_run:
        analyzer.dry_run()
        return

    if args.paper_id:
        # Exact match — used by main.py automation
        match = _load_extraction_by_paper_id(args.paper_id)
        if not match:
            console.print(f"  [red]No extraction found for paper_id '{args.paper_id}'[/red]")
            return
        paper_id, extraction = match
        console.print(f"  Paper: [bold cyan]{paper_id}[/bold cyan]  (auto-triggered)\n")
        result = analyzer.analyze_paper(paper_id, extraction)

    elif args.paper:
        # Substring match — manual use
        match = _load_extraction_by_substring(args.paper)
        if not match:
            console.print(f"  [red]No extraction found matching '{args.paper}'[/red]")
            return
        paper_id, extraction = match
        console.print(f"  Paper: [bold cyan]{paper_id}[/bold cyan]\n")
        result = analyzer.analyze_paper(paper_id, extraction)

    else:
        result = analyzer.analyze_all_missing()

    elapsed = time.time() - run_start
    console.print(f"\n  [bold]Done[/bold] in {elapsed:.1f}s")
    console.print(
        f"  Written: {result.get('written', 0)}, "
        f"Skipped: {result.get('skipped', 0)}, "
        f"Failed: {result.get('failed', 0)}"
    )
    console.print()


if __name__ == "__main__":
    main()
