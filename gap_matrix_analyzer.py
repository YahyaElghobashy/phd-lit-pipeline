#!/usr/bin/env python3
"""
PhD Literature Extraction Pipeline — Gap Matrix Analyzer
==========================================================
Unified replacement for GAP_COVERAGE_MAP + GAP_NOVELTY.

Uses a cumulative percentage elimination model:
- Each cell = % of REMAINING gap this paper eliminates
- Sequential: Paper B evaluates against what's LEFT after Paper A
- Resolved gaps (< threshold remaining) auto-skipped
- Two-phase: Sonnet screen -> Opus deep analysis with history

Writes to GAP_MATRIX (cross-tabulation) and GAP_EVIDENCE (audit trail)
in the ORIGINAL Google Sheet.

Usage:
    python3 gap_matrix_analyzer.py                        # All unanalyzed papers
    python3 gap_matrix_analyzer.py --paper "Adams"        # One paper (substring)
    python3 gap_matrix_analyzer.py --paper-id "He_2019"   # Exact paper_id
    python3 gap_matrix_analyzer.py --dry-run              # Preview
    python3 gap_matrix_analyzer.py --status               # Matrix stats
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from config import (
    CLAUDE_CLI,
    CLAUDE_MODEL,
    EXTRACTIONS_DIR,
    PIPELINE_DIR,
    GAP_BATCH_SIZE,
    SHEETS_WRITE_DELAY,
    SPREADSHEET_ID,
    REASONING_LOG_FILE,
    TIER_NICHE,
    TIER_SUPPORTING,
)
from populator import SheetPopulator, authenticate, retry_on_api_error

console = Console()


# ─── CONFIGURATION ──────────────────────────────────────────

GAP_MATRIX_TAB = "GAP_MATRIX"
GAP_EVIDENCE_TAB = "GAP_EVIDENCE"
RESOLVED_THRESHOLD = 10        # % remaining below which gap is "Resolved"
SCREEN_TIMEOUT = 120           # Phase 1 Sonnet screen (seconds)
DEEP_TIMEOUT = 300             # Phase 2 Opus deep analysis (seconds)
MAX_RETRIES = 2
RETRY_DELAY = 30
SONNET_MODEL = "claude-sonnet-4-6"

GAP_EVIDENCE_COLUMNS = [
    "Gap_ID", "Paper_ID", "Pct_Eliminated", "Pct_Remaining_Before",
    "Pct_Remaining_After", "Aspect_Addressed", "What_Still_Remains",
    "Reasoning",  # Full AI reasoning (truncated for sheet, full in local log)
    "Assessed_By", "Assessed_At", "Source",
    # Module 6: Confidence scoring
    "Confidence_Methodological", "Confidence_Sample",
    "Confidence_Variables", "Confidence_Directness",
    "Confidence_Overall", "Confidence_Tier",
]

# State thresholds
STATE_THRESHOLDS = [
    (80, "Open"),                   # >= 80% remaining
    (40, "Under Investigation"),    # 40-79%
    (10, "Partially Resolved"),     # 10-39%
    (0, "Resolved"),                # < 10%
]


def _derive_gap_state(pct_remaining: float) -> str:
    """Derive gap state from remaining percentage."""
    for threshold, state in STATE_THRESHOLDS:
        if pct_remaining >= threshold:
            return state
    return "Resolved"


def _extract_confidence(assessment: dict) -> dict:
    """
    Extract confidence sub-scores from a Claude assessment, compute weighted overall + tier.

    Returns empty dict if no confidence data present (backward-compatible).
    """
    conf = assessment.get("confidence", {})
    if not conf or not isinstance(conf, dict):
        return {}

    from config import CONFIDENCE_WEIGHTS, CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_LOW_THRESHOLD

    scores = {
        "methodological": min(5, max(1, int(conf.get("methodological_alignment", 0) or 0))),
        "sample": min(5, max(1, int(conf.get("sample_relevance", 0) or 0))),
        "variables": min(5, max(1, int(conf.get("variable_overlap", 0) or 0))),
        "directness": min(5, max(1, int(conf.get("evidence_directness", 0) or 0))),
    }

    overall = round(
        scores["methodological"] * CONFIDENCE_WEIGHTS["methodological_alignment"]
        + scores["sample"] * CONFIDENCE_WEIGHTS["sample_relevance"]
        + scores["variables"] * CONFIDENCE_WEIGHTS["variable_overlap"]
        + scores["directness"] * CONFIDENCE_WEIGHTS["evidence_directness"],
        2,
    )

    tier = (
        "High" if overall >= CONFIDENCE_HIGH_THRESHOLD
        else "Moderate" if overall >= CONFIDENCE_LOW_THRESHOLD
        else "Low"
    )

    return {
        **scores,
        "overall": overall,
        "tier": tier,
        "rationale": str(conf.get("rationale", "")),
    }


def _log_reasoning(paper_id: str, assessments: list[dict]) -> None:
    """
    Append full reasoning to local JSON log (too large for Google Sheets).
    This is the untruncated version of reasoning — the sheet gets [:2000].
    """
    log_file = REASONING_LOG_FILE
    log_file.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if log_file.exists():
        try:
            with open(log_file) as f:
                existing = json.load(f)
        except Exception:
            existing = []

    entry = {
        "paper_id": paper_id,
        "assessed_at": datetime.now().isoformat(),
        "assessments": [
            {
                "gap_id": a.get("gap_id"),
                "pct_eliminated": a.get("pct_eliminated"),
                "reasoning": a.get("reasoning", ""),
                "aspect_addressed": a.get("aspect_addressed", ""),
                "what_still_remains": a.get("what_still_remains", ""),
                "confidence": a.get("confidence", {}),
            }
            for a in assessments
            if isinstance(a, dict) and a.get("gap_id")
        ],
    }
    existing.append(entry)

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


# ─── SYSTEM PROMPTS ─────────────────────────────────────────

SCREEN_SYSTEM_PROMPT = """You are a research gap screener for a PhD dissertation: "[TITLE_PLACEHOLDER — regenerated by codegen]"

Your task: Given a paper's key data and a list of research gaps, quickly identify which gaps this paper MIGHT be relevant to. Be INCLUSIVE — it's better to include a borderline gap than miss a relevant one. The deep analysis will filter false positives.

Return ONLY a JSON array of gap IDs that this paper could potentially affect.
Example: ["GAP_001", "GAP_015", "GAP_042"]

If the paper is irrelevant to ALL gaps, return an empty array: []

RULES:
- Include any gap where the paper's topic, methodology, sample, or findings could have ANY bearing
- Include gaps about the same variables, same region, same methodology, or same theoretical framework
- Pay special attention to the EXPERT GAP ASSESSMENT section (OUR_ fields) — if it identifies theoretical, methodological, variable, contextual, or mechanism connections to any gap, include that gap
- Be generous — false positives are OK, false negatives are costly
- Return ONLY the JSON array. No explanation, no markdown."""

DEEP_SYSTEM_PROMPT = """You are a research gap analyst for a PhD dissertation: "[TITLE_PLACEHOLDER — regenerated by codegen]"

DISSERTATION CONTEXT:
[This section is regenerated by `python -m codegen.generate_gap_prompts` from research_config.yaml]
- Configure your research papers, variables, and databases in research_config.yaml
- Run the codegen to populate this prompt with your specific research context

Your task: For each gap below, determine what PERCENTAGE of the REMAINING gap this paper eliminates. This is a cumulative model — previous papers may have already addressed parts of each gap. You evaluate ONLY against what's still open.

CRITICAL: Your percentage reflects what THIS paper adds BEYOND previous coverage. If a previous paper already addressed the same angle, this paper's addition is minimal (near 0%). But if this paper covers a NEW dimension, it should score meaningfully.

For each gap, return:
{
  "gap_id": "GAP_XXX",
  "pct_eliminated": <0-100>,
  "aspect_addressed": "What specific aspect of the remaining gap does this paper address? Be detailed — reference specific findings, methodology, sample, and how they relate to what was still open.",
  "what_still_remains": "What aspects of the gap are still open after this paper? Be specific about what's missing.",
  "reasoning": "Full reasoning: Why this percentage? Reference specific evidence from the paper. Compare to prior coverage. Explain what's new vs redundant.",
  "confidence": {
    "methodological_alignment": <1-5>,
    "sample_relevance": <1-5>,
    "variable_overlap": <1-5>,
    "evidence_directness": <1-5>,
    "rationale": "<1 sentence explaining confidence>"
  }
}

SCORING GUIDE — Be ACCURATE and CALIBRATED:
- 0%: Paper is irrelevant to what remains of this gap
- 1-5%: Paper touches the topic tangentially — no direct contribution to what remains
- 6-15%: Paper addresses one minor dimension (e.g., same theory in a different context, or same region but unrelated DV)
- 16-30%: Paper addresses a MEANINGFUL dimension of what's remaining (e.g., same methodology applied to related DVs, or same DVs in a different region, or a relevant moderator/mediator)
- 31-50%: Paper SUBSTANTIALLY addresses the core of what's remaining — covers the key question with relevant evidence, though not a perfect match on all dimensions
- 51-75%: Paper COMPREHENSIVELY addresses most of what's remaining — strong methodology, relevant context, similar variables, solid evidence
- 76-100%: Paper resolves nearly everything remaining — same question, strong evidence, comprehensive coverage (rare but possible)

IMPORTANT CALIBRATION NOTES:
- The MIDPOINT for a genuinely relevant paper is ~15-25%. If a paper passed the relevance screening, it likely has something meaningful to contribute.
- A paper studying the focal IV with a financial DV in a single country contributes ~5-10% to a gap about the focal IV and a non-financial DV (related IV but wrong DV and narrow context).
- A paper studying a related IV with the target DV in a multi-country panel contributes ~25-40% to a gap about the focal IV and target DV (right direction, relevant evidence, transferable methodology).
- A paper studying related characteristics with a related DV using strong methodology contributes ~15-25% to a methodological gap about endogeneity in the research domain.
- A meta-analysis of research topic effects on outcome variables contributes ~30-50% to broad theoretical gaps.

