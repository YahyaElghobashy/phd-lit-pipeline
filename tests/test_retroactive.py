"""
Tests for Module 1: Retroactive Gap Analysis
=============================================

Tests the retroactive_analyze() flow:
- gap_analyzer returns new_gap_ids
- retroactive screening filters old papers correctly
- evidence rows are written with correct paper_id / gap_id pairs
- existing paper column cells are updated (not new columns)
- resolved gaps are skipped
- non-breaking: pipeline continues even if retroactive fails

Uses mocking to avoid real Claude CLI calls and Google Sheets access.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Add pipeline root to path
PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))


# ─── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def sample_extraction_paper1():
    """A minimal extraction dict for Paper 1 (old paper)."""
    return {
        "paper_id": "Adams_2020",
        "1_IDENTIFICATION": {
            "Full_Citation_APA7": "Adams, R. B. (2020). Women on boards: The superheroes of tomorrow?"
        },
        "2_RESEARCH_DESIGN": {
            "Research_Question": "Do women on boards improve firm performance?",
            "One_Sentence_Summary": "Board gender diversity positively impacts ROA.",
        },
        "3_VARIABLES": {
            "DV1_Name": "ROA",
            "DV1_Measurement": "Net income / Total assets",
            "IV1_Name": "Board gender diversity",
            "IV1_Type": "Governance",
        },
        "4_METHODOLOGY": {"Research_Design": "Panel regression"},
        "5_SAMPLE": {"Countries": "US", "N_Observations": "5000"},
        "7_FINDINGS": {"Main_Finding": "Positive relationship between women on boards and ROA"},
        "gap_analysis": {},
    }


@pytest.fixture
def sample_extraction_paper2():
    """A minimal extraction dict for Paper 2 (old paper)."""
    return {
        "paper_id": "Chen_2021",
        "1_IDENTIFICATION": {
            "Full_Citation_APA7": "Chen, J. (2021). Gender quotas and firm innovation."
        },
        "2_RESEARCH_DESIGN": {
            "Research_Question": "Do gender quotas affect innovation output?",
            "One_Sentence_Summary": "Mandatory quotas increase patent filings.",
        },
        "3_VARIABLES": {
            "DV1_Name": "Patent count",
            "IV1_Name": "Gender quota adoption",
        },
        "4_METHODOLOGY": {"Research_Design": "Difference-in-differences"},
        "5_SAMPLE": {"Countries": "Norway", "N_Observations": "2000"},
        "7_FINDINGS": {"Main_Finding": "Quotas led to 12% increase in patent filings"},
        "gap_analysis": {},
    }


@pytest.fixture
def sample_gaps():
    """Gaps that were just created by Paper 10 (the new paper)."""
    return [
        {
            "gap_id": "GAP_NEW_001",
            "gap_type": "Methodological",
            "gap_statement": "No studies use difference-in-differences to isolate causal effect of board gender diversity on innovation",
            "severity": "4",
            "status": "Identified",
            "variables_needed": "Patent count, Board diversity %",
            "methodology_needed": "DiD with natural experiment",
        },
        {
            "gap_id": "GAP_NEW_002",
            "gap_type": "Contextual",
            "gap_statement": "Lack of studies examining board gender diversity effects in Nordic countries with mandatory quotas",
            "severity": "3",
            "status": "Identified",
            "variables_needed": "Board diversity %, Firm performance",
            "methodology_needed": "Cross-country analysis",
        },
    ]


@pytest.fixture
def sample_matrix():
    """A mock matrix state with 2 papers and some existing gaps."""
    return {
        "gap_ids": ["GAP_001", "GAP_002", "GAP_NEW_001", "GAP_NEW_002"],
        "paper_ids": ["Adams_2020", "Chen_2021"],
        "pct_remaining": {
            "GAP_001": 60.0,
            "GAP_002": 5.0,  # Already resolved (below 10% threshold)
            "GAP_NEW_001": 100.0,
            "GAP_NEW_002": 100.0,
        },
        "scores": {
            ("GAP_001", "Adams_2020"): "15%",
            ("GAP_001", "Chen_2021"): "10%",
        },
    }


@pytest.fixture
def extraction_dir(sample_extraction_paper1, sample_extraction_paper2):
    """Create a temp dir with extraction JSONs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for ext in [sample_extraction_paper1, sample_extraction_paper2]:
            path = Path(tmpdir) / f"{ext['paper_id']}.json"
            with open(path, "w") as f:
                json.dump(ext, f)
        yield Path(tmpdir)


