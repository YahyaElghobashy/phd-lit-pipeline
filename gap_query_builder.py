"""
PhD Literature Discovery Pipeline — Gap-to-Query Builder
==========================================================
Reads unresolved gaps from the original GAP_TRACKER sheet and converts
each gap statement into optimal OpenAlex search queries using Claude Sonnet.

Uses the same Claude CLI subprocess pattern as gap_coverage_analyzer.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box

from populator import SheetPopulator, retry_on_api_error
from discovery_config import (
    ORIGINAL_SPREADSHEET_ID,
    CLAUDE_SONNET_MODEL,
    MAX_QUERIES_PER_GAP,
)
from config import CLAUDE_CLI

console = Console()


# ─── SYSTEM PROMPT ──────────────────────────────────────────

QUERY_BUILDER_SYSTEM_PROMPT = """You are a research query specialist helping a PhD student discover papers relevant to specific research gaps.

PhD context: "Women on Boards: An International Study in Governance and Wealth Creation" — a three-paper dissertation studying technology & digital transformation outcomes, environmental sustainability / esg outcomes, and innovation as a mediating pathway.

Your task: Convert a research gap statement into optimal academic search queries for OpenAlex (a scholarly search engine).

RULES:
1. Generate exactly {max_queries} search queries per gap, each taking a different angle
2. Queries should be 4-8 words — the sweet spot for academic search engines
3. Use specific academic terminology, not colloquial language
4. First query: most direct/literal translation of the gap
5. Second query: broader conceptual framing or alternative terminology
6. Third query: methodological or contextual angle (if applicable)
7. Avoid overly generic queries like "corporate governance" alone
8. Include relevant variable names, methodological terms, or geographic contexts from the gap
9. Do NOT include quotes or boolean operators — OpenAlex uses semantic search

Return ONLY a valid JSON array of objects. No markdown, no code fences, no explanation.