USE THE EXPERT GAP ASSESSMENT: The paper data includes an "EXPERT GAP ASSESSMENT" section with observations about how this paper relates to the dissertation's gaps (theoretical, methodological, variable, contextual, mechanism). These are expert-quality observations — use them as evidence when scoring.

RULES:
- A paper that covers the SAME ground as a previous paper scores near 0% (redundant)
- A paper that covers a NEW dimension of the gap scores proportionally to the significance of that dimension
- NEVER fabricate evidence. Only cite findings from the provided extraction data
- Return ONLY a valid JSON array. No markdown, no code fences

CONFIDENCE SCORING (1-5 integer scale):
- methodological_alignment: Does the paper's research design relate to what the gap requires?
  1 = Completely different paradigm, 2 = Weak connection, 3 = Related approach (ACADEMIC NORM for papers in same field), 4 = Strong alignment, 5 = Exact method match

- sample_relevance: Does the paper's sample context relate to the gap's target?
  1 = Completely different, 2 = Weak overlap, 3 = Meaningful partial overlap (ACADEMIC NORM), 4 = Strong overlap, 5 = Exact context match

- variable_overlap: Do the paper's variables relate to the gap's requirements?
  1 = No overlap, 2 = Tangentially related, 3 = Studies related variables (ACADEMIC NORM), 4 = Strong variable overlap, 5 = Exact variable match

- evidence_directness: How directly does evidence address the gap?
  1 = Tangential only, 2 = Implied connection, 3 = Addresses related question with transferable findings (ACADEMIC NORM), 4 = Directly relevant evidence, 5 = Explicitly tests the gap's question