# ─── Tests: gap_analyzer.merge_paper_gaps returns new_gap_ids ──────────


class TestGapAnalyzerNewGapIds:
    """Verify that merge_paper_gaps() now returns new_gap_ids in its summary."""

    def test_returns_new_gap_ids_key(self):
        from gap_analyzer import GapAnalyzer
        analyzer = GapAnalyzer()

        gap_analysis = {
            "new_gaps_identified": [
                {"gap_id": "GAP_100", "gap_statement": "Missing longitudinal studies on board turnover effects"},
                {"gap_id": "GAP_101", "gap_statement": "No cross-country analysis of quota enforcement mechanisms"},
            ],
            "existing_gaps_updated": [],
        }

        summary = analyzer.merge_paper_gaps("TestPaper_2024", gap_analysis)

        assert "new_gap_ids" in summary
        assert isinstance(summary["new_gap_ids"], list)
        assert summary["new_gap_ids"] == ["GAP_100", "GAP_101"]
        assert summary["new"] == 2

    def test_duplicates_not_in_new_gap_ids(self):
        from gap_analyzer import GapAnalyzer

        # Pre-populate with an existing gap
        existing = [{
            "gap_id": "GAP_050",
            "gap_statement": "Missing longitudinal studies on board turnover effects",
            "gap_type": "Methodological",
            "coverage_level": "NOT ADDRESSED",
        }]
        analyzer = GapAnalyzer(initial_gaps=existing)

        gap_analysis = {
            "new_gaps_identified": [
                # This should be detected as duplicate (high keyword overlap)
                {"gap_id": "GAP_200", "gap_statement": "Missing longitudinal studies on board turnover effects in firms"},
                # This should be new
                {"gap_id": "GAP_201", "gap_statement": "Blockchain governance token voting mechanisms unexplored"},
            ],
            "existing_gaps_updated": [],
        }

        summary = analyzer.merge_paper_gaps("TestPaper_2024", gap_analysis)

        # GAP_200 should be filtered as duplicate, GAP_201 should be new
        assert "GAP_201" in summary["new_gap_ids"]
        assert "GAP_200" not in summary["new_gap_ids"]

    def test_empty_gaps_returns_empty_list(self):
        from gap_analyzer import GapAnalyzer
        analyzer = GapAnalyzer()

        gap_analysis = {"new_gaps_identified": [], "existing_gaps_updated": []}
        summary = analyzer.merge_paper_gaps("TestPaper_2024", gap_analysis)

        assert summary["new_gap_ids"] == []
        assert summary["new"] == 0

    def test_existing_callers_unaffected(self):
        """Existing code that reads only updated/new/warnings still works."""
        from gap_analyzer import GapAnalyzer
        analyzer = GapAnalyzer()

        gap_analysis = {
            "new_gaps_identified": [
                {"gap_id": "GAP_300", "gap_statement": "Some new gap about corporate governance"},
            ],
            "existing_gaps_updated": [],
        }

        summary = analyzer.merge_paper_gaps("Test_2024", gap_analysis)

        # These are the keys existing code accesses
        assert isinstance(summary["updated"], int)
        assert isinstance(summary["new"], int)
        assert isinstance(summary["warnings"], list)
        # New key is additive — doesn't break dict access patterns
        assert summary["new"] == 1


# ─── Tests: retroactive_analyze() ─────────────────────────────────────


