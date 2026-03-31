"""
Tests for Module 2: Semantic Gap Deduplication
================================================

Tests the GapDeduplicator:
- Sonnet-based semantic comparison
- Keyword fallback when Sonnet is unavailable
- Backfill clustering
- Audit log
- Integration with gap_analyzer._is_duplicate_gap()
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))


# ─── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def existing_gaps():
    """Existing gaps in the tracker."""
    return [
        {
            "gap_id": "GAP_012",
            "gap_statement": "Insufficient time-series data examining gender composition on corporate boards",
            "gap_type": "Methodological",
        },
        {
            "gap_id": "GAP_045",
            "gap_statement": "Limited multi-country studies on board gender quota compliance mechanisms",
            "gap_type": "Contextual",
        },
        {
            "gap_id": "GAP_067",
            "gap_statement": "No studies examining CEO duality and board independence interaction effects",
            "gap_type": "Variable",
        },
    ]


@pytest.fixture
def new_gaps_with_duplicates():
    """New gaps where some are semantic duplicates of existing ones."""
    return [
        {
            "gap_id": "GAP_NEW_001",
            "gap_statement": "Lack of longitudinal studies on board diversity effects over time",
        },
        {
            "gap_id": "GAP_NEW_002",
            "gap_statement": "Blockchain governance token voting mechanisms remain unexplored",
        },
    ]


@pytest.fixture
def sonnet_duplicate_response():
    """Mocked Sonnet response identifying a duplicate."""
    return json.dumps({
        "result": json.dumps([
            {
                "new_gap_id": "GAP_NEW_001",
                "status": "duplicate",
                "duplicate_of": "GAP_012",
                "similarity": 0.88,
                "reason": "Both address lack of longitudinal/time-series analysis of board gender composition",
            },
            {
                "new_gap_id": "GAP_NEW_002",
                "status": "unique",
            },
        ])
    })


@pytest.fixture
def sonnet_cluster_response():
    """Mocked Sonnet response for backfill clustering."""
    return json.dumps({
        "result": json.dumps([
            {
                "cluster_id": 1,
                "canonical_gap_id": "GAP_012",
                "members": ["GAP_012", "GAP_NEW_001"],
                "reason": "Both address longitudinal analysis of board diversity",
            },
            {
                "cluster_id": 2,
                "canonical_gap_id": "GAP_045",
                "members": ["GAP_045"],
                "reason": "Unique gap about multi-country quota compliance",
            },
            {
                "cluster_id": 3,
                "canonical_gap_id": "GAP_067",
                "members": ["GAP_067"],
                "reason": "Unique gap about CEO duality interaction",
            },
        ])
    })


@pytest.fixture
def dedup_with_temp_log():
    """Create a GapDeduplicator with a temp log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "dedup_log.json"
        with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
            from gap_deduplicator import GapDeduplicator
            dedup = GapDeduplicator()
            yield dedup, log_path


# ─── Tests: Semantic check via Sonnet ──────────────────────────


