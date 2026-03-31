"""
PhD Literature Discovery Pipeline — Configuration
====================================================
All constants for the gap validation & research discovery mini-project.
"""
from pathlib import Path
from config import PIPELINE_DIR, CLIENT_SECRET_FILE, TOKEN_FILE, SCOPES

# ─── PATHS ──────────────────────────────────────────────────
DISCOVERIES_DIR = PIPELINE_DIR / "discoveries"
DISCOVERY_REPORTS_DIR = PIPELINE_DIR / "reports"
DISCOVERY_STATE_FILE = PIPELINE_DIR / "discovery_state.json"

# PDF download destination
PDF_DOWNLOAD_DIR = PIPELINE_DIR.parent / "Automated Extraction"

# ─── ORIGINAL SHEET (READ-ONLY) ────────────────────────────
ORIGINAL_SPREADSHEET_ID = "15OI-dwZBCpag7K_Gif1GcAampoou9pqFHVohjcHKpIc"

# ─── AUTOMATED EXTRACTION SHEET (will be set after creation) ─
AUTO_SPREADSHEET_ID = "1lmt-sNf15Gllvf6OEQrne7bpt0Wj0GsPigNssJplH2Y"  # Set after Milestone 2 creates the sheet

# ─── API ENDPOINTS ──────────────────────────────────────────
OPENALEX_BASE_URL = "https://api.openalex.org"
CROSSREF_BASE_URL = "https://api.crossref.org"
UNPAYWALL_BASE_URL = "https://api.unpaywall.org/v2"

# Polite pool email (OpenAlex & Unpaywall require mailto for polite rate limits)
API_MAILTO = "yahya.elghobashy@gmail.com"

# ─── RATE LIMITS ────────────────────────────────────────────
OPENALEX_RATE_LIMIT = 0.1       # seconds between requests (10 req/s polite pool)
CROSSREF_RATE_LIMIT = 1.0       # seconds between requests (be conservative)
UNPAYWALL_RATE_LIMIT = 0.1      # seconds between requests
PDF_DOWNLOAD_DELAY = 1.0        # seconds between PDF downloads

# ─── SEARCH DEFAULTS ────────────────────────────────────────
DEFAULT_MAX_RESULTS = 50        # papers per gap query
DEFAULT_YEAR_RANGE = (2000, 2026)
DEFAULT_MIN_CITATIONS = 0
MAX_QUERIES_PER_GAP = 3         # Claude Sonnet generates up to 3 queries per gap

# ─── OPENALEX CONCEPT FILTERING ──────────────────────────────
# Concept IDs for domain-specific filtering (dramatically improves relevance)
# Configure these via research_config.yaml concept_ids
# C2993150066 = Green innovation (Level 2, ~10K works)
# C126082660 = Digital transformation (Level 2, ~140K works)
OPENALEX_CONCEPT_IDS = ["C39389867", "C2778397978"]  # Default concepts — override via research_config.yaml

# ─── SEMANTIC SCHOLAR ─────────────────────────────────────────
SEMANTIC_SCHOLAR_BASE_URL = "https://api.semanticscholar.org/graph/v1"
SEMANTIC_SCHOLAR_RATE_LIMIT = 3.5       # seconds between requests (no API key)
SEMANTIC_SCHOLAR_RATE_LIMIT_WITH_KEY = 1.1  # seconds (with free API key)

# ─── CORE API ─────────────────────────────────────────────────
CORE_BASE_URL = "https://api.core.ac.uk/v3"
CORE_RATE_LIMIT = 1.0

# ─── SCI-HUB ──────────────────────────────────────────────────
SCIHUB_MIRRORS = ["https://sci-hub.st", "https://sci-hub.ru"]
SCIHUB_RATE_LIMIT = 5.0

# ─── RELEVANCE SCREENING ──────────────────────────────────────
RELEVANCE_SCREEN_THRESHOLD = 0.5
RELEVANCE_SCREEN_BATCH_SIZE = 15
RELEVANCE_SCREEN_TIMEOUT = 60

# ─── GOOGLE SCHOLAR SCRAPER ───────────────────────────────────
SCHOLAR_MIN_DELAY = 5.0
SCHOLAR_MAX_DELAY = 15.0
SCHOLAR_CAPTCHA_TIMEOUT = 300

# ─── PDF ACQUISITION CHAIN ───────────────────────────────────
PDF_SOURCE_CHAIN = ["openalex", "unpaywall", "semantic_scholar", "core", "scihub"]

# ─── CLAUDE MODELS ──────────────────────────────────────────
CLAUDE_SONNET_MODEL = "claude-sonnet-4-6"   # Lightweight: gap→query conversion
CLAUDE_OPUS_MODEL = "claude-opus-4-6"       # Deep: extraction + novelty assessment

# ─── TIMEOUTS ───────────────────────────────────────────────
API_REQUEST_TIMEOUT = 30        # seconds per HTTP request
API_MAX_RETRIES = 3
API_RETRY_BASE_DELAY = 2.0     # exponential: 2s, 4s, 8s

# ─── PAPER TYPE MAPPING ────────────────────────────────────
# OpenAlex type → Our Paper_Type enum
OPENALEX_TYPE_MAP = {
    "article": "Journal Article",
    "journal-article": "Journal Article",
    "review": "Review",
    "book-chapter": "Book Chapter",
    "book": "Book",
    "dissertation": "Dissertation",
    "proceedings-article": "Conference Paper",
    "conference-paper": "Conference Paper",
    "preprint": "Working Paper",
    "posted-content": "Working Paper",
    "report": "Report",
    "dataset": "Dataset",
    "editorial": "Editorial",
    "letter": "Letter",
    "erratum": "Erratum",
}

# ─── GAP NOVELTY TAB SCHEMA (legacy — replaced by GAP_MATRIX in original sheet) ──
GAP_NOVELTY_COLUMNS = [
    "PAPER_ID",
    "Gap_ID",
    "Gap_Statement",
    "Affects_Gap",           # Yes / No / Tangentially
    "Impact_Level",          # NOT ADDRESSED / PARTIALLY ADDRESSED / SUBSTANTIALLY COVERED / DIRECTLY TACKLED
    "Evidence_Summary",
    "Gap_Still_Valid",       # Yes / No / Partially
    "Validation_Reasoning",
    "What_Remains_Open",
    "Implications_For_PhD",
    "Assessed_By",
    "Assessed_At",
]

# ─── AUTO SHEET TABS (clone of original minus gap-specific) ─
# Note: GAP_NOVELTY removed — gap analysis now uses GAP_MATRIX in the original sheet
AUTO_SHEET_TABS = [
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
    "MASTER_VIEW",
    "Literature_Review_Summary",
]