class TestRetroactiveAnalyze:
    """Test the retroactive analysis flow with mocked Claude calls and Sheets."""

    def _make_analyzer(self):
        """Create a GapMatrixAnalyzer with mocked Sheets connection."""
        with patch("gap_matrix_analyzer.SheetPopulator") as MockPop:
            mock_pop_instance = MagicMock()
            mock_pop_instance._ensure_connected = MagicMock()
            MockPop.return_value = mock_pop_instance
            from gap_matrix_analyzer import GapMatrixAnalyzer
            analyzer = GapMatrixAnalyzer()
            analyzer._pop = mock_pop_instance
            return analyzer

    def test_empty_gap_ids_returns_immediately(self):
        analyzer = self._make_analyzer()
        result = analyzer.retroactive_analyze(new_gap_ids=[], current_paper_id="X")
        assert result["papers_scanned"] == 0
        assert result["evidence_written"] == 0

    def test_skips_current_paper(self, sample_matrix, sample_gaps, extraction_dir):
        """The paper that created the new gaps should not be scanned against itself."""
        analyzer = self._make_analyzer()

        # Mock matrix read
        analyzer._read_matrix = MagicMock(return_value=sample_matrix)
        analyzer._get_all_gaps_from_tracker = MagicMock(return_value=sample_gaps)

        # Sonnet returns empty for all papers (no relevance)
        analyzer._screen_relevance = MagicMock(return_value=set())

        result = analyzer.retroactive_analyze(
            new_gap_ids=["GAP_NEW_001", "GAP_NEW_002"],
            current_paper_id="Adams_2020",
            extraction_dir=extraction_dir,
        )

        # Should have scanned Chen_2021 only (not Adams_2020)
        assert result["papers_scanned"] == 1

    def test_sonnet_screens_out_irrelevant_papers(self, sample_matrix, sample_gaps, extraction_dir):
        """If Sonnet says no relevance, Opus should not be called."""
        analyzer = self._make_analyzer()
        analyzer._read_matrix = MagicMock(return_value=sample_matrix)
        analyzer._get_all_gaps_from_tracker = MagicMock(return_value=sample_gaps)
        analyzer._screen_relevance = MagicMock(return_value=set())  # No relevance
        analyzer._deep_analyze = MagicMock()

        result = analyzer.retroactive_analyze(
            new_gap_ids=["GAP_NEW_001"],
            current_paper_id="",
            extraction_dir=extraction_dir,
        )

        # Opus should never be called
        analyzer._deep_analyze.assert_not_called()
        assert result["papers_relevant"] == 0

    def test_full_flow_with_relevant_paper(self, sample_matrix, sample_gaps, extraction_dir):
        """End-to-end: Sonnet finds relevance, Opus scores, results are written."""
        analyzer = self._make_analyzer()
        analyzer._read_matrix = MagicMock(return_value=sample_matrix)
        analyzer._get_all_gaps_from_tracker = MagicMock(return_value=sample_gaps)

        # Sonnet says Chen_2021 is relevant to GAP_NEW_001
        analyzer._screen_relevance = MagicMock(return_value={"GAP_NEW_001"})

        # Opus says Chen_2021 eliminates 25% of GAP_NEW_001
        analyzer._deep_analyze = MagicMock(return_value=[
            {
                "gap_id": "GAP_NEW_001",
                "pct_eliminated": 25,
                "aspect_addressed": "DiD methodology applied in Norway context",
                "what_still_remains": "Need same methodology for board diversity specifically",
                "reasoning": "Paper uses DiD for quota effects on innovation, directly relevant",
            }
        ])

        # Mock the write method to track calls
        analyzer._write_retroactive_results = MagicMock(return_value={
            "written": 1,
            "newly_resolved": [],
        })

        result = analyzer.retroactive_analyze(
            new_gap_ids=["GAP_NEW_001", "GAP_NEW_002"],
            current_paper_id="",
            extraction_dir=extraction_dir,
        )

        assert result["papers_relevant"] >= 1
        assert result["evidence_written"] >= 1
        assert len(result["per_paper"]) >= 1

    def test_resolved_gaps_are_skipped(self, sample_gaps, extraction_dir):
        """Gaps below RESOLVED_THRESHOLD (10%) should be skipped."""
        analyzer = self._make_analyzer()

        # Matrix shows GAP_NEW_001 is already at 5% remaining (resolved)
        matrix_with_resolved = {
            "gap_ids": ["GAP_NEW_001", "GAP_NEW_002"],
            "paper_ids": ["Adams_2020"],
            "pct_remaining": {
                "GAP_NEW_001": 5.0,  # Below 10% threshold
                "GAP_NEW_002": 100.0,
            },
            "scores": {},
        }
        analyzer._read_matrix = MagicMock(return_value=matrix_with_resolved)
        analyzer._get_all_gaps_from_tracker = MagicMock(return_value=sample_gaps)
        analyzer._screen_relevance = MagicMock(return_value=set())

        result = analyzer.retroactive_analyze(
            new_gap_ids=["GAP_NEW_001", "GAP_NEW_002"],
            current_paper_id="",
            extraction_dir=extraction_dir,
        )

        # Screening should only receive GAP_NEW_002 (GAP_NEW_001 is resolved)
        if analyzer._screen_relevance.called:
            call_args = analyzer._screen_relevance.call_args
            gaps_sent = call_args[0][2]  # third positional arg = open_new_gaps
            gap_ids_sent = {g["gap_id"] for g in gaps_sent}
            assert "GAP_NEW_001" not in gap_ids_sent