class TestSemanticCheck:
    """Test Sonnet-based semantic duplicate detection."""

    def test_detects_semantic_duplicate(
        self, existing_gaps, new_gaps_with_duplicates, sonnet_duplicate_response
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                with patch.object(dedup, "_run_claude", return_value=sonnet_duplicate_response):
                    result = dedup.check_duplicates(new_gaps_with_duplicates, existing_gaps)

                # GAP_NEW_001 should be detected as duplicate of GAP_012
                assert result["GAP_NEW_001"] is not None
                assert result["GAP_NEW_001"]["duplicate_of"] == "GAP_012"
                assert result["GAP_NEW_001"]["similarity"] == 0.88

                # GAP_NEW_002 should be unique
                assert result["GAP_NEW_002"] is None

    def test_unique_gaps_pass_through(self, existing_gaps):
        unique_gaps = [
            {
                "gap_id": "GAP_UNIQUE",
                "gap_statement": "Quantum computing effects on corporate governance remain unstudied",
            }
        ]

        response = json.dumps({
            "result": json.dumps([
                {"new_gap_id": "GAP_UNIQUE", "status": "unique"}
            ])
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                with patch.object(dedup, "_run_claude", return_value=response):
                    result = dedup.check_duplicates(unique_gaps, existing_gaps)

                assert result["GAP_UNIQUE"] is None

    def test_invalid_duplicate_of_treated_as_unique(self, existing_gaps):
        """If Sonnet returns a duplicate_of that doesn't exist, treat as unique."""
        response = json.dumps({
            "result": json.dumps([
                {
                    "new_gap_id": "GAP_X",
                    "status": "duplicate",
                    "duplicate_of": "GAP_NONEXISTENT",
                    "similarity": 0.9,
                }
            ])
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                with patch.object(dedup, "_run_claude", return_value=response):
                    result = dedup.check_duplicates(
                        [{"gap_id": "GAP_X", "gap_statement": "test"}],
                        existing_gaps,
                    )

                assert result["GAP_X"] is None  # Invalid reference → unique

    def test_empty_new_gaps_returns_empty(self, existing_gaps):
        from gap_deduplicator import GapDeduplicator
        dedup = GapDeduplicator()
        result = dedup.check_duplicates([], existing_gaps)
        assert result == {}

    def test_empty_existing_gaps_all_unique(self):
        from gap_deduplicator import GapDeduplicator
        dedup = GapDeduplicator()
        result = dedup.check_duplicates(
            [{"gap_id": "G1", "gap_statement": "test"}],
            [],
        )
        assert result["G1"] is None


# ─── Tests: Keyword fallback ──────────────────────────────────


class TestKeywordFallback:
    """Test that keyword overlap fallback works when Sonnet fails."""

    def test_falls_back_on_claude_failure(self, existing_gaps):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                # Sonnet returns None (failure)
                with patch.object(dedup, "_run_claude", return_value=None):
                    # This gap has high keyword overlap with GAP_012
                    new_gap = {
                        "gap_id": "GAP_HIGH_OVERLAP",
                        "gap_statement": "Insufficient time-series data examining gender composition on corporate boards and governance",
                    }
                    result = dedup.check_duplicates([new_gap], existing_gaps)

                # Should detect via keyword fallback
                assert result["GAP_HIGH_OVERLAP"] is not None
                assert result["GAP_HIGH_OVERLAP"]["duplicate_of"] == "GAP_012"

    def test_keyword_fallback_misses_semantic_duplicates(self, existing_gaps):
        """Keyword fallback can't catch rephrased duplicates — this is expected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                with patch.object(dedup, "_run_claude", return_value=None):
                    # This is semantically equivalent to GAP_012 but uses different words
                    new_gap = {
                        "gap_id": "GAP_REPHRASED",
                        "gap_statement": "Lack of longitudinal panel studies tracking female director appointment effects over decades",
                    }
                    result = dedup.check_duplicates([new_gap], existing_gaps)

                # Keyword fallback can't catch this — expected behavior
                assert result["GAP_REPHRASED"] is None


# ─── Tests: is_duplicate() boolean API ────────────────────────


class TestIsDuplicate:
    """Test the simple boolean is_duplicate() API."""

    def test_returns_true_for_duplicate(self, existing_gaps, sonnet_duplicate_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                with patch.object(dedup, "_run_claude", return_value=sonnet_duplicate_response):
                    result = dedup.is_duplicate(
                        {"gap_id": "GAP_NEW_001", "gap_statement": "Lack of longitudinal studies on board diversity effects over time"},
                        existing_gaps,
                    )

                assert result is True

    def test_returns_false_for_unique(self, existing_gaps):
        response = json.dumps({
            "result": json.dumps([
                {"new_gap_id": "GAP_X", "status": "unique"}
            ])
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                with patch.object(dedup, "_run_claude", return_value=response):
                    result = dedup.is_duplicate(
                        {"gap_id": "GAP_X", "gap_statement": "Quantum computing in governance"},
                        existing_gaps,
                    )

                assert result is False

    def test_returns_false_for_empty_existing(self):
        from gap_deduplicator import GapDeduplicator
        dedup = GapDeduplicator()
        result = dedup.is_duplicate(
            {"gap_id": "G1", "gap_statement": "test"},
            [],
        )
        assert result is False


# ─── Tests: Backfill clustering ───────────────────────────────


class TestBackfillClusters:
    """Test the backfill clustering functionality."""

    def test_clusters_gaps_correctly(self, existing_gaps, sonnet_cluster_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                with patch.object(dedup, "_run_claude", return_value=sonnet_cluster_response):
                    clusters = dedup.backfill_clusters(existing_gaps)

                assert len(clusters) == 3
                dup_clusters = [c for c in clusters if len(c.get("members", [])) > 1]
                assert len(dup_clusters) == 1  # Only cluster 1 has >1 member

    def test_empty_gaps_returns_empty(self):
        from gap_deduplicator import GapDeduplicator
        dedup = GapDeduplicator()
        result = dedup.backfill_clusters([])
        assert result == []


# ─── Tests: Audit log ────────────────────────────────────────


class TestAuditLog:
    """Test the dedup decision audit log."""

    def test_log_records_decisions(self, existing_gaps, sonnet_duplicate_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()

                with patch.object(dedup, "_run_claude", return_value=sonnet_duplicate_response):
                    dedup.check_duplicates(
                        [
                            {"gap_id": "GAP_NEW_001", "gap_statement": "test1"},
                            {"gap_id": "GAP_NEW_002", "gap_statement": "test2"},
                        ],
                        existing_gaps,
                    )

                # Check log file was written
                assert log_path.exists()
                with open(log_path) as f:
                    log = json.load(f)

                assert len(log) == 2
                # One duplicate, one unique
                dup_entry = next(e for e in log if e["gap_id"] == "GAP_NEW_001")
                assert dup_entry["is_duplicate"] is True
                assert dup_entry["method"] == "sonnet"
                assert dup_entry["duplicate_of"] == "GAP_012"

                unique_entry = next(e for e in log if e["gap_id"] == "GAP_NEW_002")
                assert unique_entry["is_duplicate"] is False

    def test_log_stats(self, existing_gaps, sonnet_duplicate_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "dedup_log.json"
            with patch("gap_deduplicator.DEDUP_LOG_FILE", log_path):
                from gap_deduplicator import GapDeduplicator
                dedup = GapDeduplicator()
                dedup._log = []

                # Use gap IDs that match the sonnet response fixture
                with patch.object(dedup, "_run_claude", return_value=sonnet_duplicate_response):
                    dedup.check_duplicates(
                        [
                            {"gap_id": "GAP_NEW_001", "gap_statement": "test1"},
                            {"gap_id": "GAP_NEW_002", "gap_statement": "test2"},
                        ],
                        existing_gaps,
                    )

                stats = dedup.get_log_stats()
                assert stats["total_checks"] == 2
                assert stats["duplicates_found"] == 1
                assert stats["unique"] == 1
                assert stats["by_method"]["sonnet"] == 2


# ─── Tests: Integration with gap_analyzer ─────────────────────


class TestGapAnalyzerIntegration:
    """Test that gap_analyzer uses deduplicator correctly."""

    def test_gap_analyzer_uses_deduplicator(self):
        """gap_analyzer._is_duplicate_gap should try deduplicator first."""
        from gap_analyzer import GapAnalyzer

        analyzer = GapAnalyzer(initial_gaps=[
            {
                "gap_id": "GAP_001",
                "gap_statement": "Lack of longitudinal studies on board diversity",
                "gap_type": "Methodological",
                "coverage_level": "NOT ADDRESSED",
            }
        ])

        # Mock the deduplicator
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate.return_value = True
        analyzer._deduplicator = mock_dedup

        result = analyzer._is_duplicate_gap({
            "gap_id": "GAP_NEW",
            "gap_statement": "Insufficient time-series analysis of female director effects",
        })

        assert result is True
        mock_dedup.is_duplicate.assert_called_once()

    def test_gap_analyzer_falls_back_to_keyword(self):
        """If deduplicator raises, should fall back to keyword check."""
        from gap_analyzer import GapAnalyzer

        analyzer = GapAnalyzer(initial_gaps=[
            {
                "gap_id": "GAP_001",
                "gap_statement": "Lack of longitudinal studies on board diversity in emerging markets",
                "gap_type": "Methodological",
                "coverage_level": "NOT ADDRESSED",
            }
        ])

        # Mock deduplicator that raises
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate.side_effect = Exception("Claude unavailable")
        analyzer._deduplicator = mock_dedup

        # This gap has low keyword overlap → should be unique via fallback
        result = analyzer._is_duplicate_gap({
            "gap_id": "GAP_NEW",
            "gap_statement": "Quantum computing governance mechanisms remain unexplored",
        })

        assert result is False  # Keyword fallback says unique

    def test_gap_analyzer_works_without_deduplicator_module(self):
        """If gap_deduplicator module can't be imported, use keyword fallback."""
        from gap_analyzer import GapAnalyzer

        analyzer = GapAnalyzer(initial_gaps=[
            {
                "gap_id": "GAP_001",
                "gap_statement": "Lack of studies on board diversity effects on firm performance in emerging markets",
                "gap_type": "Methodological",
                "coverage_level": "NOT ADDRESSED",
            }
        ])

        # Simulate import failure
        analyzer._deduplicator = "unavailable"

        # High keyword overlap → caught by fallback
        result = analyzer._is_duplicate_gap({
            "gap_id": "GAP_DUP",
            "gap_statement": "Lack of studies on board diversity effects on firm performance in emerging markets and developing nations",
        })

        assert result is True  # Keyword overlap > 0.6


# ─── Tests: Non-breaking regression ──────────────────────────


class TestNonBreaking:
    """Verify Module 2 doesn't break existing behavior."""

    def test_merge_paper_gaps_still_works(self):
        """merge_paper_gaps() should still return all expected keys."""
        from gap_analyzer import GapAnalyzer
        analyzer = GapAnalyzer()

        # Force keyword fallback (no deduplicator)
        analyzer._deduplicator = "unavailable"

        gap_analysis = {
            "new_gaps_identified": [
                {"gap_id": "GAP_TEST", "gap_statement": "A completely unique test gap about something novel"},
            ],
            "existing_gaps_updated": [],
        }

        summary = analyzer.merge_paper_gaps("Test_2024", gap_analysis)

        assert "updated" in summary
        assert "new" in summary
        assert "warnings" in summary
        assert "new_gap_ids" in summary
        assert summary["new"] == 1
        assert "GAP_TEST" in summary["new_gap_ids"]

    def test_keyword_duplicate_check_preserved(self):
        """The original keyword check is preserved as _keyword_duplicate_check."""
        from gap_analyzer import GapAnalyzer
        analyzer = GapAnalyzer(initial_gaps=[
            {
                "gap_id": "GAP_001",
                "gap_statement": "board gender diversity effects on firm financial performance remain unclear",
                "gap_type": "Variable",
                "coverage_level": "NOT ADDRESSED",
            }
        ])

        # High overlap → duplicate
        assert analyzer._keyword_duplicate_check({
            "gap_statement": "board gender diversity effects on firm financial performance remain understudied"
        }) is True

        # Low overlap → unique
        assert analyzer._keyword_duplicate_check({
            "gap_statement": "quantum computing blockchain artificial intelligence novel"
        }) is False
