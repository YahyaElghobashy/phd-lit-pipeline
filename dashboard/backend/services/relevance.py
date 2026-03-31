"""AI relevance screening — uses Claude Sonnet to score papers against gaps."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

# Import config values
try:
    from config import CLAUDE_CLI
except ImportError:
    CLAUDE_CLI = "claude"

try:
    from discovery_config import CLAUDE_SONNET_MODEL
except ImportError:
    CLAUDE_SONNET_MODEL = "claude-sonnet-4-6"

BATCH_SIZE = 15  # papers per Sonnet call
TIMEOUT = 60     # seconds per batch

SYSTEM_PROMPT = """\
You are a research paper relevance assessor for a PhD literature review on \
the configured research topic and domain.

You will receive a set of research GAPS (statements of what the literature lacks) \
and a batch of PAPERS (title + abstract).

For each paper, assess how relevant it is to ANY of the provided gaps.

Score each paper 0-10:
- 9-10: Directly addresses one or more gaps (exact topic match)
- 7-8:  Closely related, could provide useful evidence
- 5-6:  Somewhat relevant, tangentially related
- 3-4:  Weak connection, mostly different topic
- 0-2:  Irrelevant to all gaps

Return ONLY a JSON array:
[
  {"paper_index": 0, "relevance_score": 8, "reason": "Directly studies the core research variables..."},
  {"paper_index": 1, "relevance_score": 2, "reason": "Focuses on unrelated supply chain topic"},
  ...
]

Be strict. Academic papers often have overlapping keywords but address different research questions. \
Only score ≥7 if the paper genuinely contributes evidence toward filling the gap."""


def assess_relevance(
    papers: list[dict],
    gap_statements: dict[str, str],  # gap_id -> statement
) -> list[dict]:
    """
    Score each paper's relevance to the given gaps using Claude Sonnet.

    Returns list of {paper_index, relevance_score, reason}.
    Papers without scores get default score=0.
    """
    if not papers or not gap_statements:
        return [{"paper_index": i, "relevance_score": 0, "reason": "No gaps provided"} for i in range(len(papers))]

    all_scores: list[dict] = []

    # Process in batches
    for batch_start in range(0, len(papers), BATCH_SIZE):
        batch = papers[batch_start : batch_start + BATCH_SIZE]
        batch_scores = _score_batch(batch, gap_statements, batch_start)
        all_scores.extend(batch_scores)

    # Fill in any missing papers with score 0
    scored_indices = {s["paper_index"] for s in all_scores}
    for i in range(len(papers)):
        if i not in scored_indices:
            all_scores.append({"paper_index": i, "relevance_score": 0, "reason": "Not scored"})

    return sorted(all_scores, key=lambda x: x["paper_index"])


def _score_batch(
    batch: list[dict],
    gap_statements: dict[str, str],
    index_offset: int,
) -> list[dict]:
    """Call Claude Sonnet to score one batch of papers."""
    # Build gap text
    gap_lines = []
    for gid, stmt in gap_statements.items():
        gap_lines.append(f"- {gid}: {stmt}")
    gaps_text = "\n".join(gap_lines)

    # Build paper text
    paper_lines = []
    for i, p in enumerate(batch):
        idx = index_offset + i
        title = p.get("title", "Unknown")
        abstract = p.get("abstract", "No abstract available")
        year = p.get("year", "?")
        citations = p.get("citation_count", 0)
        paper_lines.append(f"{idx}. Title: {title}\n   Abstract: {abstract}\n   Year: {year}, Citations: {citations}")
    papers_text = "\n\n".join(paper_lines)

    user_prompt = (
        f"Assess the relevance of these {len(batch)} papers to the research gaps below.\n\n"
        f"GAPS:\n{gaps_text}\n\n"
        f"PAPERS:\n{papers_text}\n\n"
        f"Return ONLY a JSON array with paper_index, relevance_score (0-10), and reason for each paper."
    )

    cmd = [
        CLAUDE_CLI,
        "-p", user_prompt,
        "--output-format", "json",
        "--model", CLAUDE_SONNET_MODEL,
        "--max-turns", "1",
        "--no-session-persistence",
        "--append-system-prompt", SYSTEM_PROMPT,
    ]

    try:
        env = {**__import__("os").environ, "CLAUDE_CODE_HEADLESS": "1"}
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT, env=env
        )
        if proc.returncode != 0:
            print(f"[relevance] Claude returned exit code {proc.returncode}: {proc.stderr[:200]}")
            return []

        return _parse_scores(proc.stdout)
    except subprocess.TimeoutExpired:
        print("[relevance] Claude timed out")
        return []
    except FileNotFoundError:
        print(f"[relevance] Claude CLI not found at: {CLAUDE_CLI}")
        return []
    except Exception as e:
        print(f"[relevance] Error: {e}")
        return []


def _parse_scores(stdout: str) -> list[dict]:
    """Parse Claude's JSON output, handling envelope format."""
    try:
        # Try direct parse
        data = json.loads(stdout)
        # Handle envelope: {"type":"result","result":"<json>"}
        if isinstance(data, dict) and "result" in data:
            result = data["result"]
            if isinstance(result, str):
                data = json.loads(result)
            else:
                data = result
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: extract JSON array from text
    try:
        start = stdout.index("[")
        end = stdout.rindex("]") + 1
        return json.loads(stdout[start:end])
    except (ValueError, json.JSONDecodeError):
        print(f"[relevance] Could not parse output: {stdout[:200]}")
        return []