NOTE: A confidence score of 3 is the EXPECTED NORM for papers in the same research area. Scores of 4-5 require specific, strong alignment. Most papers in a literature review should cluster around 2.5-3.5."""


# ─── GAP MATRIX ANALYZER ───────────────────────────────────

class GapMatrixAnalyzer:
    """
    Unified gap analysis using cumulative percentage elimination.
    Reads/writes GAP_MATRIX and GAP_EVIDENCE tabs in the original sheet.
    """

    def __init__(self, sheet_id: str = "", on_status: callable = None):
        self._sheet_id = sheet_id or SPREADSHEET_ID
        self._pop = SheetPopulator(on_status=on_status or (lambda msg: console.print(f"  {msg}")))
        self._matrix_cache = None  # Lazy loaded

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════

    def reset_and_rerun(self, extraction_dir: Path = None) -> dict:
        """
        Clear GAP_MATRIX + GAP_EVIDENCE data and redo all gap analysis from scratch.

        This fixes issues like incorrect manual formulas in the sheet by wiping
        everything and letting Python repopulate with correct multiplicative values.

        Returns: totals dict from analyze_all_missing().
        """
        ext_dir = extraction_dir or EXTRACTIONS_DIR
        self._pop._ensure_connected()

        console.print("\n  [bold red]RESET: Clearing GAP_MATRIX and GAP_EVIDENCE[/]\n")

        # 1. Clear GAP_MATRIX — both data rows AND paper column headers (D1+)
        #    Leaving A1:C1 (Gap_ID, Pct_Remaining, Gap_State labels) intact.
        #    Clearing D1:ZZ1 is critical: analyze_all_missing() detects "done"
        #    papers by reading paper_ids from row 1, so stale headers here
        #    would cause those papers to be silently skipped on re-run.
        try:
            ws_matrix = self._pop._get_worksheet(GAP_MATRIX_TAB)
            row_count = ws_matrix.row_count
            ranges_to_clear = ["D1:ZZ1"]  # paper column headers
            if row_count > 1:
                ranges_to_clear.append(f"A2:ZZ{row_count}")  # all data rows
            ws_matrix.batch_clear(ranges_to_clear)
            console.print("  [dim]GAP_MATRIX data + paper column headers cleared[/]")
            time.sleep(SHEETS_WRITE_DELAY)
        except Exception as e:
            console.print(f"  [red]Failed to clear GAP_MATRIX: {e}[/]")
            return {}

        # 2. Clear GAP_EVIDENCE data rows and rewrite header with all columns
        try:
            ws_evidence = self._pop._get_worksheet(GAP_EVIDENCE_TAB)
            row_count = ws_evidence.row_count
            if row_count > 1:
                ws_evidence.batch_clear([f"A2:ZZ{row_count}"])
                console.print("  [dim]GAP_EVIDENCE data cleared[/]")
            # Write full header row (includes Module 6 confidence columns)
            end_col = _col_letter(len(GAP_EVIDENCE_COLUMNS) - 1)
            ws_evidence.update(
                f"A1:{end_col}1",
                [GAP_EVIDENCE_COLUMNS],
                value_input_option="USER_ENTERED",
            )
            console.print(f"  [dim]GAP_EVIDENCE header written ({len(GAP_EVIDENCE_COLUMNS)} columns)[/]")
            # Invalidate cached next-row since we cleared data
            self._pop.invalidate_next_row(GAP_EVIDENCE_TAB)
            time.sleep(SHEETS_WRITE_DELAY)
        except Exception as e:
            console.print(f"  [red]Failed to clear GAP_EVIDENCE: {e}[/]")
            return {}

        # 3. Populate GAP_MATRIX col A with gap_ids from GAP_TRACKER,
        #    col B = "100.0%", col C = "Open" (initial state)
        all_gaps = self._get_all_gaps_from_tracker()
        if all_gaps:
            rows = [[g["gap_id"], "100.0%", "Open"] for g in all_gaps]
            ws_matrix.update(
                f"A2:C{1 + len(rows)}",
                rows,
                value_input_option="USER_ENTERED",
            )
            console.print(f"  [dim]Populated {len(rows)} gap rows in GAP_MATRIX[/]")
            time.sleep(SHEETS_WRITE_DELAY)
        else:
            console.print("  [yellow]No gaps found in GAP_TRACKER[/]")
            return {}

        # 4. Invalidate cache
        self._matrix_cache = None

        console.print("\n  [bold cyan]Rerunning gap analysis for all papers...[/]\n")

        # 5. Reprocess all extraction JSONs
        return self.analyze_all_missing(extraction_dir=ext_dir)

    def _sync_gap_rows(self) -> None:
        """
        Ensure GAP_MATRIX column A has all gaps from GAP_TRACKER.

        When new gaps are created by a paper, they exist in GAP_TRACKER but may not
        have rows in GAP_MATRIX yet. This method adds missing gap rows with initial
        values (100% remaining, Open state).
        """
        all_gaps = self._get_all_gaps_from_tracker()
        matrix = self._read_matrix()
        existing_gap_ids = set(matrix["gap_ids"])

        new_gaps = [g for g in all_gaps if g["gap_id"] not in existing_gap_ids]
        if not new_gaps:
            return

        try:
            ws = self._pop._get_worksheet(GAP_MATRIX_TAB)
            # Append new rows after existing data
            start_row = len(matrix["gap_ids"]) + 2  # 1-indexed, skip header
            rows = [[g["gap_id"], "100.0%", "Open"] for g in new_gaps]
            ws.update(
                f"A{start_row}:C{start_row + len(rows) - 1}",
                rows,
                value_input_option="USER_ENTERED",
            )
            console.print(
                f"  [dim]Synced {len(new_gaps)} new gap row(s) to GAP_MATRIX[/]"
            )
            # Invalidate cache since we added rows
            self._matrix_cache = None
            time.sleep(SHEETS_WRITE_DELAY)
        except Exception as e:
            console.print(f"  [red]Gap row sync failed: {e}[/]")

    def analyze_paper(self, paper_id: str, extraction: dict, source: str = "main") -> dict:
        """
        Evaluate one paper against all open gaps using two-phase analysis.

        Args:
            paper_id: The paper identifier
            extraction: Full extraction dict (12 sections)
            source: "main" (original pipeline) or "discovery" (auto pipeline)

        Returns:
            {"written": N, "skipped_resolved": N, "skipped_irrelevant": N,
             "total_gaps": N, "assessments": [...], "gaps_newly_resolved": [...]}
        """
        self._pop._ensure_connected()

        # Ensure GAP_MATRIX has rows for all gaps in GAP_TRACKER
        self._sync_gap_rows()

        # Guard: overwrite any manual formulas in column B with correct values
        self._clear_column_b_formulas()

        result = {
            "written": 0,
            "skipped_resolved": 0,
            "skipped_irrelevant": 0,
            "total_gaps": 0,
            "assessments": [],
            "gaps_newly_resolved": [],
        }

        # Check if paper column already exists in matrix
        matrix = self._read_matrix()
        if paper_id in matrix["paper_ids"]:
            console.print(f"  [dim]{paper_id} already in GAP_MATRIX — skipping[/]")
            return result

        # Get open gaps (Pct_Remaining >= threshold)
        all_gaps = self._get_all_gaps_from_tracker()
        if not all_gaps:
            console.print("  [yellow]No gaps found in GAP_TRACKER[/]")
            return result

        result["total_gaps"] = len(all_gaps)

        # Pre-filter: skip resolved gaps
        open_gaps = []
        for gap in all_gaps:
            gid = gap["gap_id"]
            pct = matrix["pct_remaining"].get(gid, 100.0)
            if pct >= RESOLVED_THRESHOLD:
                open_gaps.append(gap)
            else:
                result["skipped_resolved"] += 1

        if not open_gaps:
            console.print("  [green]All gaps are resolved! Nothing to analyze.[/]")
            self._write_empty_column(paper_id, matrix)
            return result

        # Filter out Niche gaps (tracked in GAP_TRACKER but excluded from matrix)
        # Only filter if tiers are populated (backward compat: empty tier = Core)
        niche_count = sum(1 for g in open_gaps if g.get("tier") == TIER_NICHE)
        if niche_count:
            open_gaps = [g for g in open_gaps if g.get("tier", "") != TIER_NICHE]
            result["skipped_niche"] = niche_count

        if not open_gaps:
            console.print("  [dim]All open gaps are Niche — skipping analysis[/]")
            self._write_empty_column(paper_id, matrix)
            return result

        niche_note = f", {niche_count} niche" if niche_count else ""
        console.print(
            f"  [bold]{len(open_gaps)}[/] open gaps to screen "
            f"([dim]{result['skipped_resolved']} resolved{niche_note}, skipped[/])"
        )

        paper_context = self._build_paper_context(extraction)

        # ── Phase 1: Quick Relevance Screen (Sonnet) ──
        relevant_gap_ids = self._screen_relevance(paper_id, paper_context, open_gaps)

        if not relevant_gap_ids:
            console.print("  [dim]No relevant gaps found — writing zero column[/]")
            self._write_empty_column(paper_id, matrix)
            result["skipped_irrelevant"] = len(open_gaps)
            return result

        relevant_gaps = [g for g in open_gaps if g["gap_id"] in relevant_gap_ids]
        result["skipped_irrelevant"] = len(open_gaps) - len(relevant_gaps)

        console.print(
            f"  Phase 1: [bold cyan]{len(relevant_gaps)}[/] potentially relevant gaps "
            f"([dim]{result['skipped_irrelevant']} screened out[/])"
        )

        # ── Phase 2: Deep History-Aware Analysis (Opus) ──
        assessments = self._deep_analyze(
            paper_id, paper_context, relevant_gaps, matrix
        )

        if not assessments:
            console.print("  [red]Deep analysis returned no results[/]")
            self._write_empty_column(paper_id, matrix)
            return result

        result["assessments"] = assessments

        # ── Log full reasoning locally (untruncated) ──
        _log_reasoning(paper_id, assessments)

        # ── Phase 3: Write Results + Update State ──
        write_result = self._write_results(paper_id, assessments, matrix, source)
        result["written"] = write_result["written"]
        result["gaps_newly_resolved"] = write_result["newly_resolved"]

        # Show summary
        non_zero = [a for a in assessments if a.get("pct_eliminated", 0) > 0]
        console.print(
            f"  [bold green]Results:[/] {len(non_zero)} gaps affected, "
            f"{result['written']} evidence rows written"
        )
        if result["gaps_newly_resolved"]:
            console.print(
                f"  [bold yellow]Newly resolved gaps:[/] "
                f"{', '.join(result['gaps_newly_resolved'])}"
            )

        # Show top impacts
        top = sorted(assessments, key=lambda a: a.get("pct_eliminated", 0), reverse=True)[:5]
        for a in top:
            pct = a.get("pct_eliminated", 0)
            if pct > 0:
                console.print(
                    f"    {a['gap_id']}: [cyan]{pct}%[/] eliminated — "
                    f"{a.get('aspect_addressed', '')[:60]}"
                )

        return result

    def retroactive_analyze(
        self,
        new_gap_ids: list[str],
        current_paper_id: str = "",
        extraction_dir: Path = None,
    ) -> dict:
        """
        Check whether previously-analyzed papers address newly-created gaps.

        When Paper N introduces new gaps, this method scans Papers 1..N-1
        (from their extraction JSONs) to see if any of them already address
        these new gaps. Uses the same two-phase Sonnet+Opus flow.

        Args:
            new_gap_ids: Gap IDs just created by the current paper.
            current_paper_id: Paper that created these gaps (excluded from scan).
            extraction_dir: Dir with extraction JSONs. Defaults to EXTRACTIONS_DIR.

        Returns:
            {"papers_scanned": N, "papers_relevant": N, "evidence_written": N,
             "gaps_newly_resolved": [...], "per_paper": [...]}
        """
        ext_dir = extraction_dir or EXTRACTIONS_DIR
        result = {
            "papers_scanned": 0,
            "papers_relevant": 0,
            "evidence_written": 0,
            "gaps_newly_resolved": [],
            "per_paper": [],
        }

        if not new_gap_ids:
            return result

        self._pop._ensure_connected()

        # Read the matrix to know which papers have columns
        matrix = self._read_matrix()
        papers_in_matrix = set(matrix["paper_ids"])

        # Get the new gaps from the tracker (need full gap data for prompts)
        all_gaps = self._get_all_gaps_from_tracker()
        new_gaps = [g for g in all_gaps if g["gap_id"] in set(new_gap_ids)]

        if not new_gaps:
            console.print("  [dim]Retroactive: no matching gaps found in tracker[/]")
            return result

        # Filter: only gaps that are still open (above resolved threshold)
        open_new_gaps = []
        for gap in new_gaps:
            gid = gap["gap_id"]
            pct = matrix["pct_remaining"].get(gid, 100.0)
            if pct >= RESOLVED_THRESHOLD:
                open_new_gaps.append(gap)

        if not open_new_gaps:
            console.print("  [dim]Retroactive: all new gaps already resolved[/]")
            return result

        console.print(
            f"\n  [bold magenta]Retroactive Analysis[/]: "
            f"{len(open_new_gaps)} new gaps vs previously-analyzed papers"
        )

        # Load all extraction JSONs for papers already in the matrix
        old_papers = []
        for ext_file in sorted(ext_dir.glob("*.json")):
            if "_metadata" in ext_file.name:
                continue
            try:
                with open(ext_file) as f:
                    extraction = json.load(f)
                pid = extraction.get("paper_id", "")
                if not pid:
                    continue
                # Only papers already in the matrix (already analyzed)
                # and not the paper that just created these gaps
                if pid in papers_in_matrix and pid != current_paper_id:
                    old_papers.append((pid, extraction))
            except Exception:
                continue

        if not old_papers:
            console.print("  [dim]Retroactive: no prior papers to scan[/]")
            return result

        console.print(
            f"  Scanning {len(old_papers)} prior papers against "
            f"{len(open_new_gaps)} new gaps..."
        )

        for i, (pid, extraction) in enumerate(old_papers, 1):
            result["papers_scanned"] += 1
            paper_context = self._build_paper_context(extraction)

            # Phase 1: Sonnet screen — does this old paper touch any new gaps?
            relevant_ids = self._screen_relevance(pid, paper_context, open_new_gaps)

            if not relevant_ids:
                continue

            relevant_gaps = [g for g in open_new_gaps if g["gap_id"] in relevant_ids]
            if not relevant_gaps:
                continue

            result["papers_relevant"] += 1
            console.print(
                f"  [{i}/{len(old_papers)}] [cyan]{pid}[/]: "
                f"{len(relevant_gaps)} potentially relevant new gap(s)"
            )

            # Refresh matrix cache to get latest pct_remaining
            self._matrix_cache = None
            matrix = self._read_matrix()

            # Phase 2: Opus deep analysis
            assessments = self._deep_analyze(pid, paper_context, relevant_gaps, matrix)

            if not assessments:
                continue

            # Filter to non-zero contributions
            non_zero = [a for a in assessments if a.get("pct_eliminated", 0) > 0]
            if not non_zero:
                continue

            # Write results: update existing paper column cells + evidence rows
            write_result = self._write_retroactive_results(
                pid, assessments, matrix, "retroactive"
            )
            result["evidence_written"] += write_result["written"]
            result["gaps_newly_resolved"].extend(write_result["newly_resolved"])
            result["per_paper"].append({
                "paper_id": pid,
                "gaps_assessed": len(assessments),
                "evidence_written": write_result["written"],
                "newly_resolved": write_result["newly_resolved"],
            })

            for a in non_zero:
                console.print(
                    f"    {a['gap_id']}: [cyan]{a.get('pct_eliminated', 0)}%[/] "
                    f"eliminated — {a.get('aspect_addressed', '')[:60]}"
                )

        console.print(
            f"\n  [bold magenta]Retroactive complete[/]: "
            f"{result['papers_scanned']} scanned, "
            f"{result['papers_relevant']} relevant, "
            f"{result['evidence_written']} evidence rows"
        )
        if result["gaps_newly_resolved"]:
            console.print(
                f"  [bold yellow]Newly resolved: "
                f"{', '.join(result['gaps_newly_resolved'])}[/]"
            )

        return result

    def _write_retroactive_results(
        self,
        paper_id: str,
        assessments: list[dict],
        matrix: dict,
        source: str,
    ) -> dict:
        """
        Write retroactive evidence: update cells in an EXISTING paper column
        and append evidence rows. Does NOT create a new column.

        This differs from _write_results() which creates a new column.
        Here the paper already has a column — we just fill in cells for new gaps.
        """
        result = {"written": 0, "newly_resolved": []}

        # Find the paper's column index in the matrix
        if paper_id not in matrix["paper_ids"]:
            console.print(f"  [red]Retroactive: {paper_id} not in matrix, skipping[/]")
            return result

        paper_col_offset = matrix["paper_ids"].index(paper_id)
        paper_col_idx = 3 + paper_col_offset  # 0-indexed; cols A=gap_id, B=pct, C=state, D+=papers
        col_letter = _col_letter(paper_col_idx)

        assessment_map = {a["gap_id"]: a for a in assessments if isinstance(a, dict) and "gap_id" in a}
        assessed_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        pct_updates = {}
        state_updates = {}
        cell_updates = []  # (row_number, value) for the paper column

        for i, gid in enumerate(matrix["gap_ids"]):
            a = assessment_map.get(gid)
            if not a:
                continue

            pct_eliminated = min(100, max(0, int(a.get("pct_eliminated", 0))))
            if pct_eliminated == 0:
                continue

            row_num = i + 2  # 1-indexed, skip header

            # Check if this cell already has a value (don't overwrite)
            existing_score = matrix["scores"].get((gid, paper_id), "")
            if existing_score:
                continue  # Already assessed this gap for this paper

            cell_updates.append((row_num, f"{pct_eliminated}%"))

            old_remaining = matrix["pct_remaining"].get(gid, 100.0)
            new_remaining = old_remaining * (1 - pct_eliminated / 100)
            new_remaining = round(max(0, new_remaining), 1)
            pct_updates[gid] = new_remaining
            state_updates[gid] = _derive_gap_state(new_remaining)

            if old_remaining >= RESOLVED_THRESHOLD and new_remaining < RESOLVED_THRESHOLD:
                result["newly_resolved"].append(gid)

        # Write cell updates to the existing paper column
        if cell_updates:
            try:
                ws = self._pop._get_worksheet(GAP_MATRIX_TAB)
                from gspread import Cell
                cells = [
                    Cell(row=row_num, col=paper_col_idx + 1, value=value)
                    for row_num, value in cell_updates
                ]
                ws.update_cells(cells)
                console.print(
                    f"  [dim]Retroactive: updated {len(cells)} cells in "
                    f"column {col_letter} ({paper_id})[/]"
                )
            except Exception as e:
                console.print(f"  [red]Retroactive column update failed: {e}[/]")
                return result

        # Write evidence rows
        for gid, a in assessment_map.items():
            pct_eliminated = min(100, max(0, int(a.get("pct_eliminated", 0))))
            if pct_eliminated == 0:
                continue

            # Skip if this cell was already present
            existing_score = matrix["scores"].get((gid, paper_id), "")
            if existing_score:
                continue

            old_remaining = matrix["pct_remaining"].get(gid, 100.0)
            new_remaining = pct_updates.get(gid, old_remaining)

            # Get next row number for formula references
            next_row = self._pop._get_next_row(GAP_EVIDENCE_TAB)

            evidence_row = {
                "Gap_ID": gid,
                "Paper_ID": paper_id,
                "Pct_Eliminated": f"{pct_eliminated}%",
                "Pct_Remaining_Before": f"{old_remaining:.1f}%",
                "Pct_Remaining_After": f"=D{next_row}*(1-C{next_row}/100)",
                "Aspect_Addressed": str(a.get("aspect_addressed", ""))[:2000],
                "What_Still_Remains": str(a.get("what_still_remains", ""))[:2000],
                "Reasoning": str(a.get("reasoning", ""))[:2000],
                "Assessed_By": "Claude Opus 4.6 (Retroactive)",
                "Assessed_At": assessed_at,
                "Source": source,
            }

            # Add confidence scores (graceful if Claude omits them)
            conf = _extract_confidence(a)
            evidence_row.update({
                "Confidence_Methodological": conf.get("methodological", ""),
                "Confidence_Sample": conf.get("sample", ""),
                "Confidence_Variables": conf.get("variables", ""),
                "Confidence_Directness": conf.get("directness", ""),
                "Confidence_Overall": conf.get("overall", ""),
                "Confidence_Tier": conf.get("tier", ""),
            })

            try:
                self._pop._write_row_by_headers(GAP_EVIDENCE_TAB, evidence_row)
                result["written"] += 1
                time.sleep(SHEETS_WRITE_DELAY)
            except Exception as e:
                console.print(f"  [red]Retroactive evidence write failed for {gid}: {e}[/]")

        # Update Pct_Remaining and Gap_State
        if pct_updates:
            self._update_pct_remaining(pct_updates, state_updates, matrix)

        # Update GAP_TRACKER
        affected_gap_ids = list(pct_updates.keys())
        if affected_gap_ids:
            self._update_gap_tracker(affected_gap_ids, pct_updates, state_updates)

        # Invalidate cache
        self._matrix_cache = None

        return result

    def retroactive_analyze_all_uncovered(self, extraction_dir: Path = None) -> dict:
        """
        Find all gaps with zero evidence rows in GAP_EVIDENCE and run
        retroactive analysis against all papers. Standalone CLI mode.
        """
        ext_dir = extraction_dir or EXTRACTIONS_DIR
        self._pop._ensure_connected()

        # Find gaps with no evidence rows
        matrix = self._read_matrix()
        all_gap_ids = set(matrix["gap_ids"])

        # Read evidence to find which gaps have at least one row
        try:
            ws = self._pop._get_worksheet(GAP_EVIDENCE_TAB)
            evidence_rows = ws.get_all_values()
            covered_gaps = set()
            for row in evidence_rows[1:]:
                if row and row[0].strip():
                    covered_gaps.add(row[0].strip())
        except Exception:
            covered_gaps = set()

        uncovered = all_gap_ids - covered_gaps
        if not uncovered:
            console.print("  [green]All gaps have evidence rows — nothing to backfill[/]")
            return {"gaps_found": 0}

        console.print(
            f"\n  [bold]Found {len(uncovered)} gaps with zero evidence rows[/]"
        )

        return self.retroactive_analyze(
            new_gap_ids=list(uncovered),
            current_paper_id="",
            extraction_dir=ext_dir,
        )

    def analyze_all_missing(self, extraction_dir: Path = None) -> dict:
        """
        Scan extraction JSONs, analyze papers not yet in the matrix.

        Args:
            extraction_dir: Directory containing extraction JSONs.
                            Defaults to EXTRACTIONS_DIR (main pipeline).
        """
        ext_dir = extraction_dir or EXTRACTIONS_DIR
        totals = {
            "written": 0, "skipped_resolved": 0, "skipped_irrelevant": 0,
            "papers_processed": 0, "papers_skipped": 0, "assessments": [],
        }

        extraction_files = sorted(ext_dir.glob("*.json"))
        # Filter out metadata-only files
        extraction_files = [f for f in extraction_files if "_metadata" not in f.name]

        if not extraction_files:
            console.print(f"  [yellow]No extraction files found in {ext_dir}[/]")
            return totals

        self._pop._ensure_connected()
        matrix = self._read_matrix()
        existing_papers = set(matrix["paper_ids"])

        # Find papers not yet in matrix
        papers_to_analyze = []
        for ext_file in extraction_files:
            try:
                with open(ext_file) as f:
                    extraction = json.load(f)
                pid = extraction.get("paper_id", "")
                if not pid:
                    continue
                if pid in existing_papers:
                    totals["papers_skipped"] += 1
                    continue
                papers_to_analyze.append((pid, extraction))
            except Exception as e:
                console.print(f"  [red]Error reading {ext_file.name}: {e}[/]")

        if not papers_to_analyze:
            console.print("  [green]All papers already in GAP_MATRIX[/]")
            return totals

        console.print(
            f"\n  [bold]Papers to analyze: {len(papers_to_analyze)}[/] "
            f"({totals['papers_skipped']} already done)\n"
        )

        source = "discovery" if ext_dir != EXTRACTIONS_DIR else "main"

        for i, (pid, extraction) in enumerate(papers_to_analyze, 1):
            console.print(f"\n  [{i}/{len(papers_to_analyze)}] [bold cyan]{pid}[/]")
            result = self.analyze_paper(pid, extraction, source=source)
            totals["written"] += result["written"]
            totals["skipped_resolved"] += result["skipped_resolved"]
            totals["skipped_irrelevant"] += result["skipped_irrelevant"]
            totals["papers_processed"] += 1
            totals["assessments"].extend(result["assessments"])

        return totals

    def show_matrix_status(self) -> None:
        """Display matrix stats dashboard."""
        self._pop._ensure_connected()
        matrix = self._read_matrix()

        n_gaps = len(matrix["gap_ids"])
        n_papers = len(matrix["paper_ids"])

        # Count states
        state_counts = {"Open": 0, "Under Investigation": 0, "Partially Resolved": 0, "Resolved": 0}
        for gid in matrix["gap_ids"]:
            pct = matrix["pct_remaining"].get(gid, 100.0)
            state = _derive_gap_state(pct)
            state_counts[state] = state_counts.get(state, 0) + 1

        # Display
        content = Text()
        content.append("GAP MATRIX STATUS\n\n", style="bold magenta")
        content.append(f"Total gaps: {n_gaps}\n")
        content.append(f"Papers analyzed: {n_papers}\n\n")
        content.append("Gap States:\n")

        style_map = {
            "Open": "red", "Under Investigation": "yellow",
            "Partially Resolved": "cyan", "Resolved": "green",
        }
        for state, count in state_counts.items():
            pct = (count / n_gaps * 100) if n_gaps > 0 else 0
            bar = "#" * int(pct / 2)
            content.append(
                f"  {state:22s} {count:3d} ({pct:5.1f}%) {bar}\n",
                style=style_map.get(state, "white"),
            )

        # Average remaining
        if matrix["pct_remaining"]:
            avg_remaining = sum(matrix["pct_remaining"].values()) / len(matrix["pct_remaining"])
            content.append(f"\nAverage gap remaining: {avg_remaining:.1f}%\n")

        # Most-covered gaps (lowest remaining)
        if matrix["pct_remaining"]:
            sorted_gaps = sorted(matrix["pct_remaining"].items(), key=lambda x: x[1])
            content.append("\nMost covered gaps:\n")
            for gid, pct in sorted_gaps[:5]:
                state = _derive_gap_state(pct)
                content.append(f"  {gid}: {pct:.1f}% remaining [{state}]\n")

        console.print(Panel(content, border_style="magenta", box=box.ROUNDED))

    def dry_run(self, extraction_dir: Path = None) -> None:
        """Preview what would be analyzed."""
        ext_dir = extraction_dir or EXTRACTIONS_DIR
        self._pop._ensure_connected()
        matrix = self._read_matrix()

        extraction_files = sorted(ext_dir.glob("*.json"))
        extraction_files = [f for f in extraction_files if "_metadata" not in f.name]

        existing_papers = set(matrix["paper_ids"])
        n_open = sum(1 for pct in matrix["pct_remaining"].values() if pct >= RESOLVED_THRESHOLD)
        n_resolved = len(matrix["pct_remaining"]) - n_open

        console.print("\n  [bold]Gap Matrix Analyzer — Dry Run[/]\n")
        console.print(f"  Gaps in matrix: {len(matrix['gap_ids'])} ({n_open} open, {n_resolved} resolved)")
        console.print(f"  Papers in matrix: {len(matrix['paper_ids'])}")
        console.print(f"  Extraction files: {len(extraction_files)}\n")

        pending_count = 0
        for ext_file in extraction_files:
            try:
                with open(ext_file) as f:
                    extraction = json.load(f)
                pid = extraction.get("paper_id", "")
                if not pid:
                    continue
                if pid in existing_papers:
                    status = "[green]done[/]"
                else:
                    status = "[yellow]pending[/]"
                    pending_count += 1
                console.print(f"    {pid:40s} {status}")
            except Exception:
                continue

        console.print(f"\n  Papers to analyze: {pending_count}")
        console.print(f"  Open gaps per paper: ~{n_open}")
        console.print(f"  Estimated Claude calls per paper: 1 Sonnet + 1 Opus\n")

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: RELEVANCE SCREEN (Sonnet)
    # ═══════════════════════════════════════════════════════════

    def _screen_relevance(
        self, paper_id: str, paper_context: str, open_gaps: list[dict]
    ) -> set[str]:
        """
        Quick screen: which gaps might this paper be relevant to?
        Uses Claude Sonnet for speed. Returns set of gap IDs.
        """
        gap_summary = "\n".join(
            f'{g["gap_id"]} [{g["gap_type"]}]: "{g["gap_statement"][:120]}"'
            for g in open_gaps
        )

        user_prompt = (
            f"{paper_context}\n\n---\n\n"
            f"RESEARCH GAPS ({len(open_gaps)} total):\n{gap_summary}\n\n---\n\n"
            f"Which gap IDs might this paper be relevant to? Return JSON array of gap IDs."
        )

        stdout = self._run_claude(
            prompt=user_prompt,
            system=SCREEN_SYSTEM_PROMPT,
            model=SONNET_MODEL,
            timeout=SCREEN_TIMEOUT,
            label=f"Screening {paper_id}",
        )

        if not stdout:
            # Fallback: treat all gaps as potentially relevant
            console.print("  [yellow]Screen failed — treating all gaps as relevant[/]")
            return {g["gap_id"] for g in open_gaps}

        # Parse JSON array of gap IDs
        parsed = self._parse_json_output(stdout)
        if parsed is None:
            console.print("  [yellow]Screen parse failed — treating all gaps as relevant[/]")
            return {g["gap_id"] for g in open_gaps}

        if isinstance(parsed, list):
            # Could be list of strings or list of dicts
            gap_ids = set()
            for item in parsed:
                if isinstance(item, str):
                    gap_ids.add(item)
                elif isinstance(item, dict) and "gap_id" in item:
                    gap_ids.add(item["gap_id"])
            return gap_ids

        return {g["gap_id"] for g in open_gaps}

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: DEEP ANALYSIS (Opus, history-aware)
    # ═══════════════════════════════════════════════════════════

    def _deep_analyze(
        self,
        paper_id: str,
        paper_context: str,
        relevant_gaps: list[dict],
        matrix: dict,
    ) -> list[dict]:
        """
        Deep percentage-elimination analysis with coverage history.
        Tier-aware: Core gaps → Opus, Supporting gaps → Sonnet.
        Batches gaps if needed. Returns list of assessment dicts.
        """
        # Split gaps by tier for model selection
        core_gaps = [g for g in relevant_gaps if g.get("tier", "") != TIER_SUPPORTING]
        supporting_gaps = [g for g in relevant_gaps if g.get("tier", "") == TIER_SUPPORTING]

        all_assessments = []

        # Analyze Core gaps with Opus (full deep analysis)
        if core_gaps:
            console.print(
                f"  Phase 2a: [bold blue]{len(core_gaps)} Core/unclassified gaps[/] → Opus"
            )
            all_assessments.extend(
                self._deep_analyze_batch_group(paper_id, paper_context, core_gaps, matrix, CLAUDE_MODEL)
            )

        # Analyze Supporting gaps with Sonnet (lighter analysis)
        if supporting_gaps:
            console.print(
                f"  Phase 2b: [bold yellow]{len(supporting_gaps)} Supporting gaps[/] → Sonnet"
            )
            all_assessments.extend(
                self._deep_analyze_batch_group(paper_id, paper_context, supporting_gaps, matrix, SONNET_MODEL)
            )

        return all_assessments

    def _deep_analyze_batch_group(
        self,
        paper_id: str,
        paper_context: str,
        gaps: list[dict],
        matrix: dict,
        model: str,
    ) -> list[dict]:
        """Run deep analysis on a group of gaps using the specified model."""
        all_assessments = []
        batches = [
            gaps[i:i + GAP_BATCH_SIZE]
            for i in range(0, len(gaps), GAP_BATCH_SIZE)
        ]

        for batch_idx, batch in enumerate(batches):
            if len(batches) > 1:
                console.print(f"    Batch {batch_idx + 1}/{len(batches)} ({len(batch)} gaps)")

            gap_prompt_parts = []
            for gap in batch:
                gid = gap["gap_id"]
                pct_remaining = matrix["pct_remaining"].get(gid, 100.0)
                history = self._read_gap_history(gid)

                part = self._format_gap_for_deep_analysis(gap, pct_remaining, history)
                gap_prompt_parts.append(part)

            gap_text = "\n---\n\n".join(gap_prompt_parts)

            user_prompt = (
                f"{paper_context}\n\n"
                f"{'=' * 60}\n"
                f"GAPS TO EVALUATE ({len(batch)} gaps):\n\n"
                f"{gap_text}\n\n"
                f"{'=' * 60}\n"
                f"Return a JSON array with one object per gap.\n"
                f"Fields: gap_id, pct_eliminated (0-100), aspect_addressed, "
                f"what_still_remains, reasoning"
            )

            assessments = None
            for attempt in range(MAX_RETRIES + 1):
                if attempt > 0:
                    console.print(f"  [yellow]Retry {attempt}/{MAX_RETRIES} in {RETRY_DELAY}s...[/]")
                    time.sleep(RETRY_DELAY)

                stdout = self._run_claude(
                    prompt=user_prompt,
                    system=DEEP_SYSTEM_PROMPT,
                    model=model,
                    timeout=DEEP_TIMEOUT,
                    label=f"Deep analysis {paper_id} (batch {batch_idx + 1})",
                )

                if stdout:
                    assessments = self._parse_json_output(stdout)
                    if assessments is not None:
                        break

            if assessments:
                valid = [a for a in assessments if isinstance(a, dict) and "gap_id" in a]
                all_assessments.extend(valid)
            else:
                console.print(f"  [red]Batch {batch_idx + 1} failed after all retries[/]")

        return all_assessments

    def _format_gap_for_deep_analysis(
        self, gap: dict, pct_remaining: float, history: list[dict]
    ) -> str:
        """Format a single gap with its history for the deep analysis prompt."""
        lines = [
            f'GAP: {gap["gap_id"]} [{gap["gap_type"]}]',
            f'"{gap["gap_statement"]}"',
        ]

        # Include tier context if available
        tier = gap.get("tier", "")
        if tier:
            lines.append(f"TIER: {tier}")

        lines.append(f"")
        lines.append(f"REMAINING: {pct_remaining:.1f}% of this gap is still open.")

        if history:
            lines.append("")
            lines.append("COVERAGE HISTORY (what previous papers contributed):")
            for h in history:
                pid = h.get("Paper_ID", "?")
                pct = h.get("Pct_Eliminated", "?")
                aspect = h.get("Aspect_Addressed", "")
                remains = h.get("What_Still_Remains", "")
                conf_tier = h.get("Confidence_Tier", "")

                conf_str = f", confidence: {conf_tier}" if conf_tier else ""
                lines.append(f"  --- {pid} (eliminated {pct}%{conf_str}) ---")
                if aspect:
                    lines.append(f"  What it addressed: {aspect}")
                if remains:
                    lines.append(f"  What it left open: {remains}")

            # What still remains (from the latest history entry)
            latest = history[-1] if history else {}
            what_remains = latest.get("What_Still_Remains", "")
            if what_remains:
                lines.append("")
                lines.append(f"CURRENT STATE — what's still open ({pct_remaining:.1f}%):")
                lines.append(f"  {what_remains}")
        else:
            lines.append("")
            lines.append("No previous papers have addressed this gap. The full gap is open.")

        lines.append("")
        lines.append(
            f"QUESTION: What percentage of the REMAINING {pct_remaining:.1f}% "
            f"does this new paper eliminate?"
        )

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: WRITE RESULTS
    # ═══════════════════════════════════════════════════════════

    def _write_results(
        self, paper_id: str, assessments: list[dict], matrix: dict, source: str
    ) -> dict:
        """
        Write paper column to GAP_MATRIX, evidence rows to GAP_EVIDENCE,
        and update Pct_Remaining + Gap_State.
        """
        result = {"written": 0, "newly_resolved": []}

        # Index assessments by gap_id
        assessment_map = {}
        for a in assessments:
            gid = a.get("gap_id", "")
            if gid and gid not in assessment_map:
                assessment_map[gid] = a

        assessed_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Build column values (one per gap row)
        column_values = []
        pct_updates = {}  # gap_id -> new pct_remaining
        state_updates = {}  # gap_id -> new state

        for gid in matrix["gap_ids"]:
            a = assessment_map.get(gid)
            pct_eliminated = 0
            if a:
                pct_eliminated = min(100, max(0, int(a.get("pct_eliminated", 0))))

            column_values.append(f"{pct_eliminated}%" if pct_eliminated > 0 else "")

            if pct_eliminated > 0:
                old_remaining = matrix["pct_remaining"].get(gid, 100.0)
                new_remaining = old_remaining * (1 - pct_eliminated / 100)
                new_remaining = round(max(0, new_remaining), 1)
                pct_updates[gid] = new_remaining
                state_updates[gid] = _derive_gap_state(new_remaining)

                # Check if newly resolved
                if old_remaining >= RESOLVED_THRESHOLD and new_remaining < RESOLVED_THRESHOLD:
                    result["newly_resolved"].append(gid)

        # ── Write paper column to GAP_MATRIX ──
        self._write_paper_column(paper_id, column_values, matrix)

        # ── Write evidence rows (non-zero only) ──
        for gid, a in assessment_map.items():
            pct_eliminated = min(100, max(0, int(a.get("pct_eliminated", 0))))
            if pct_eliminated == 0:
                continue

            old_remaining = matrix["pct_remaining"].get(gid, 100.0)
            new_remaining = pct_updates.get(gid, old_remaining)

            # Get next row number for formula references (before _write_row_by_headers advances it)
            next_row = self._pop._get_next_row(GAP_EVIDENCE_TAB)

            evidence_row = {
                "Gap_ID": gid,
                "Paper_ID": paper_id,
                "Pct_Eliminated": f"{pct_eliminated}%",
                "Pct_Remaining_Before": f"{old_remaining:.1f}%",
                "Pct_Remaining_After": f"=D{next_row}*(1-C{next_row}/100)",
                "Aspect_Addressed": str(a.get("aspect_addressed", ""))[:2000],
                "What_Still_Remains": str(a.get("what_still_remains", ""))[:2000],
                "Reasoning": str(a.get("reasoning", ""))[:2000],
                "Assessed_By": f"Claude Opus 4.6 ({'Auto-Discovery' if source == 'discovery' else 'Main Pipeline'})",
                "Assessed_At": assessed_at,
                "Source": source,
            }

            # Add confidence scores (graceful if Claude omits them)
            conf = _extract_confidence(a)
            evidence_row.update({
                "Confidence_Methodological": conf.get("methodological", ""),
                "Confidence_Sample": conf.get("sample", ""),
                "Confidence_Variables": conf.get("variables", ""),
                "Confidence_Directness": conf.get("directness", ""),
                "Confidence_Overall": conf.get("overall", ""),
                "Confidence_Tier": conf.get("tier", ""),
            })

            try:
                self._pop._write_row_by_headers(GAP_EVIDENCE_TAB, evidence_row)
                result["written"] += 1
                time.sleep(SHEETS_WRITE_DELAY)
            except Exception as e:
                console.print(f"  [red]Evidence write failed for {gid}: {e}[/]")

        # ── Update Pct_Remaining and Gap_State in matrix ──
        if pct_updates:
            self._update_pct_remaining(pct_updates, state_updates, matrix)

        # ── Update GAP_TRACKER feedback ──
        affected_gap_ids = list(pct_updates.keys())
        if affected_gap_ids:
            self._update_gap_tracker(affected_gap_ids, pct_updates, state_updates)

        # Invalidate matrix cache so next paper reads fresh data
        self._matrix_cache = None

        return result

    @retry_on_api_error()
    def _write_paper_column(
        self, paper_id: str, column_values: list[str], matrix: dict
    ) -> None:
        """Add a new paper column to GAP_MATRIX, expanding the sheet if needed."""
        ws = self._pop._get_worksheet(GAP_MATRIX_TAB)

        # New column index = number of existing columns + 1 (1-indexed)
        # Cols: A=Gap_ID, B=Pct_Remaining, C=Gap_State, D+=papers
        new_col_idx = 3 + len(matrix["paper_ids"])  # 0-indexed → col D is index 3
        col_letter = _col_letter(new_col_idx)

        # Expand grid if the new column exceeds current sheet dimensions
        needed_cols = new_col_idx + 1  # 1-indexed
        if needed_cols > ws.col_count:
            # Add extra buffer (10 columns) to reduce future resizes
            ws.resize(cols=needed_cols + 10)
            time.sleep(1)

        # Write header (paper_id)
        ws.update(
            range_name=f"{col_letter}1",
            values=[[paper_id]],
        )

        # Write values (one per gap row, starting at row 2)
        if column_values:
            values_2d = [[v] for v in column_values]
            ws.update(
                range_name=f"{col_letter}2:{col_letter}{1 + len(column_values)}",
                values=values_2d,
            )

        console.print(f"  [dim]Matrix column {col_letter} written for {paper_id}[/]")

    @retry_on_api_error()
    def _update_pct_remaining(
        self, pct_updates: dict, state_updates: dict, matrix: dict
    ) -> None:
        """Batch update Pct_Remaining (col B) and Gap_State (col C)."""
        from gspread import Cell

        ws = self._pop._get_worksheet(GAP_MATRIX_TAB)
        cells = []

        for i, gid in enumerate(matrix["gap_ids"]):
            if gid in pct_updates:
                row = i + 2  # 1-indexed, skip header
                cells.append(Cell(row=row, col=2, value=f"{pct_updates[gid]:.1f}%"))
                cells.append(Cell(row=row, col=3, value=state_updates.get(gid, "")))

        if cells:
            ws.update_cells(cells, value_input_option="RAW")
            console.print(f"  [dim]Updated Pct_Remaining for {len(pct_updates)} gaps[/]")

    def _clear_column_b_formulas(self) -> int:
        """
        Detect and overwrite any formulas in GAP_MATRIX column B with correct values.

        If someone manually added formulas like =100%-SUM(D2:Z2) to column B,
        those produce incorrect (often negative) percentages. This method reads
        column B raw, detects formula cells, and replaces them with the Python-
        computed multiplicative values from the cached matrix.

        Returns: number of formula cells fixed.
        """
        try:
            ws = self._pop._get_worksheet(GAP_MATRIX_TAB)
            raw_b = ws.get("B2:B", value_render_option="FORMULA")
        except Exception as e:
            console.print(f"  [yellow]Could not read column B formulas: {e}[/]")
            return 0

        if not raw_b:
            return 0

        matrix = self._read_matrix()
        from gspread import Cell
        fixes = []
        for i, row in enumerate(raw_b):
            cell_val = row[0] if row else ""
            if isinstance(cell_val, str) and cell_val.startswith("="):
                gid = matrix["gap_ids"][i] if i < len(matrix["gap_ids"]) else None
                correct_val = matrix["pct_remaining"].get(gid, 100.0) if gid else 100.0
                fixes.append(Cell(row=i + 2, col=2, value=f"{correct_val:.1f}%"))

        if fixes:
            ws.update_cells(fixes, value_input_option="RAW")
            console.print(
                f"  [yellow]Fixed {len(fixes)} formula cell(s) in GAP_MATRIX column B[/]"
            )

        return len(fixes)

    # ═══════════════════════════════════════════════════════════
    # MATRIX & EVIDENCE I/O
    # ═══════════════════════════════════════════════════════════

    @retry_on_api_error()
    def _read_matrix(self) -> dict:
        """
        Read the GAP_MATRIX tab.
        Returns: {"gap_ids": [...], "paper_ids": [...], "pct_remaining": {gid: float}, "scores": {(gid, pid): str}}
        """
        if self._matrix_cache is not None:
            return self._matrix_cache

        try:
            ws = self._pop._get_worksheet(GAP_MATRIX_TAB)
            all_values = ws.get_all_values()
        except Exception as e:
            console.print(f"  [yellow]GAP_MATRIX tab not found or empty: {e}[/]")
            self._matrix_cache = {
                "gap_ids": [], "paper_ids": [],
                "pct_remaining": {}, "scores": {},
            }
            return self._matrix_cache

        if not all_values or len(all_values) < 1:
            self._matrix_cache = {
                "gap_ids": [], "paper_ids": [],
                "pct_remaining": {}, "scores": {},
            }
            return self._matrix_cache

        header = all_values[0]
        # Cols D+ are paper IDs
        paper_ids = [h.strip() for h in header[3:] if h.strip()]

        gap_ids = []
        pct_remaining = {}
        scores = {}

        for row in all_values[1:]:
            if not row or not row[0].strip():
                continue

            gid = row[0].strip()
            gap_ids.append(gid)

            # Col B: Pct_Remaining
            pct_str = row[1].strip().replace("%", "") if len(row) > 1 else "100"
            try:
                pct_remaining[gid] = float(pct_str)
            except ValueError:
                pct_remaining[gid] = 100.0

            # Cols D+: paper scores
            for j, pid in enumerate(paper_ids):
                cell_idx = 3 + j
                if cell_idx < len(row) and row[cell_idx].strip():
                    scores[(gid, pid)] = row[cell_idx].strip()

        self._matrix_cache = {
            "gap_ids": gap_ids,
            "paper_ids": paper_ids,
            "pct_remaining": pct_remaining,
            "scores": scores,
        }
        return self._matrix_cache

    @retry_on_api_error()
    def _read_gap_history(self, gap_id: str) -> list[dict]:
        """Read coverage history for a gap from GAP_EVIDENCE tab."""
        try:
            ws = self._pop._get_worksheet(GAP_EVIDENCE_TAB)
            all_values = ws.get_all_values()
        except Exception:
            return []

        if len(all_values) < 2:
            return []

        header = all_values[0]
        history = []
        for row in all_values[1:]:
            if len(row) < 2:
                continue
            row_dict = {header[i]: row[i] for i in range(min(len(header), len(row)))}
            if row_dict.get("Gap_ID", "").strip() == gap_id:
                history.append(row_dict)

        return history

    def _write_empty_column(self, paper_id: str, matrix: dict) -> None:
        """Write a column of empty values (paper irrelevant to all gaps)."""
        column_values = [""] * len(matrix["gap_ids"])
        self._write_paper_column(paper_id, column_values, matrix)

    # ═══════════════════════════════════════════════════════════
    # GAP TRACKER FEEDBACK
    # ═══════════════════════════════════════════════════════════

    @retry_on_api_error()
    def _update_gap_tracker(
        self,
        affected_gap_ids: list[str],
        pct_updates: dict,
        state_updates: dict,
    ) -> None:
        """
        Update GAP_TRACKER Status, Severity, Novelty based on matrix results.
        Never downgrades status or increases scores.
        """
        from gspread import Cell

        gap_id_set = set(affected_gap_ids)

        tracker_ws = self._pop._get_worksheet("GAP_TRACKER")
        tracker_header_map = self._pop._get_header_map("GAP_TRACKER")
        tracker_all = tracker_ws.get_all_values()

        if len(tracker_all) < 2:
            return

        t_gid = tracker_header_map.get("Gap_ID", 0)
        t_severity = tracker_header_map.get("Severity", 3)
        t_novelty = tracker_header_map.get("Novelty", 5)
        t_status = tracker_header_map.get("Status", 13)
        t_coverage = tracker_header_map.get("Coverage_Level", 15)
        t_coverage_notes = tracker_header_map.get("Coverage_Notes", 17)

        status_rank = {
            "Identified": 0, "Open": 0, "Under Investigation": 1,
            "Partially Resolved": 2, "Resolved": 3,
        }

        cells_to_update = []

        for row_idx, row in enumerate(tracker_all[1:], start=2):
            if len(row) <= t_gid:
                continue
            gid = row[t_gid].strip()
            if gid not in gap_id_set:
                continue

            new_pct = pct_updates.get(gid)
            new_state = state_updates.get(gid)
            if new_pct is None or new_state is None:
                continue

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

            # Map matrix state to tracker state
            tracker_state = new_state
            if tracker_state == "Open":
                tracker_state = "Identified"  # GAP_TRACKER uses "Identified" not "Open"

            # Never downgrade
            if status_rank.get(tracker_state, 0) <= status_rank.get(current_status, 0):
                continue  # No upgrade needed

            # Score adjustments based on new state
            sev_delta = 0
            nov_delta = 0
            if tracker_state == "Resolved":
                sev_delta = -3
                nov_delta = -3
            elif tracker_state == "Partially Resolved":
                sev_delta = -2
                nov_delta = -2
            elif tracker_state == "Under Investigation":
                sev_delta = -1
                nov_delta = -1

            final_severity = max(1, current_severity + sev_delta)
            final_novelty = max(1, current_novelty + nov_delta)

            notes = f"Matrix: {new_pct:.1f}% remaining → {new_state}. Severity {current_severity}→{final_severity}, Novelty {current_novelty}→{final_novelty}."

            # Coverage level mapping from matrix percentage
            if new_pct < 10:
                coverage_level = "DIRECTLY TACKLED"
            elif new_pct < 40:
                coverage_level = "SUBSTANTIALLY COVERED"
            elif new_pct < 80:
                coverage_level = "PARTIALLY ADDRESSED"
            else:
                coverage_level = "NOT ADDRESSED"

            cells_to_update.append(Cell(row=row_idx, col=t_status + 1, value=tracker_state))
            cells_to_update.append(Cell(row=row_idx, col=t_severity + 1, value=str(final_severity)))
            cells_to_update.append(Cell(row=row_idx, col=t_novelty + 1, value=str(final_novelty)))
            cells_to_update.append(Cell(row=row_idx, col=t_coverage + 1, value=coverage_level))
            cells_to_update.append(Cell(row=row_idx, col=t_coverage_notes + 1, value=notes))

        if cells_to_update:
            tracker_ws.update_cells(cells_to_update)
            n_gaps = len(cells_to_update) // 5
            console.print(f"  [green]GAP_TRACKER updated: {n_gaps} gap verdicts refreshed[/]")

    # ═══════════════════════════════════════════════════════════
    # GAP TRACKER READER
    # ═══════════════════════════════════════════════════════════

    @retry_on_api_error()
    def _get_all_gaps_from_tracker(self) -> list[dict]:
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
                "variables_needed": str(row.get("Variables_Needed", "")),
                "methodology_needed": str(row.get("Methodology_Needed", "")),
                "tier": str(row.get("Tier", "")),  # Gap taxonomy tier
            })
        return gaps

    # ═══════════════════════════════════════════════════════════
    # PAPER CONTEXT BUILDER
    # ═══════════════════════════════════════════════════════════

    def _build_paper_context(self, extraction: dict) -> str:
        """Compose paper's key sections into prompt text."""
        parts = [f"PAPER: {extraction.get('paper_id', 'unknown')}"]

        # Identification
        ident = extraction.get("1_IDENTIFICATION", {})
        if ident:
            parts.append(f"\nTITLE/CITATION: {ident.get('Full_Citation_APA7', '')}")

        # Abstract
        abstract = extraction.get("Verbatim_Abstract", "")
        if abstract:
            parts.append(f"\nABSTRACT:\n{abstract}")

        # Research Design
        rd = extraction.get("2_RESEARCH_DESIGN", {})
        if rd:
            rq = rd.get("Research_Question", "")
            if rq:
                parts.append(f"\nRESEARCH QUESTION: {rq}")
            summary = rd.get("One_Sentence_Summary", "")
            if summary:
                parts.append(f"SUMMARY: {summary}")

        # Findings
        f = extraction.get("7_FINDINGS", {})
        if f:
            parts.append("\nFINDINGS:")
            for key in ["Main_Finding", "Effect_Direction", "Coefficient_Beta",
                         "P_Value", "Economic_Significance", "Moderating_Effects_Found",
                         "Mediating_Effects_Found", "Mechanisms_Channels_Identified"]:
                val = f.get(key, "")
                if val:
                    parts.append(f"  {key}: {val}")

        # Variables
        v = extraction.get("3_VARIABLES", {})
        if v:
            parts.append("\nVARIABLES:")
            for prefix in ["DV1", "DV2", "IV1", "IV2", "IV3"]:
                name = v.get(f"{prefix}_Name", "")
                if name:
                    meas = v.get(f"{prefix}_Measurement", "")
                    parts.append(f"  {prefix}: {name}" + (f" -- {meas}" if meas else ""))
            for i in [1, 2]:
                name = v.get(f"Moderator{i}_Name", "")
                if name:
                    parts.append(f"  Moderator{i}: {name}")
                name = v.get(f"Mediator{i}_Name", "")
                if name:
                    parts.append(f"  Mediator{i}: {name}")

        # Methodology
        m = extraction.get("4_METHODOLOGY", {})
        if m:
            parts.append("\nMETHODOLOGY:")
            for key in ["Research_Design", "Estimation_Primary", "Endogeneity_Methods"]:
                val = m.get(key, "")
                if val:
                    parts.append(f"  {key}: {val}")

        # Sample
        s = extraction.get("5_SAMPLE", {})
        if s:
            parts.append("\nSAMPLE:")
            for key in ["Countries", "N_Observations", "Period_Start", "Period_End", "Industries_Included"]:
                val = s.get(key, "")
                if val:
                    parts.append(f"  {key}: {val}")

        # Theory
        t = extraction.get("6_THEORY", {})
        if t:
            theory = t.get("Primary_Theory", "")
            if theory:
                parts.append(f"\nTHEORY: {theory}")

        # Gaps & Limitations — IMPORTANT: Expert observations about how this
        # paper relates to the dissertation's research gaps. Used as evidence.
        gl = extraction.get("8_GAPS_LIMITATIONS", {})
        if gl:
            gap_lines = []
            for key in ["OUR_Theoretical_Gap", "OUR_Methodological_Gap", "OUR_Variable_Gap",
                         "OUR_Contextual_Gap", "OUR_Mechanism_Gap"]:
                val = gl.get(key, "")
                if val:
                    label = key.replace("OUR_", "").replace("_", " ")
                    gap_lines.append(f"  {label}: {val}")

            # Also include stated limitations and future research suggestions
            for key in ["Stated_Limitation_1", "Stated_Limitation_2", "Stated_Limitation_3",
                         "Future_Research_1", "Future_Research_2", "Future_Research_3"]:
                val = gl.get(key, "")
                if val:
                    gap_lines.append(f"  {key.replace('_', ' ')}: {val}")

            adopt = gl.get("What_To_Adopt", "")
            if adopt:
                gap_lines.append(f"  What to adopt from this paper: {adopt}")

            if gap_lines:
                parts.append("\n=== EXPERT GAP ASSESSMENT (use as evidence for gap analysis) ===")
                parts.extend(gap_lines)
                parts.append("=== END GAP ASSESSMENT ===")

        # Narrative
        narr = extraction.get("narrative_assessment", "")
        if narr:
            parts.append(f"\nNARRATIVE ASSESSMENT: {narr}")

        return "\n".join(parts)

    # ═══════════════════════════════════════════════════════════
    # CLAUDE CLI
    # ═══════════════════════════════════════════════════════════

    def _run_claude(
        self,
        prompt: str,
        system: str,
        model: str,
        timeout: int,
        label: str = "Claude",
    ) -> str | None:
        """Spawn Claude CLI subprocess. Returns raw stdout or None."""
        cmd = [
            CLAUDE_CLI,
            "-p", prompt,
            "--output-format", "json",
            "--model", model,
            "--max-turns", "1",
            "--no-session-persistence",
            "--append-system-prompt", system,
        ]

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(label)

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
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    console.print(f"  [red]TIMEOUT after {timeout}s[/]")
                    return None

                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)

            stdout_full = "".join(stdout_lines)
            stderr_full = "".join(stderr_lines)

            if process.returncode != 0:
                console.print(f"  [red]Claude exited with code {process.returncode}[/]")
                if stderr_full.strip():
                    console.print(f"  [dim]stderr: {stderr_full[:300]}[/]")
                return None

            return stdout_full

        except FileNotFoundError:
            console.print("  [red]'claude' CLI not found[/]")
            return None
        except Exception as e:
            console.print(f"  [red]Unexpected error: {e}[/]")
            return None

    def _parse_json_output(self, stdout: str) -> list[dict] | None:
        """Parse Claude CLI JSON output."""
        stdout = stdout.strip()
        if not stdout:
            return None

        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            return self._extract_json_array(stdout)

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
                        return None
        return None


