"""
PhD Literature Extraction Pipeline — Summary Writer
=====================================================
Consolidates per-paper extraction data into the Literature_Review_Summary tab.
Each paper gets one row with composed, readable summaries from all 12 sections.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from config import SUMMARY_TAB, EXTRACTIONS_DIR, SHEETS_WRITE_DELAY
from populator import SheetPopulator, retry_on_api_error


class SummaryWriter:
    """Writes consolidated summary rows to the Literature_Review_Summary tab."""

    def __init__(self, populator: SheetPopulator):
        self._pop = populator
        self._tab = SUMMARY_TAB

    # ── Public API ───────────────────────────────────────────

    def write_summary(self, paper_id: str, extraction: dict,
                      gap_analysis: dict | None = None) -> bool:
        """Write a single paper's summary row. Returns True on success."""
        self._pop._ensure_connected()

        if self._pop._check_duplicate(self._tab, paper_id):
            self._pop.on_status(f"Summary for {paper_id} already exists — skipping")
            return True

        ws = self._pop._get_worksheet(self._tab)
        num_cols = len(self._pop._read_headers(self._tab))
        next_row = self._pop._find_next_empty_row(ws, num_cols)
        row_number = next_row - 1  # row 1 = header, row 2 = Number 1

        row_data = self.compose_summary_row(paper_id, extraction, gap_analysis, row_number)

        try:
            self._pop._write_row_by_headers(self._tab, row_data)
            self._pop.on_status(f"  ✅ {self._tab}")
            time.sleep(SHEETS_WRITE_DELAY)
            return True
        except Exception as e:
            self._pop.on_status(f"  ❌ {self._tab}: {e}")
            return False

    def backfill_missing(self) -> dict:
        """Scan extractions/ dir, write summary rows for papers not yet in tab."""
        self._pop._ensure_connected()

        stats = {"written": 0, "skipped": 0, "failed": 0}
        existing_ids = self._get_existing_paper_ids()

        extraction_files = sorted(EXTRACTIONS_DIR.glob("*.json"))
        if not extraction_files:
            self._pop.on_status("No extraction files found")
            return stats

        for ext_file in extraction_files:
            try:
                with open(ext_file) as f:
                    extraction = json.load(f)
                paper_id = extraction.get("paper_id", "")
                if not paper_id:
                    continue
                if paper_id in existing_ids:
                    self._pop.on_status(f"  ⏭️  {paper_id} already in summary")
                    stats["skipped"] += 1
                    continue

                ga = extraction.get("gap_analysis", {})
                ok = self.write_summary(paper_id, extraction, ga)
                if ok:
                    stats["written"] += 1
                    existing_ids.add(paper_id)
                else:
                    stats["failed"] += 1
            except Exception as e:
                self._pop.on_status(f"  ❌ Backfill {ext_file.name}: {e}")
                stats["failed"] += 1

        return stats

    # ── Composition ──────────────────────────────────────────

    def compose_summary_row(self, paper_id: str, extraction: dict,
                            gap_analysis: dict | None = None,
                            row_number: int | None = None) -> dict:
        """Build column-name -> value dict for one paper. Pure function, no I/O."""
        ga = gap_analysis or extraction.get("gap_analysis", {})
        return {
            "Number": str(row_number) if row_number else "",
            "PAPER_ID": paper_id,
            "Title": self._compose_title(extraction),
            "Summary": self._compose_abstract(extraction),
            "Abstract": extraction.get("Verbatim_Abstract", ""),
            "Objective": self._compose_objective(extraction),
            "Key_Variables": self._compose_key_variables(extraction),
            "Variable_Measurement": self._compose_variable_measurement(extraction),
            "Methodology": self._compose_methodology(extraction),
            "Sample": self._compose_sample(extraction),
            "Key_Findings": self._compose_key_findings(extraction),
            "Gap_IDs": self._compose_gap_ids(extraction, ga),
            "Limitations": self._compose_limitations(extraction),
            "Theme": self._compose_theme(extraction),
            "Relevance": self._compose_relevance_formula(row_number) if row_number else "",
            "Future_Research": self._compose_future_research(extraction),
        }

    # ── Private composition helpers ──────────────────────────

    def _compose_title(self, ext: dict) -> str:
        return ext.get("1_IDENTIFICATION", {}).get("Full_Citation_APA7", "")

    def _compose_abstract(self, ext: dict) -> str:
        sections = []

        # 1. Opening — what the paper studies
        rd = ext.get("2_RESEARCH_DESIGN", {})
        summary = rd.get("One_Sentence_Summary", "")
        if summary:
            sections.append(summary)

        # 2. Hypotheses tested
        hyp_lines = []
        for i in range(1, 5):
            stmt = rd.get(f"H{i}_Statement", "")
            if not stmt:
                continue
            direction = rd.get(f"H{i}_Direction", "")
            supported = rd.get(f"H{i}_Supported", "")
            line = f"H{i}: {stmt}"
            if direction:
                line += f" [{direction}]"
            if supported:
                line += f" — {supported}"
            hyp_lines.append(line)
        if hyp_lines:
            sections.append("Hypotheses:\n" + "\n".join(hyp_lines))

        # 3. Method + Sample
        m = ext.get("4_METHODOLOGY", {})
        s = ext.get("5_SAMPLE", {})
        method_parts = []
        design = m.get("Research_Design", "")
        est = m.get("Estimation_Primary", "")
        if design or est:
            method_parts.append(f"Design: {design} — {est}".strip(" — "))
        countries = s.get("Countries", "")
        n_obs = s.get("N_Observations", "")
        start = s.get("Period_Start", "")
        end = s.get("Period_End", "")
        sample_bits = []
        if countries:
            sample_bits.append(countries)
        if n_obs:
            sample_bits.append(f"{n_obs} obs")
        if start and end:
            sample_bits.append(f"{start}–{end}")
        if sample_bits:
            method_parts.append(f"Sample: {', '.join(sample_bits)}")
        endo = m.get("Endogeneity_Methods", "")
        if endo:
            method_parts.append(f"Endogeneity: {endo}")
        if method_parts:
            sections.append("\n".join(method_parts))

        # 4. Key Results
        f = ext.get("7_FINDINGS", {})
        result_parts = []
        main_finding = f.get("Main_Finding", "")
        if main_finding:
            result_parts.append(main_finding)
        direction = f.get("Effect_Direction", "")
        coeff = f.get("Coefficient_Beta", "")
        p_val = f.get("P_Value", "")
        stat_bits = []
        if direction:
            stat_bits.append(f"Effect: {direction}")
        if coeff:
            stat_bits.append(f"β: {coeff}")
        if p_val:
            stat_bits.append(f"p: {p_val}")
        if stat_bits:
            result_parts.append("; ".join(stat_bits))
        mechanisms = f.get("Mechanisms_Channels_Identified", "")
        if mechanisms:
            result_parts.append(f"Mechanisms: {mechanisms}")
        if result_parts:
            sections.append("Results: " + " | ".join(result_parts))

        # 5. Theoretical Framework
        theory = ext.get("6_THEORY", {})
        primary = theory.get("Primary_Theory", "")
        if primary:
            secondaries = [t for t in [
                theory.get("Secondary_Theory_1", ""),
                theory.get("Secondary_Theory_2", ""),
            ] if t]
            theory_line = f"Theoretical Framework: {primary}"
            if secondaries:
                theory_line += f" (also: {', '.join(secondaries)})"
            sections.append(theory_line)

        return "\n\n".join(sections)

    def _compose_objective(self, ext: dict) -> str:
        rd = ext.get("2_RESEARCH_DESIGN", {})
        rq = rd.get("Research_Question", "")
        aim = rd.get("Aim_Type", "")
        if aim and rq:
            return f"[{aim}] {rq}"
        return rq or aim

    def _compose_key_variables(self, ext: dict) -> str:
        v = ext.get("3_VARIABLES", {})
        lines = []

        for i in [1, 2]:
            name = v.get(f"DV{i}_Name", "")
            if name:
                label = "DV" if i == 1 else f"DV{i}"
                lines.append(f"{label}: {name}")

        for i in [1, 2, 3]:
            name = v.get(f"IV{i}_Name", "")
            if name:
                label = "IV" if i == 1 else f"IV{i}"
                lines.append(f"{label}: {name}")

        for i in [1, 2]:
            name = v.get(f"Moderator{i}_Name", "")
            if name:
                lines.append(f"Moderator: {name}")

        for i in [1, 2]:
            name = v.get(f"Mediator{i}_Name", "")
            if name:
                lines.append(f"Mediator: {name}")

        controls = v.get("Controls_List", "")
        count = v.get("Controls_Count", "")
        if controls:
            suffix = f" ({count} total)" if count else ""
            lines.append(f"Controls: {controls}{suffix}")

        return "\n".join(lines)

    def _compose_variable_measurement(self, ext: dict) -> str:
        v = ext.get("3_VARIABLES", {})
        lines = []

        for i in [1, 2]:
            name = v.get(f"DV{i}_Name", "")
            meas = v.get(f"DV{i}_Measurement", "")
            if name and meas:
                lines.append(f"DV{i}: {meas}")

        for i in [1, 2, 3]:
            name = v.get(f"IV{i}_Name", "")
            meas = v.get(f"IV{i}_Measurement", "")
            if name and meas:
                detail = v.get(f"IV{i}_Detail", "")
                entry = f"IV{i}: {meas}"
                if detail:
                    entry += f"; {detail}"
                lines.append(entry)

        for i in [1, 2]:
            name = v.get(f"Moderator{i}_Name", "")
            meas = v.get(f"Moderator{i}_Measurement", "")
            if name and meas:
                lines.append(f"Mod{i}: {meas}")

        for i in [1, 2]:
            name = v.get(f"Mediator{i}_Name", "")
            meas = v.get(f"Mediator{i}_Measurement", "")
            if name and meas:
                lines.append(f"Med{i}: {meas}")

        return "\n".join(lines)

    def _compose_methodology(self, ext: dict) -> str:
        m = ext.get("4_METHODOLOGY", {})
        parts = []

        design = m.get("Research_Design", "")
        est = m.get("Estimation_Primary", "")
        if design and est:
            parts.append(f"{design} — {est}")
        elif design or est:
            parts.append(design or est)

        endo = m.get("Endogeneity_Methods", "")
        if endo:
            parts.append(f"Endogeneity: {endo}")

        robustness = [m.get(f"Robustness_Check_{i}", "") for i in range(1, 5)]
        robustness = [r for r in robustness if r]
        if robustness:
            parts.append(f"Robustness: {', '.join(robustness)}")

        return "\n".join(parts)

    def _compose_sample(self, ext: dict) -> str:
        s = ext.get("5_SAMPLE", {})
        line1_parts = []
        n_firms = s.get("N_Firms", "")
        n_obs = s.get("N_Observations", "")
        if n_firms:
            line1_parts.append(f"{n_firms} firms")
        if n_obs:
            line1_parts.append(f"{n_obs} obs")
        line1 = ", ".join(line1_parts)

        countries = s.get("Countries", "")
        start = s.get("Period_Start", "")
        end = s.get("Period_End", "")
        period = f"({start}–{end})" if start and end else ""
        line2 = f"{countries} {period}".strip()

        industries = s.get("Industries_Included", "")
        listing = s.get("Listing_Requirement", "")
        line3_parts = [p for p in [industries, listing] if p]
        line3 = ", ".join(line3_parts)

        return "\n".join(p for p in [line1, line2, line3] if p)

    def _compose_key_findings(self, ext: dict) -> str:
        f = ext.get("7_FINDINGS", {})
        main = f.get("Main_Finding", "")
        coeff = f.get("Coefficient_Beta", "")
        p_val = f.get("P_Value", "")

        stat_parts = []
        if coeff:
            stat_parts.append(coeff)
        if p_val:
            stat_parts.append(f"p: {p_val}")

        result = main
        if stat_parts:
            result += f"\n[{'; '.join(stat_parts)}]"
        return result

    def _compose_gap_ids(self, ext: dict, gap_analysis: dict) -> str:
        ids = []
        for gap in gap_analysis.get("new_gaps_identified", []):
            gid = gap.get("gap_id", "")
            if gid:
                ids.append(gid)
        for gap in gap_analysis.get("existing_gaps_updated", []):
            gid = gap.get("gap_id", "")
            if gid:
                ids.append(gid)
        return ", ".join(ids)

    def _compose_limitations(self, ext: dict) -> str:
        gl = ext.get("8_GAPS_LIMITATIONS", {})
        lims = []
        for i in range(1, 4):
            lim = gl.get(f"Stated_Limitation_{i}", "")
            if lim:
                lims.append(f"{i}. {lim}")
        return "\n".join(lims)

    def _compose_theme(self, ext: dict) -> str:
        return ext.get("10_CLASSIFICATION", {}).get("Primary_Theme", "")

    def _compose_relevance_formula(self, row_number: int) -> str:
        """VLOOKUP formula referencing 9_RELEVANCE tab.
        B{row} = PAPER_ID. Col 8 = Weighted_Score, Col 9 = Relevance_Tier.
        Shows empty string if score is missing, otherwise 'Score (Tier)'."""
        r = row_number + 1  # row_number is 1-based data index, sheet row = row_number + 1
        return (
            f'=IFERROR(IF(VLOOKUP(B{r},\'9_RELEVANCE\'!A:J,8,FALSE)="",'
            f'"",VLOOKUP(B{r},\'9_RELEVANCE\'!A:J,8,FALSE)'
            f'&" ("&VLOOKUP(B{r},\'9_RELEVANCE\'!A:J,9,FALSE)&")"), "")'
        )

    def _compose_future_research(self, ext: dict) -> str:
        gl = ext.get("8_GAPS_LIMITATIONS", {})
        items = []
        for i in range(1, 4):
            fr = gl.get(f"Future_Research_{i}", "")
            if fr:
                items.append(f"{i}. {fr}")
        return "\n".join(items)

    # ── Helpers ──────────────────────────────────────────────

    @retry_on_api_error()
    def _get_existing_paper_ids(self) -> set[str]:
        """Read PAPER_ID column from the summary tab."""
        ws = self._pop._get_worksheet(self._tab)
        header_map = self._pop._get_header_map(self._tab)
        pid_col = header_map.get("PAPER_ID", 1)
        col_values = ws.col_values(pid_col + 1)  # 1-indexed
        return set(col_values[1:])  # skip header
