# PhD Literature Review Extraction Pipeline

An automated pipeline for PhD literature reviews that extracts structured data from academic PDFs using Claude AI, tracks research gaps with a cumulative model, discovers new papers via OpenAlex, and provides a visual dashboard.

## Features

- **Automated PDF Extraction** — Claude reads papers and extracts structured data into 11+ Google Sheets tabs (identification, methodology, variables, findings, gaps, and more)
- **Gap Tracking** — Identifies research gaps, maintains a cumulative GAP_MATRIX showing how each paper contributes to closing gaps
- **Paper Discovery** — Converts unresolved gaps into search queries, searches OpenAlex, downloads open-access PDFs, and extracts them
- **Visual Dashboard** — React + FastAPI web interface for monitoring the pipeline, viewing papers, gaps, run history, and an admin console
- **Fully Configurable** — A single `research_config.yaml` defines your entire research project; a setup wizard generates all pipeline files

## Quick Start

### Prerequisites

- Python 3.11+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) installed
- A Google Cloud project with Sheets API and Drive API enabled

### Setup

1. **Clone and install:**
   ```bash
   git clone https://github.com/YahyaElghobashy/phd-lit-pipeline.git
   cd phd-lit-pipeline
   pip install -r requirements.txt
   ```

2. **Configure your research project:**

   Option A — **Interactive wizard:**
   ```bash
   python setup_wizard.py
   ```

   Option B — **Use the master prompt** ([master_prompt.md](master_prompt.md)):
   Paste the master prompt into a Claude.com chat, answer its questions about your research, and it generates a `research_config.yaml` for you. Then:
   ```bash
   python setup_wizard.py --from-config
   ```

3. **Set up Google OAuth:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Enable Google Sheets API + Google Drive API
   - Create OAuth client (Desktop app)
   - Download as `client_secret.json` to the pipeline root

4. **Run the pipeline:**
   ```bash
   python main.py --dry-run    # Preview
   python main.py              # Extract all papers
   ```

5. **Start the dashboard:**
   ```bash
   # Backend
   cd dashboard && python -m uvicorn backend.app:app --port 8765 --reload

   # Frontend (new terminal)
   cd dashboard/frontend && npm install && npx vite --port 5173
   ```

## Architecture

```
research_config.yaml  →  setup_wizard.py  →  generates pipeline files
                                               ├── extraction_prompt.py
                                               ├── schemas.py
                                               ├── config.py
                                               ├── discovery_config.py
                                               ├── gap_matrix_analyzer.py
                                               ├── gap_query_builder.py
                                               ├── Google Sheets
                                               └── Local folders

PDFs → main.py → Claude CLI → structured JSON → Google Sheets
       ↕                                           ↕
    gap_matrix_analyzer.py ←── GAP_TRACKER ←── gap_analyzer.py
       ↓
    discover.py → OpenAlex → new PDFs → extract → analyze
```

## Configuration

The `research_config.yaml` file defines everything research-specific:

- **Project**: title, researcher name
- **Papers**: dissertation chapters with focus areas
- **Research context**: summary, critical notes, available databases
- **Key scholars**: whose citations to track across papers
- **Theories**: theoretical frameworks used
- **Custom sections**: topic-specific extraction sections beyond the standard 11
- **Dropdowns**: all enum values for classification fields
- **Relevance rubric**: scoring dimensions with weights

See [`research_config.example.yaml`](research_config.example.yaml) for a fully commented template, and [`research_config_yara.yaml`](research_config_yara.yaml) for a real-world example.

## Code Generation

The `codegen/` directory contains generators that produce pipeline files from your config:

| Generator | Produces | What it does |
|-----------|----------|-------------|
| `generate_extraction_prompt.py` | `extraction_prompt.py` | 350-line Claude system prompt with your research context, schema, rubric |
| `generate_schemas.py` | `schemas.py` | Column definitions for Google Sheets tabs |
| `generate_config.py` | updates `config.py` | Sets spreadsheet IDs and tab list |
| `generate_discovery_config.py` | updates `discovery_config.py` | Sets auto sheet IDs and API email |
| `generate_gap_prompts.py` | updates gap analyzers | Sets dissertation title in gap screening/analysis prompts |

These are run automatically by `setup_wizard.py`. To re-run after config changes:
```bash
python setup_wizard.py --generate-only
```

Or use the Admin page in the dashboard (`/admin` → Regenerate).

## Dashboard

The web dashboard provides:

- **Dashboard** — Overview stats (papers processed, gaps tracked, runs completed)
- **Papers** — Browse extracted papers with search/filter
- **Gap Tracker** — View and filter research gaps
- **Run History** — View past pipeline runs
- **Actions** — Run pipeline commands from the UI
- **Discovery** — Search for new papers, generate queries, review results
- **Admin** — Edit research config, manage files, view sheet structure

## License

MIT