class TestWriteRetroactiveResults:
    """Test the _write_retroactive_results helper that updates existing columns."""

    def _make_analyzer(self):
        with patch("gap_matrix_analyzer.SheetPopulator") as MockPop:
            mock_pop_instance = MagicMock()
            mock_pop_instance._ensure_connected = MagicMock()
            MockPop.return_value = mock_pop_instance
            from gap_matrix_analyzer import GapMatrixAnalyzer
            analyzer = GapMatrixAnalyzer()
            analyzer._pop = mock_pop_instance
            return analyzer

    def test_updates_existing_column_not_new(self, sample_matrix):
        """Retroactive should update cells in Adams_2020's existing column, not create a new one."""
        analyzer = self._make_analyzer()

        # Mock worksheet
        mock_ws = MagicMock()
        analyzer._pop._get_worksheet = MagicMock(return_value=mock_ws)
        analyzer._pop._write_row_by_headers = MagicMock()

        # Mock _update_pct_remaining and _update_gap_tracker
        analyzer._update_pct_remaining = MagicMock()
        analyzer._update_gap_tracker = MagicMock()

        assessments = [
            {
                "gap_id": "GAP_NEW_001",
                "pct_eliminated": 30,
                "aspect_addressed": "DiD approach from US context",
                "what_still_remains": "Nordic context still missing",
            }
        ]

        result = analyzer._write_retroactive_results(
            "Adams_2020", assessments, sample_matrix, "retroactive"
        )

        # Should have called update_cells on the worksheet (not _write_paper_column)
        assert mock_ws.update_cells.called
        assert result["written"] >= 1

    def test_skips_cells_that_already_have_scores(self, sample_matrix):
        """If a (gap, paper) cell already has a score, don't overwrite it."""
        analyzer = self._make_analyzer()
        mock_ws = MagicMock()
        analyzer._pop._get_worksheet = MagicMock(return_value=mock_ws)
        analyzer._pop._write_row_by_headers = MagicMock()
        analyzer._update_pct_remaining = MagicMock()
        analyzer._update_gap_tracker = MagicMock()

        # GAP_001 already has a score for Adams_2020 in sample_matrix
        assessments = [
            {
                "gap_id": "GAP_001",  # Already has "15%" for Adams_2020
                "pct_eliminated": 20,
                "aspect_addressed": "Something",
                "what_still_remains": "Something else",
            }
        ]

        result = analyzer._write_retroactive_results(
            "Adams_2020", assessments, sample_matrix, "retroactive"
        )

        # Should NOT have written anything (cell already exists)
        assert result["written"] == 0

    def test_paper_not_in_matrix_returns_empty(self, sample_matrix):
        """If paper_id is not in the matrix, return empty result."""
        analyzer = self._make_analyzer()

        result = analyzer._write_retroactive_results(
            "NonExistent_2024", [], sample_matrix, "retroactive"
        )

        assert result["written"] == 0
        assert result["newly_resolved"] == []


# ─── Tests: retroactive_analyze_all_uncovered (CLI mode) ──────────────