Format:
[
  {{
    "gap_id": "GAP_XXX",
    "gap_statement": "...",
    "queries": [
      {{"query": "...", "angle": "direct"}},
      {{"query": "...", "angle": "broader"}},
      {{"query": "...", "angle": "methodological"}}
    ],
    "search_rationale": "Brief explanation of query strategy"
  }}
]"""


# ─── GAP READER ─────────────────────────────────────────────

class GapReader:
    """Reads gaps from the original GAP_TRACKER sheet."""

    def __init__(self):
        self._pop = SheetPopulator(on_status=lambda msg: console.print(f"  [dim]{msg}[/dim]"))
        # Override spreadsheet to point to original
        self._client = None
        self._spreadsheet = None

    def _ensure_connected(self):
        if self._client is None:
            from populator import authenticate
            self._client = authenticate()
            self._spreadsheet = self._client.open_by_key(ORIGINAL_SPREADSHEET_ID)

    @retry_on_api_error()
    def get_all_gaps(self) -> list[dict]:
        """Read all gaps from the original GAP_TRACKER."""
        self._ensure_connected()
        ws = self._spreadsheet.worksheet("GAP_TRACKER")
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
                "feasibility": str(row.get("Feasibility", "")),
                "novelty": str(row.get("Novelty", "")),
                "priority_score": str(row.get("Priority_Score", "")),
                "status": str(row.get("Status", "")),
                "coverage_level": str(row.get("Coverage_Level", "")),
                "paper_assignment": str(row.get("Paper_Assignment", "")),
                "variables_needed": str(row.get("Variables_Needed", "")),
                "methodology_needed": str(row.get("Methodology_Needed", "")),
            })
        return gaps

    def get_unresolved_gaps(self) -> list[dict]:
        """Get gaps that are NOT 'DIRECTLY TACKLED' — i.e., still open."""
        all_gaps = self.get_all_gaps()
        return [
            g for g in all_gaps
            if g["coverage_level"].upper() != "DIRECTLY TACKLED"
            and g["status"].upper() not in ("CLOSED", "RESOLVED", "DIRECTLY TACKLED")
        ]


# ─── QUERY BUILDER ──────────────────────────────────────────

class GapQueryBuilder:
    """
    Converts gap statements into search queries using Claude Sonnet via CLI.
    Batches gaps together for efficiency.
    """

    BATCH_SIZE = 15  # Gaps per Claude call (Sonnet is fast, but prompts shouldn't be huge)
    TIMEOUT = 120    # 2 minutes per batch (Sonnet is fast)
    MAX_RETRIES = 2
    RETRY_DELAY = 10

    def __init__(self):
        self._reader = GapReader()

    def build_queries(self, gaps: list[dict] | None = None) -> list[dict]:
        """
        Convert gaps to search queries.

        Args:
            gaps: Optional pre-loaded gap list. If None, reads from sheet.

        Returns:
            List of {gap_id, gap_statement, queries: [{query, angle}], search_rationale}
        """
        if gaps is None:
            console.print("[bold blue]Reading gaps from GAP_TRACKER...[/]")
            gaps = self._reader.get_unresolved_gaps()

        if not gaps:
            console.print("[yellow]No unresolved gaps found.[/]")
            return []

        console.print(f"[green]Found {len(gaps)} unresolved gaps[/]\n")

        # Batch gaps for efficiency
        batches = [gaps[i:i + self.BATCH_SIZE] for i in range(0, len(gaps), self.BATCH_SIZE)]
        all_results = []

        for batch_idx, batch in enumerate(batches):
            console.print(f"[bold blue]Batch {batch_idx + 1}/{len(batches)} ({len(batch)} gaps)...[/]")

            result = None
            for attempt in range(self.MAX_RETRIES + 1):
                if attempt > 0:
                    console.print(f"  [yellow]Retry {attempt}/{self.MAX_RETRIES} in {self.RETRY_DELAY}s...[/]")
                    time.sleep(self.RETRY_DELAY)

                result = self._run_claude_query_generation(batch)
                if result is not None:
                    break

            if result is None:
                console.print(f"  [red]All retries exhausted for batch {batch_idx + 1}[/]")
                # Fall back to simple keyword extraction
                for gap in batch:
                    all_results.append(self._fallback_queries(gap))
            else:
                all_results.extend(result)

        return all_results

    def _build_gap_text(self, gaps: list[dict]) -> str:
        """Format gaps for the Claude prompt."""
        lines = []
        for g in gaps:
            lines.append(
                f"- Gap_ID: {g['gap_id']}\n"
                f"  Type: {g['gap_type']}\n"
                f"  Statement: {g['gap_statement']}\n"
                f"  Variables: {g.get('variables_needed', '')}\n"
                f"  Methodology: {g.get('methodology_needed', '')}\n"
                f"  Paper Assignment: {g.get('paper_assignment', '')}"
            )
        return "\n\n".join(lines)

    def _run_claude_query_generation(self, gaps: list[dict]) -> list[dict] | None:
        """Spawn Claude Sonnet CLI to generate queries for a batch of gaps."""
        gap_text = self._build_gap_text(gaps)
        user_prompt = (
            f"Convert these {len(gaps)} research gaps into OpenAlex search queries.\n\n"
            f"GAPS:\n{gap_text}\n\n"
            f"Generate {MAX_QUERIES_PER_GAP} queries per gap. Return ONLY a JSON array."
        )

        system_prompt = QUERY_BUILDER_SYSTEM_PROMPT.format(max_queries=MAX_QUERIES_PER_GAP)

        cmd = [
            CLAUDE_CLI,
            "-p", user_prompt,
            "--output-format", "json",
            "--model", CLAUDE_SONNET_MODEL,
            "--max-turns", "1",
            "--no-session-persistence",
            "--append-system-prompt", system_prompt,
        ]

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(f"Generating queries ({len(gaps)} gaps)...")

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
                    process.wait(timeout=self.TIMEOUT)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    console.print(f"  [red]TIMEOUT after {self.TIMEOUT}s[/red]")
                    return None

                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)

            stdout_full = "".join(stdout_lines)
            stderr_full = "".join(stderr_lines)

            if process.returncode != 0:
                console.print(f"  [red]Claude exited with code {process.returncode}[/red]")
                if stderr_full.strip():
                    console.print(f"  [dim]stderr: {stderr_full[:300]}[/dim]")
                return None

            return self._parse_output(stdout_full)

        except FileNotFoundError:
            console.print("  [red]'claude' CLI not found. Is Claude Code installed?[/red]")
            return None
        except Exception as e:
            console.print(f"  [red]Unexpected error: {e}[/red]")
            return None

    def _parse_output(self, stdout: str) -> list[dict] | None:
        """Parse Claude CLI JSON output expecting a JSON array of query objects."""
        stdout = stdout.strip()
        if not stdout:
            console.print("  [red]Empty output from Claude CLI[/red]")
            return None

        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            return self._extract_json_array(stdout)

        # Handle direct array
        if isinstance(envelope, list):
            return envelope

        # Handle Claude CLI envelope: {"type":"result","result":"<content>"}
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

        console.print("  [red]Could not find query array in Claude output[/red]")
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
                        console.print("  [red]Found JSON-like array but couldn't parse[/red]")
                        return None
        return None

    def _fallback_queries(self, gap: dict) -> dict:
        """
        Generate simple keyword-based queries as fallback if Claude fails.
        Extracts key terms from the gap statement.
        """
        statement = gap["gap_statement"]
        gap_type = gap["gap_type"].lower()

        # Extract key terms: remove common words, take first meaningful phrases
        stop_words = {
            "the", "a", "an", "of", "in", "for", "to", "and", "or", "is", "are",
            "this", "that", "these", "those", "has", "have", "been", "be", "was",
            "were", "will", "would", "could", "should", "may", "might", "can",
            "no", "not", "how", "what", "why", "when", "where", "which", "who",
            "does", "do", "did", "on", "at", "by", "with", "from", "as", "but",
            "if", "so", "it", "its", "their", "there", "our", "we", "they",
            "between", "whether", "more", "most", "such", "into",
        }

        words = statement.replace(",", "").replace(".", "").replace(":", "").split()
        key_words = [w for w in words if w.lower() not in stop_words and len(w) > 2]

        # Build queries from key terms
        queries = []
        if len(key_words) >= 4:
            queries.append({"query": " ".join(key_words[:6]), "angle": "direct"})
        else:
            queries.append({"query": " ".join(key_words[:8]), "angle": "direct"})

        # Add type-based query
        type_terms = {
            "theoretical": "theory framework",
            "methodological": "methodology estimation",
            "variable": "measurement variable proxy",
            "contextual": "cross-country institutional context",
            "mechanism": "mechanism channel pathway",
        }
        extra = type_terms.get(gap_type, "board gender diversity")
        if len(key_words) >= 3:
            queries.append({"query": f"{' '.join(key_words[:3])} {extra}", "angle": "broader"})
        else:
            queries.append({"query": f"{statement[:40]} {extra}", "angle": "broader"})

        # Generic governance query
        queries.append({"query": "women board directors firm performance governance", "angle": "methodological"})

        return {
            "gap_id": gap["gap_id"],
            "gap_statement": gap["gap_statement"],
            "queries": queries[:MAX_QUERIES_PER_GAP],
            "search_rationale": "Fallback: keyword extraction (Claude unavailable)",
        }


# ─── DISPLAY ────────────────────────────────────────────────

def show_query_results(results: list[dict]):
    """Display generated queries in a Rich table."""
    table = Table(
        title="Generated Search Queries",
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold magenta",
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Gap ID", width=10)
    table.add_column("Gap Statement", max_width=40, overflow="fold")
    table.add_column("Query", max_width=35, overflow="fold")
    table.add_column("Angle", width=15)

    for r in results:
        gap_id = r.get("gap_id", "?")
        statement = r.get("gap_statement", "")[:60]
        queries = r.get("queries", [])

        for i, q in enumerate(queries):
            table.add_row(
                gap_id if i == 0 else "",
                statement if i == 0 else "",
                q.get("query", ""),
                q.get("angle", ""),
            )

    console.print(table)
    console.print()

    # Summary
    total_queries = sum(len(r.get("queries", [])) for r in results)
    console.print(f"[bold green]Generated {total_queries} queries for {len(results)} gaps[/]")


# ─── STANDALONE ENTRY ────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert research gaps to search queries")
    parser.add_argument("--dry-run", action="store_true", help="Show gaps without generating queries")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of gaps to process")
    parser.add_argument("--fallback-only", action="store_true", help="Use keyword fallback, skip Claude")
    args = parser.parse_args()

    reader = GapReader()
    console.print("[bold blue]Reading unresolved gaps...[/]")
    gaps = reader.get_unresolved_gaps()
    console.print(f"[green]Found {len(gaps)} unresolved gaps[/]\n")

    if args.dry_run:
        for g in gaps:
            console.print(f"  {g['gap_id']} [{g['gap_type']}] {g['gap_statement'][:80]}...")
        console.print(f"\n[dim]Total: {len(gaps)} gaps would generate ~{len(gaps) * MAX_QUERIES_PER_GAP} queries[/]")
    else:
        if args.limit:
            gaps = gaps[:args.limit]

        builder = GapQueryBuilder()

        if args.fallback_only:
            results = [builder._fallback_queries(g) for g in gaps]
        else:
            results = builder.build_queries(gaps)

        show_query_results(results)
