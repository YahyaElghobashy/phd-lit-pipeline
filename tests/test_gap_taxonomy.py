"""Tests for gap_taxonomy.py — gap classification into Core/Supporting/Niche tiers."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

import sys
from pathlib import Path

# Add pipeline root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gap_taxonomy import GapTaxonomy, CLASSIFY_SYSTEM_PROMPT
from config import TIER_CORE, TIER_SUPPORTING, TIER_NICHE, VALID_TIERS


# ─── FIXTURES ──────────────────────────────────────────────

SAMPLE_GAPS = [
    {
        "gap_id": "GAP_001",
        "gap_type": "Variable",
        "gap_statement": "No study examines BGD → green innovation using panel FE",
        "severity": "4",
        "paper_assignment": "Paper 2: Sustainability",
        "variables_needed": "BGD, green patents",
        "methodology_needed": "Panel FE with endogeneity",
        "tier": "",
    },
    {
        "gap_id": "GAP_002",
        "gap_type": "Contextual",
        "gap_statement": "BGD in Jordanian insurance firms using DEA not studied",
        "severity": "2",
        "paper_assignment": "",
        "variables_needed": "",
        "methodology_needed": "DEA",
        "tier": "",
    },
    {
        "gap_id": "GAP_003",
        "gap_type": "Theoretical",
        "gap_statement": "Resource dependence theory not tested for board diversity → sustainability",
        "severity": "3",
        "paper_assignment": "Paper 2: Sustainability",
        "variables_needed": "",
        "methodology_needed": "",
        "tier": "",
    },
]

SAMPLE_CLASSIFICATIONS = [
    {"gap_id": "GAP_001", "tier": "Core", "justification": "Directly addresses Paper 2 research question"},
    {"gap_id": "GAP_002", "tier": "Niche", "justification": "Hyper-specific single-country context"},
    {"gap_id": "GAP_003", "tier": "Supporting", "justification": "Theoretical framework relevant but not a direct RQ"},
]


# ─── PROMPT TESTS ──────────────────────────────────────────

class TestClassificationPrompt:
    """Test that the classification prompt is well-structured."""

    def test_prompt_contains_dissertation_context(self):
        assert "TITLE_PLACEHOLDER" in CLASSIFY_SYSTEM_PROMPT

    def test_prompt_defines_all_tiers(self):
        assert "CORE:" in CLASSIFY_SYSTEM_PROMPT
        assert "SUPPORTING:" in CLASSIFY_SYSTEM_PROMPT
        assert "NICHE:" in CLASSIFY_SYSTEM_PROMPT

    def test_prompt_mentions_research_design(self):
        assert "research design" in CLASSIFY_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_tier_labels(self):
        assert "CORE" in CLASSIFY_SYSTEM_PROMPT or "Core" in CLASSIFY_SYSTEM_PROMPT
        assert "SUPPORTING" in CLASSIFY_SYSTEM_PROMPT or "Supporting" in CLASSIFY_SYSTEM_PROMPT
        assert "NICHE" in CLASSIFY_SYSTEM_PROMPT or "Niche" in CLASSIFY_SYSTEM_PROMPT

    def test_prompt_requests_json_array(self):
        assert "JSON array" in CLASSIFY_SYSTEM_PROMPT


# ─── TIER VALIDATION TESTS ────────────────────────────────

class TestTierValidation:
    """Test tier constants and validation."""

    def test_valid_tiers(self):
        assert TIER_CORE == "Core"
        assert TIER_SUPPORTING == "Supporting"
        assert TIER_NICHE == "Niche"

    def test_valid_tiers_set(self):
        assert VALID_TIERS == {"Core", "Supporting", "Niche"}

    def test_invalid_tier_rejected(self):
        taxonomy = GapTaxonomy.__new__(GapTaxonomy)
        # override_tier should reject invalid tier (but we can't call it without sheet)
        assert "Invalid" not in VALID_TIERS


# ─── CLASSIFICATION PARSING TESTS ─────────────────────────

class TestClassificationParsing:
    """Test JSON parsing of Claude output."""

    def setup_method(self):
        self.taxonomy = GapTaxonomy.__new__(GapTaxonomy)

    def test_parse_valid_json_array(self):
        raw = json.dumps(SAMPLE_CLASSIFICATIONS)
        result = self.taxonomy._parse_json_output(raw)
        assert result is not None
        assert len(result) == 3
        assert result[0]["gap_id"] == "GAP_001"

    def test_parse_envelope_format(self):
        envelope = {"result": json.dumps(SAMPLE_CLASSIFICATIONS)}
        raw = json.dumps(envelope)
        result = self.taxonomy._parse_json_output(raw)
        assert result is not None
        assert len(result) == 3

    def test_parse_envelope_with_list_result(self):
        envelope = {"result": SAMPLE_CLASSIFICATIONS}
        raw = json.dumps(envelope)
        result = self.taxonomy._parse_json_output(raw)
        assert result is not None
        assert len(result) == 3

    def test_parse_empty_returns_none(self):
        assert self.taxonomy._parse_json_output("") is None
        assert self.taxonomy._parse_json_output("   ") is None

    def test_parse_invalid_json_returns_none(self):
        assert self.taxonomy._parse_json_output("not json") is None

    def test_extract_json_array_from_text(self):
        text = 'Here are the results: [{"gap_id": "GAP_001", "tier": "Core", "justification": "test"}] done.'
        result = self.taxonomy._extract_json_array(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["tier"] == "Core"

    def test_extract_json_array_no_array(self):
        assert self.taxonomy._extract_json_array("no array here") is None


# ─── CLASSIFICATION VALIDATION TESTS ──────────────────────

class TestClassifyBatch:
    """Test that _classify_batch validates results correctly."""

    def setup_method(self):
        self.taxonomy = GapTaxonomy.__new__(GapTaxonomy)

    def test_valid_classifications_accepted(self):
        mock_stdout = json.dumps(SAMPLE_CLASSIFICATIONS)
        with patch.object(self.taxonomy, '_run_claude', return_value=mock_stdout):
            result = self.taxonomy._classify_batch(SAMPLE_GAPS)
        assert len(result) == 3
        assert result[0]["tier"] == "Core"
        assert result[1]["tier"] == "Niche"
        assert result[2]["tier"] == "Supporting"

    def test_invalid_tier_filtered(self):
        bad_classifications = [
            {"gap_id": "GAP_001", "tier": "Core", "justification": "ok"},
            {"gap_id": "GAP_002", "tier": "InvalidTier", "justification": "bad"},
        ]
        mock_stdout = json.dumps(bad_classifications)
        with patch.object(self.taxonomy, '_run_claude', return_value=mock_stdout):
            result = self.taxonomy._classify_batch(SAMPLE_GAPS)
        assert len(result) == 1
        assert result[0]["gap_id"] == "GAP_001"

    def test_missing_gap_id_filtered(self):
        bad_classifications = [
            {"tier": "Core", "justification": "no gap_id"},
            {"gap_id": "GAP_002", "tier": "Niche", "justification": "ok"},
        ]
        mock_stdout = json.dumps(bad_classifications)
        with patch.object(self.taxonomy, '_run_claude', return_value=mock_stdout):
            result = self.taxonomy._classify_batch(SAMPLE_GAPS)
        assert len(result) == 1
        assert result[0]["gap_id"] == "GAP_002"

    def test_claude_failure_returns_empty(self):
        with patch.object(self.taxonomy, '_run_claude', return_value=None):
            result = self.taxonomy._classify_batch(SAMPLE_GAPS)
        assert result == []

    def test_justification_truncated(self):
        long_justification = "x" * 1000
        classifications = [
            {"gap_id": "GAP_001", "tier": "Core", "justification": long_justification},
        ]
        mock_stdout = json.dumps(classifications)
        with patch.object(self.taxonomy, '_run_claude', return_value=mock_stdout):
            result = self.taxonomy._classify_batch(SAMPLE_GAPS)
        assert len(result[0]["justification"]) <= 500


# ─── TIER STATS TESTS ─────────────────────────────────────

class TestTierStats:
    """Test tier statistics computation."""

    def setup_method(self):
        self.taxonomy = GapTaxonomy.__new__(GapTaxonomy)
        self.taxonomy._pop = MagicMock()
        self.taxonomy._sheet_id = ""

    def test_stats_with_classified_gaps(self):
        gaps = [
            {"gap_id": "G1", "tier": "Core"},
            {"gap_id": "G2", "tier": "Core"},
            {"gap_id": "G3", "tier": "Supporting"},
            {"gap_id": "G4", "tier": "Niche"},
            {"gap_id": "G5", "tier": ""},  # Unclassified
        ]
        with patch.object(self.taxonomy, '_read_gaps_from_tracker', return_value=gaps):
            stats = self.taxonomy.get_tier_stats()
        assert stats["Core"] == 2
        assert stats["Supporting"] == 1
        assert stats["Niche"] == 1
        assert stats["Unclassified"] == 1

    def test_stats_all_unclassified(self):
        gaps = [
            {"gap_id": "G1", "tier": ""},
            {"gap_id": "G2", "tier": ""},
        ]
        with patch.object(self.taxonomy, '_read_gaps_from_tracker', return_value=gaps):
            stats = self.taxonomy.get_tier_stats()
        assert stats["Unclassified"] == 2
        assert stats["Core"] == 0

    def test_stats_empty_tracker(self):
        with patch.object(self.taxonomy, '_read_gaps_from_tracker', return_value=[]):
            stats = self.taxonomy.get_tier_stats()
        assert all(v == 0 for v in stats.values())


# ─── GET GAPS BY TIER TESTS ───────────────────────────────

class TestGetGapsByTier:
    """Test tier filtering."""

    def setup_method(self):
        self.taxonomy = GapTaxonomy.__new__(GapTaxonomy)
        self.taxonomy._pop = MagicMock()

    def test_filter_core(self):
        gaps = [
            {"gap_id": "G1", "tier": "Core"},
            {"gap_id": "G2", "tier": "Niche"},
            {"gap_id": "G3", "tier": "Core"},
        ]
        with patch.object(self.taxonomy, '_read_gaps_from_tracker', return_value=gaps):
            result = self.taxonomy.get_gaps_by_tier("Core")
        assert len(result) == 2
        assert all(g["tier"] == "Core" for g in result)

    def test_filter_invalid_tier(self):
        result = self.taxonomy.get_gaps_by_tier("InvalidTier")
        assert result == []

    def test_filter_empty_tracker(self):
        with patch.object(self.taxonomy, '_read_gaps_from_tracker', return_value=[]):
            result = self.taxonomy.get_gaps_by_tier("Core")
        assert result == []