# ─── UTILITIES ──────────────────────────────────────────────

def _col_letter(index: int) -> str:
    """Convert 0-based column index to Excel-style letter (0=A, 25=Z, 26=AA)."""
    result = ""
    while True:
        result = chr(65 + index % 26) + result
        index = index // 26 - 1
        if index < 0:
            break
    return result


# ─── STANDALONE CLI ─────────────────────────────────────────

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
    """Find extraction JSON by substring match."""
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


def _show_quality_report(analyzer: GapMatrixAnalyzer) -> None:
    """Display distribution stats to detect systematic bias in gap analysis."""
    analyzer._pop._ensure_connected()

    # Read GAP_EVIDENCE
    try:
        ws = analyzer._pop._get_worksheet(GAP_EVIDENCE_TAB)
        all_data = ws.get_all_values()
    except Exception as e:
        console.print(f"  [red]Failed to read GAP_EVIDENCE: {e}[/]")
        return

    if len(all_data) < 2:
        console.print("  [yellow]No evidence data found[/]")
        return

    headers = all_data[0]
    pct_col = headers.index("Pct_Eliminated") if "Pct_Eliminated" in headers else 2
    conf_col = headers.index("Confidence_Tier") if "Confidence_Tier" in headers else -1
    paper_col = headers.index("Paper_ID") if "Paper_ID" in headers else 1

    eliminations = []
    conf_tiers = {"High": 0, "Moderate": 0, "Low": 0, "": 0}
    per_paper: dict[str, list[float]] = {}

    for row in all_data[1:]:
        if len(row) <= pct_col:
            continue
        try:
            pct = float(row[pct_col].replace("%", "").strip())
        except (ValueError, IndexError):
            continue
        if pct > 0:
            eliminations.append(pct)
        pid = row[paper_col] if len(row) > paper_col else ""
        if pid:
            per_paper.setdefault(pid, []).append(pct)

        if conf_col >= 0 and len(row) > conf_col:
            ct = row[conf_col].strip()
            conf_tiers[ct] = conf_tiers.get(ct, 0) + 1

    if not eliminations:
        console.print("  [yellow]No non-zero eliminations found[/]")
        return

    import statistics
    mean_e = statistics.mean(eliminations)
    median_e = statistics.median(eliminations)
    stdev_e = statistics.stdev(eliminations) if len(eliminations) > 1 else 0

    content = Text()
    content.append("GAP ANALYSIS QUALITY REPORT\n\n", style="bold magenta")
    content.append(f"Total non-zero assessments: {len(eliminations)}\n")
    content.append(f"Total papers with evidence: {len(per_paper)}\n\n")

    content.append("ELIMINATION DISTRIBUTION:\n", style="bold")
    content.append(f"  Mean:   {mean_e:.1f}%\n")
    content.append(f"  Median: {median_e:.1f}%\n")
    content.append(f"  StdDev: {stdev_e:.1f}%\n\n")

    # Buckets
    buckets = {"1-5%": 0, "6-15%": 0, "16-30%": 0, "31-50%": 0, "51-75%": 0, "76-100%": 0}
    for e in eliminations:
        if e <= 5: buckets["1-5%"] += 1
        elif e <= 15: buckets["6-15%"] += 1
        elif e <= 30: buckets["16-30%"] += 1
        elif e <= 50: buckets["31-50%"] += 1
        elif e <= 75: buckets["51-75%"] += 1
        else: buckets["76-100%"] += 1

    content.append("SCORE DISTRIBUTION:\n", style="bold")
    for bucket, count in buckets.items():
        pct = count / len(eliminations) * 100
        bar = "#" * int(pct / 2)
        content.append(f"  {bucket:10s} {count:4d} ({pct:5.1f}%) {bar}\n")

    content.append("\nCONFIDENCE TIERS:\n", style="bold")
    for tier, count in conf_tiers.items():
        if count > 0 and tier:
            content.append(f"  {tier:10s} {count}\n")

    # Health check
    content.append("\nDIAGNOSTIC:\n", style="bold")
    if mean_e < 10:
        content.append("  ⚠️  Mean < 10% — STILL TOO CONSERVATIVE\n", style="red")
    elif mean_e > 35:
        content.append("  ⚠️  Mean > 35% — possibly overcorrected\n", style="yellow")
    else:
        content.append(f"  ✅ Mean {mean_e:.1f}% is in healthy range (10-35%)\n", style="green")

    console.print(Panel(content, border_style="magenta", box=box.ROUNDED))


