"""
PhD Literature Extraction Pipeline — Configuration
====================================================
All constants, paths, and settings in one place.
"""
from pathlib import Path

# ─── PATHS ──────────────────────────────────────────────────
PIPELINE_DIR = Path(__file__).parent
PDF_ROOT = PIPELINE_DIR.parent  # Literature Review folder
EXTRACTIONS_DIR = PIPELINE_DIR / "extractions"
REPORTS_DIR = PIPELINE_DIR / "reports"
STATE_FILE = PIPELINE_DIR / "pipeline_state.json"
CLIENT_SECRET_FILE = PIPELINE_DIR / "client_secret.json"
TOKEN_FILE = PIPELINE_DIR / "token.json"

# ─── GOOGLE SHEETS ──────────────────────────────────────────
SPREADSHEET_ID = "15OI-dwZBCpag7K_Gif1GcAampoou9pqFHVohjcHKpIc"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Tab names in the Google Sheet (order matters for population)
SHEET_TABS = [
    "1_IDENTIFICATION",
    "2_RESEARCH_DESIGN",
    "3_VARIABLES",
    "4_METHODOLOGY",
    "5_SAMPLE",
    "6_THEORY",
    "7_FINDINGS",
    "8_GAPS_LIMITATIONS",
    "9_RELEVANCE",
    "10_CLASSIFICATION",
    "11_CONNECTIONS",
    "12_BOARD_CHARS",
    "GAP_TRACKER",
    "MASTER_VIEW",
    "Literature_Review_Summary",
]

SUMMARY_TAB = "Literature_Review_Summary"

# Tabs we must NEVER write to
READ_ONLY_TABS = {"DASHBOARD", "SYNTHESIS"}

# ─── CLAUDE CLI ─────────────────────────────────────────────
CLAUDE_CLI = "claude"
CLAUDE_MODEL = "claude-opus-4-6"
CLAUDE_MAX_TURNS = 3
CLAUDE_EFFORT = "high"

# ─── TIMEOUTS & RETRIES ────────────────────────────────────
EXTRACTION_TIMEOUT_SECONDS = 600  # 10 minutes per paper
EXTRACTION_MAX_RETRIES = 2
EXTRACTION_RETRY_DELAY = 30  # seconds between retries

SHEETS_WRITE_DELAY = 2.0  # seconds between tab writes (rate limiting)
SHEETS_MAX_RETRIES = 5
SHEETS_RETRY_BASE_DELAY = 5.0  # exponential: 5s, 10s, 20s, 40s, 80s

# ─── GAP COVERAGE ANALYZER (DEPRECATED — replaced by GAP_MATRIX_ANALYZER) ──
# GAP_COVERAGE_TAB = "GAP_COVERAGE_MAP"   # Legacy: use GAP_MATRIX_TAB instead
# GAP_ANALYSIS_TIMEOUT = 300
# GAP_ANALYSIS_MAX_RETRIES = 2
# GAP_ANALYSIS_RETRY_DELAY = 30
GAP_BATCH_SIZE = 75  # Max gaps per Claude call; if total > this, split into batches

# ─── GAP MATRIX ANALYZER (replaces GAP_COVERAGE_MAP + GAP_NOVELTY) ──
GAP_MATRIX_TAB = "GAP_MATRIX"
GAP_EVIDENCE_TAB = "GAP_EVIDENCE"
GAP_RESOLVED_THRESHOLD = 10    # % remaining below which gap is skipped
GAP_SCREEN_TIMEOUT = 120       # Phase 1 Sonnet relevance screen (seconds)
GAP_DEEP_TIMEOUT = 300         # Phase 2 Opus deep analysis (seconds)

# ─── CONFIDENCE SCORING (Module 6) ────────────────────────
CONFIDENCE_WEIGHTS = {
    "methodological_alignment": 0.30,
    "sample_relevance": 0.25,
    "variable_overlap": 0.25,
    "evidence_directness": 0.20,
}
CONFIDENCE_HIGH_THRESHOLD = 4.0   # >= this → "High"
CONFIDENCE_LOW_THRESHOLD = 2.5    # >= this → "Moderate", below → "Low"

# ─── PDF PROCESSING ────────────────────────────────────────
EXTRACTED_SUFFIX = " — Extracted.pdf"
DATE_FORMAT = "%Y-%m-%d"