class TestRetroactiveAnalyzeAllUncovered:
    """Test the standalone CLI backfill mode."""

    def _make_analyzer(self):
        with patch("gap_matrix_analyzer.SheetPopulator") as MockPop:
            mock_pop_instance = MagicMock()
            mock_pop_instance._ensure_connected = MagicMock()
            MockPop.return_value = mock_pop_instance
            from gap_matrix_analyzer import GapMatrixAnalyzer
            analyzer = GapMatrixAnalyzer()
            analyzer._pop = mock_pop_instance
            return analyzer

    def test_finds_gaps_with_no_evidence(self, sample_matrix):
        """Gaps in the matrix but not in evidence should be detected."""
        analyzer = self._make_analyzer()
        analyzer._read_matrix = MagicMock(return_value=sample_matrix)

        # Mock evidence tab — only GAP_001 has evidence rows
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [
            ["Gap_ID", "Paper_ID", "Pct_Eliminated"],
            ["GAP_001", "Adams_2020", "15%"],
            ["GAP_001", "Chen_2021", "10%"],
        ]
        analyzer._pop._get_worksheet = MagicMock(return_value=mock_ws)

        # Mock retroactive_analyze to capture what gap_ids it receives
        analyzer.retroactive_analyze = MagicMock(return_value={
            "papers_scanned": 0, "papers_relevant": 0,
            "evidence_written": 0, "gaps_newly_resolved": [], "per_paper": [],
        })

        analyzer.retroactive_analyze_all_uncovered()

        # Should have called retroactive_analyze with uncovered gaps
        call_args = analyzer.retroactive_analyze.call_args
        new_gap_ids = set(call_args[1]["new_gap_ids"])
        # GAP_002, GAP_NEW_001, GAP_NEW_002 have no evidence rows
        assert "GAP_002" in new_gap_ids
        assert "GAP_NEW_001" in new_gap_ids
        assert "GAP_NEW_002" in new_gap_ids
        assert "GAP_001" not in new_gap_ids  # Has evidence

    def test_all_gaps_covered_returns_early(self, sample_matrix):
        """If all gaps have evidence, return immediately."""
        analyzer = self._make_analyzer()
        analyzer._read_matrix = MagicMock(return_value=sample_matrix)

        # All gaps have evidence
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [
            ["Gap_ID", "Paper_ID", "Pct_Eliminated"],
            ["GAP_001", "Adams_2020", "15%"],
            ["GAP_002", "Adams_2020", "5%"],
            ["GAP_NEW_001", "Chen_2021", "10%"],
            ["GAP_NEW_002", "Chen_2021", "20%"],
        ]
        analyzer._pop._get_worksheet = MagicMock(return_value=mock_ws)

        result = analyzer.retroactive_analyze_all_uncovered()
        assert result.get("gaps_found", 0) == 0


# ─── Tests: Non-breaking integration ──────────────────────────────────


class TestNonBreaking:
    """Verify that the retroactive changes don't break existing behavior."""

    def test_gap_analyzer_backward_compatible(self):
        """merge_paper_gaps() still returns updated/new/warnings as before."""
        from gap_analyzer import GapAnalyzer
        analyzer = GapAnalyzer()

        gap_analysis = {
            "new_gaps_identified": [
                {"gap_id": "GAP_X", "gap_statement": "Novel theoretical framework for stakeholder salience"},
            ],
            "existing_gaps_updated": [],
        }

        summary = analyzer.merge_paper_gaps("Paper_X", gap_analysis)

        # Original keys still present and correct types
        assert "updated" in summary and isinstance(summary["updated"], int)
        assert "new" in summary and isinstance(summary["new"], int)
        assert "warnings" in summary and isinstance(summary["warnings"], list)

        # New key is additive
        assert "new_gap_ids" in summary

    def test_analyze_paper_unchanged(self):
        """The existing analyze_paper() method should still work identically."""
        # This test just verifies the method signature hasn't changed
        from gap_matrix_analyzer import GapMatrixAnalyzer
        import inspect
        sig = inspect.signature(GapMatrixAnalyzer.analyze_paper)
        params = list(sig.parameters.keys())
        assert params == ["self", "paper_id", "extraction", "source"]