def main():
    parser = argparse.ArgumentParser(description="Gap Matrix Analyzer — cumulative percentage elimination")
    parser.add_argument("--paper", type=str, help="Analyze one paper (substring match)")
    parser.add_argument("--paper-id", type=str, help="Analyze one paper (exact paper_id)")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be analyzed")
    parser.add_argument("--status", action="store_true", help="Show matrix status dashboard")
    parser.add_argument("--discoveries", action="store_true", help="Analyze discovery extractions instead")
    parser.add_argument("--retroactive", action="store_true", help="Backfill: check all papers against gaps with zero evidence")
    parser.add_argument("--reset", action="store_true", help="Clear GAP_MATRIX + GAP_EVIDENCE and redo all gap analysis from scratch")
    parser.add_argument("--classify", action="store_true", help="Run gap taxonomy classification")
    parser.add_argument("--classify-dry-run", action="store_true", help="Preview gap tier classifications")
    parser.add_argument("--quality-report", action="store_true", help="Show distribution stats for bias detection")
    args = parser.parse_args()

    analyzer = GapMatrixAnalyzer()
    run_start = time.time()

    console.print("\n  [bold]Gap Matrix Analyzer[/]")
    console.print("  " + "-" * 50)

    # ── Taxonomy classification ──
    if args.classify or args.classify_dry_run:
        from gap_taxonomy import GapTaxonomy
        taxonomy = GapTaxonomy()
        taxonomy.classify_all_gaps(dry_run=args.classify_dry_run)
        return

    # ── Quality report ──
    if args.quality_report:
        _show_quality_report(analyzer)
        return

    if args.reset:
        console.print("\n  [bold red]⚠ This will DELETE all GAP_MATRIX and GAP_EVIDENCE data[/]")
        console.print("  [bold red]  and rerun analysis for ALL papers from scratch.[/]\n")
        confirm = input("  Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            console.print("  [dim]Aborted.[/]")
            return
        ext_dir = None
        if args.discoveries:
            from discovery_config import DISCOVERIES_DIR
            ext_dir = DISCOVERIES_DIR
        result = analyzer.reset_and_rerun(extraction_dir=ext_dir)
        elapsed = time.time() - run_start
        console.print(f"\n  [bold]Reset complete[/] in {elapsed:.1f}s")
        if isinstance(result, dict):
            written = result.get("written", 0)
            papers = result.get("papers_processed", 0)
            console.print(f"  Evidence rows: {written}, Papers: {papers}")
        console.print()
        return

    if args.status:
        analyzer.show_matrix_status()
        return

    if args.dry_run:
        if args.discoveries:
            from discovery_config import DISCOVERIES_DIR
            analyzer.dry_run(extraction_dir=DISCOVERIES_DIR)
        else:
            analyzer.dry_run()
        return

    if args.retroactive:
        ext_dir = None
        if args.discoveries:
            from discovery_config import DISCOVERIES_DIR
            ext_dir = DISCOVERIES_DIR
        result = analyzer.retroactive_analyze_all_uncovered(extraction_dir=ext_dir)
        elapsed = time.time() - run_start
        console.print(f"\n  [bold]Done[/] in {elapsed:.1f}s")
        if isinstance(result, dict):
            written = result.get("evidence_written", 0)
            scanned = result.get("papers_scanned", 0)
            console.print(f"  Evidence rows: {written}, Papers scanned: {scanned}")
        console.print()
        return

    if args.paper_id:
        match = _load_extraction_by_paper_id(args.paper_id)
        if not match:
            console.print(f"  [red]No extraction found for paper_id '{args.paper_id}'[/]")
            return
        paper_id, extraction = match
        console.print(f"  Paper: [bold cyan]{paper_id}[/]\n")
        result = analyzer.analyze_paper(paper_id, extraction)

    elif args.paper:
        match = _load_extraction_by_substring(args.paper)
        if not match:
            console.print(f"  [red]No extraction found matching '{args.paper}'[/]")
            return
        paper_id, extraction = match
        console.print(f"  Paper: [bold cyan]{paper_id}[/]\n")
        result = analyzer.analyze_paper(paper_id, extraction)

    elif args.discoveries:
        from discovery_config import DISCOVERIES_DIR
        result = analyzer.analyze_all_missing(extraction_dir=DISCOVERIES_DIR)
    else:
        result = analyzer.analyze_all_missing()

    elapsed = time.time() - run_start
    console.print(f"\n  [bold]Done[/] in {elapsed:.1f}s")

    if isinstance(result, dict):
        written = result.get("written", 0)
        papers = result.get("papers_processed", 1 if "assessments" in result else 0)
        console.print(f"  Evidence rows: {written}, Papers: {papers}")

    console.print()


if __name__ == "__main__":
    main()
