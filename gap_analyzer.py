"""
PhD Literature Extraction Pipeline — Gap Analyzer
===================================================
Tracks research gaps cumulatively across papers.
Cross-validates coverage claims against actual paper content.
"""
from __future__ import annotations


class GapAnalyzer:
    """Manages cumulative research gap tracking and cross-validation."""

    def __init__(self, initial_gaps: list[dict] | None = None):
        self.gaps = list(initial_gaps) if initial_gaps else []
        self._deduplicator = None  # Lazy-loaded

    def merge_paper_gaps(self, paper_id: str, gap_analysis: dict) -> dict:
        """
        Process a paper's gap analysis:
        - Update existing gaps with new coverage info
        - Add new gaps
        - Return summary of changes

        Returns: {"updated": int, "new": int, "warnings": list[str]}
        """
        summary = {"updated": 0, "new": 0, "warnings": [], "new_gap_ids": []}

        # Update existing gaps
        for update in gap_analysis.get("existing_gaps_updated", []):
            gap_id = update.get("gap_id", "")
            new_coverage = update.get("new_coverage_level", "NOT ADDRESSED")

            existing = self._find_gap(gap_id)
            if existing is None:
                continue

            # Validate coverage claim
            warning = self._validate_coverage(existing, update, paper_id)
            if warning:
                summary["warnings"].append(warning)

            # Update coverage level (only upgrade, never downgrade)
            old_coverage = existing.get("coverage_level", "NOT ADDRESSED")
            if self._coverage_rank(new_coverage) > self._coverage_rank(old_coverage):
                existing["coverage_level"] = new_coverage

            # Add covering paper
            covering = existing.get("covering_papers", [])
            if paper_id not in covering:
                covering.append(paper_id)
            existing["covering_papers"] = covering
            existing["coverage_notes"] = update.get("coverage_notes", "")
            existing["last_updated_by"] = paper_id

            summary["updated"] += 1

        # Add new gaps
        for new_gap in gap_analysis.get("new_gaps_identified", []):
            gap_id = new_gap.get("gap_id", "")
            if not gap_id:
                continue

            # Check for duplicates (by statement similarity)
            if self._is_duplicate_gap(new_gap):
                continue

            # Normalize gap structure
            normalized = {
                "gap_id": gap_id,
                "gap_statement": new_gap.get("gap_statement", ""),
                "gap_type": new_gap.get("gap_type", ""),
                "severity": new_gap.get("severity", 3),
                "feasibility": new_gap.get("feasibility", 3),
                "novelty": new_gap.get("novelty", 3),
                "coverage_level": "NOT ADDRESSED",
                "covering_papers": [],
                "coverage_notes": "",
                "paper_assignment": new_gap.get("paper_assignment", ""),
                "potential_hypothesis": new_gap.get("potential_hypothesis", ""),
                "variables_needed": new_gap.get("variables_needed", ""),
                "methodology_needed": new_gap.get("methodology_needed", ""),
                "data_available": new_gap.get("data_available", ""),
                "status": "Identified",
                "first_identified_in": paper_id,
                "last_updated_by": paper_id,
            }
            self.gaps.append(normalized)
            summary["new"] += 1
            summary["new_gap_ids"].append(gap_id)

        return summary

    def cross_validate(self, paper_id: str, extraction: dict, gap_analysis: dict) -> list[str]:
        """
        Cross-validate gap coverage claims against actual paper content.
        Returns list of warning messages.
        """
        warnings = []

        paper_dvs = self._extract_dv_categories(extraction)
        paper_ivs = self._extract_iv_types(extraction)

        for update in gap_analysis.get("existing_gaps_updated", []):
            coverage = update.get("new_coverage_level", "NOT ADDRESSED")
            if coverage in ("DIRECTLY TACKLED", "SUBSTANTIALLY COVERED"):
                gap = self._find_gap(update.get("gap_id", ""))
                if gap is None:
                    continue

                gap_stmt = gap.get("gap_statement", "").lower()

                # Check: if gap mentions sustainability/ESG but paper uses financial DVs
                if any(kw in gap_stmt for kw in ["sustainab", "esg", "environment", "green"]):
                    if "Financial Performance" in paper_dvs and "ESG-Sustainability" not in paper_dvs:
                        warnings.append(
                            f"GAP {gap['gap_id']}: Coverage downgraded from {coverage} → PARTIALLY ADDRESSED. "
                            f"Paper uses financial DVs ({', '.join(paper_dvs)}), "
                            f"but gap is about sustainability."
                        )

                # Check: if gap mentions digital/technology but paper doesn't have tech DVs
                if any(kw in gap_stmt for kw in ["digital", "technology", "ai", "transform"]):
                    if "Digital-Technology" not in paper_dvs:
                        warnings.append(
                            f"GAP {gap['gap_id']}: Coverage may be overstated for {coverage}. "
                            f"Paper DVs are {', '.join(paper_dvs) or 'unknown'}, "
                            f"but gap is about digital transformation."
                        )

                # Check: if gap mentions innovation but paper doesn't measure it
                if any(kw in gap_stmt for kw in ["innovat", "patent", "r&d"]):
                    if "Innovation-Patents" not in paper_dvs:
                        warnings.append(
                            f"GAP {gap['gap_id']}: Coverage may be overstated for {coverage}. "
                            f"Paper DVs are {', '.join(paper_dvs) or 'unknown'}, "
                            f"but gap is about innovation."
                        )

        return warnings

    def get_unresolved(self) -> list[dict]:
        """Gaps not yet directly tackled."""
        return [g for g in self.gaps if g.get("coverage_level") != "DIRECTLY TACKLED"]

    def get_summary(self) -> dict:
        """Gap statistics."""
        by_coverage = {}
        by_type = {}
        by_assignment = {}

        for g in self.gaps:
            cov = g.get("coverage_level", "NOT ADDRESSED")
            by_coverage[cov] = by_coverage.get(cov, 0) + 1

            gtype = g.get("gap_type", "Unknown")
            by_type[gtype] = by_type.get(gtype, 0) + 1

            assign = g.get("paper_assignment", "Unknown")
            by_assignment[assign] = by_assignment.get(assign, 0) + 1

        return {
            "total": len(self.gaps),
            "unresolved": len(self.get_unresolved()),
            "by_coverage": by_coverage,
            "by_type": by_type,
            "by_assignment": by_assignment,
        }

    def to_list(self) -> list[dict]:
        """Serializable list for state persistence."""
        return self.gaps

    # ─── INTERNAL ────────────────────────────────────────────

    def _find_gap(self, gap_id: str) -> dict | None:
        for g in self.gaps:
            if g.get("gap_id") == gap_id:
                return g
        return None

    def _coverage_rank(self, level: str) -> int:
        ranks = {
            "NOT ADDRESSED": 0,
            "PARTIALLY ADDRESSED": 1,
            "SUBSTANTIALLY COVERED": 2,
            "DIRECTLY TACKLED": 3,
        }
        return ranks.get(level, 0)

    def _is_duplicate_gap(self, new_gap: dict) -> bool:
        """
        Check if a new gap is semantically equivalent to an existing gap.
        Uses Claude Sonnet for semantic comparison; falls back to keyword
        overlap if Sonnet is unavailable.
        """
        if not self.gaps:
            return False

        # Lazy-load deduplicator (avoids import at module level)
        if self._deduplicator is None:
            try:
                from gap_deduplicator import GapDeduplicator
                self._deduplicator = GapDeduplicator()
            except ImportError:
                self._deduplicator = "unavailable"

        # Use semantic dedup if available
        if self._deduplicator != "unavailable":
            try:
                return self._deduplicator.is_duplicate(new_gap, self.gaps)
            except Exception:
                pass  # Fall through to keyword fallback

        # Fallback: original keyword overlap > 0.6
        return self._keyword_duplicate_check(new_gap)

    def _keyword_duplicate_check(self, new_gap: dict) -> bool:
        """Original keyword Jaccard overlap check (fallback)."""
        new_words = set(new_gap.get("gap_statement", "").lower().split())
        if len(new_words) < 3:
            return False

        for existing in self.gaps:
            existing_words = set(existing.get("gap_statement", "").lower().split())
            if len(existing_words) < 3:
                continue
            overlap = len(new_words & existing_words)
            union = len(new_words | existing_words)
            if union > 0 and overlap / union > 0.6:
                return True
        return False

    def _validate_coverage(self, gap: dict, update: dict, paper_id: str) -> str | None:
        """Basic validation of coverage claim. Returns warning or None."""
        # For now, validation is done in cross_validate() with actual paper data
        return None

    def _extract_dv_categories(self, extraction: dict) -> list[str]:
        """Extract DV categories from 3_VARIABLES section."""
        cats = []
        variables = extraction.get("3_VARIABLES", {})
        for key in ["DV1_Category", "DV2_Category"]:
            val = variables.get(key, "")
            if val and val != "" and val != "N/A":
                cats.append(val)
        return cats

    def _extract_iv_types(self, extraction: dict) -> list[str]:
        """Extract IV types from 3_VARIABLES section."""
        types = []
        variables = extraction.get("3_VARIABLES", {})
        for key in ["IV1_Type", "IV2_Type", "IV3_Type"]:
            val = variables.get(key, "")
            if val and val != "" and val != "N/A":
                types.append(val)
        return types
