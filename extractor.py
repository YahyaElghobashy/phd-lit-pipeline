"""
PhD Literature Extraction Pipeline — Claude CLI Extractor
==========================================================
Spawns Claude Code CLI subprocesses to extract structured data from PDFs.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from config import (
    CLAUDE_CLI,
    CLAUDE_MODEL,
    CLAUDE_MAX_TURNS,
    CLAUDE_EFFORT,
    EXTRACTION_TIMEOUT_SECONDS,
    EXTRACTION_MAX_RETRIES,
    EXTRACTION_RETRY_DELAY,
    EXTRACTIONS_DIR,
    PDF_ROOT,
)
from extraction_prompt import build_system_prompt, build_user_prompt
from schemas import validate_extraction


class PaperExtractor:
    """Manages Claude Code CLI subprocesses for paper extraction."""

    def __init__(self):
        self.system_prompt = build_system_prompt()
        EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
        # Failure diagnostics for run reports
        self.last_failure_info: dict | None = None
        self.last_attempts: list[dict] = []

    def extract(
        self,
        pdf_path: Path,
        gap_state: list[dict],
        paper_index: int,
        total_papers: int,
        on_status: callable = None,
    ) -> dict | None:
        """
        Extract structured data from a PDF using Claude CLI.

        Args:
            pdf_path: Path to the PDF file
            gap_state: Current unresolved gaps for context
            paper_index: 1-based index in the queue
            total_papers: Total papers in queue
            on_status: Optional callback for status updates (str -> None)

        Returns:
            Validated extraction dict, or None on failure.
        """
        self.last_attempts = []
        self.last_failure_info = None

        for attempt in range(EXTRACTION_MAX_RETRIES + 1):
            if attempt > 0:
                if on_status:
                    on_status(f"Retry {attempt}/{EXTRACTION_MAX_RETRIES} in {EXTRACTION_RETRY_DELAY}s...")
                time.sleep(EXTRACTION_RETRY_DELAY)

            result = self._run_extraction(
                pdf_path, gap_state, paper_index, total_papers, on_status
            )

            if result is not None:
                self.last_attempts = []
                self.last_failure_info = None
                return result

            # Record this attempt's failure
            attempt_info = {
                "attempt": attempt + 1,
                **(self.last_failure_info or {"reason": "Unknown failure"}),
            }
            self.last_attempts.append(attempt_info)

            if on_status and attempt < EXTRACTION_MAX_RETRIES:
                on_status(f"Extraction failed (attempt {attempt + 1})")

        return None

    def _run_extraction(
        self,
        pdf_path: Path,
        gap_state: list[dict],
        paper_index: int,
        total_papers: int,
        on_status: callable = None,
    ) -> dict | None:
        """Single extraction attempt."""
        self.last_failure_info = None
        attempt_start = time.time()

        user_prompt = build_user_prompt(
            str(pdf_path.resolve()),
            gap_state,
            paper_index,
            total_papers,
        )

        cmd = [
            CLAUDE_CLI,
            "-p", user_prompt,
            "--output-format", "json",
            "--model", CLAUDE_MODEL,
            "--max-turns", str(CLAUDE_MAX_TURNS),
            "--allowedTools", "Read",
            "--no-session-persistence",
            "--append-system-prompt", self.system_prompt,
        ]

        if on_status:
            on_status("Starting Claude Code subprocess...")

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(PDF_ROOT),
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

            # Wait with timeout
            try:
                process.wait(timeout=EXTRACTION_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                elapsed = round(time.time() - attempt_start, 1)
                reason = f"TIMEOUT after {EXTRACTION_TIMEOUT_SECONDS}s"
                self.last_failure_info = {
                    "reason": reason,
                    "details": f"Process killed after {elapsed}s. stderr: {''.join(stderr_lines)[:500]}",
                    "exit_code": -9,
                    "duration_seconds": elapsed,
                }
                if on_status:
                    on_status(reason)
                return None

            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

            stdout_full = "".join(stdout_lines)
            stderr_full = "".join(stderr_lines)
            elapsed = round(time.time() - attempt_start, 1)

            if process.returncode != 0:
                reason = f"Claude exited with code {process.returncode}"
                self.last_failure_info = {
                    "reason": reason,
                    "details": stderr_full[:500] or stdout_full[:500],
                    "exit_code": process.returncode,
                    "duration_seconds": elapsed,
                }
                if on_status:
                    on_status(reason)
                    if stderr_full.strip():
                        on_status(f"stderr: {stderr_full[:200]}")
                return None

            # Parse the output
            extraction = self._parse_output(stdout_full, on_status)
            if extraction is None:
                self.last_failure_info = {
                    "reason": "Could not find extraction data in Claude output",
                    "details": stdout_full[:500],
                    "exit_code": 0,
                    "duration_seconds": elapsed,
                }
                return None

            # Validate
            is_valid, errors = validate_extraction(extraction)
            if not is_valid:
                reason = f"Validation failed: {'; '.join(errors[:3])}"
                self.last_failure_info = {
                    "reason": reason,
                    "details": f"All errors: {'; '.join(errors[:10])}",
                    "exit_code": 0,
                    "duration_seconds": elapsed,
                }
                if on_status:
                    on_status(reason)
                return None

            # Ensure PAPER_ID consistency
            pid = extraction.get("paper_id", "")
            for section_key in extraction:
                if isinstance(extraction[section_key], dict) and "PAPER_ID" in extraction[section_key]:
                    extraction[section_key]["PAPER_ID"] = pid

            # Set extraction metadata
            if "1_IDENTIFICATION" in extraction:
                extraction["1_IDENTIFICATION"]["Date_Extracted"] = datetime.now().strftime("%Y-%m-%d")
                extraction["1_IDENTIFICATION"]["Extracted_By"] = "Claude Code Pipeline"

            # Compute relevance score if not already done
            self._ensure_relevance_score(extraction)

            # Save locally
            extraction_file = self._save_extraction(extraction)
            extraction["_extraction_file"] = str(extraction_file)

            if on_status:
                rel = extraction.get("9_RELEVANCE", {})
                on_status(
                    f"Extracted: {pid} | "
                    f"Relevance: {rel.get('Weighted_Score', '?')} ({rel.get('Relevance_Tier', '?')})"
                )

            return extraction

        except FileNotFoundError:
            elapsed = round(time.time() - attempt_start, 1)
            self.last_failure_info = {
                "reason": "claude CLI not found",
                "details": "Claude Code CLI binary not on PATH. Is it installed?",
                "exit_code": None,
                "duration_seconds": elapsed,
            }
            if on_status:
                on_status(f"'claude' CLI not found. Is Claude Code installed?")
            return None
        except Exception as e:
            elapsed = round(time.time() - attempt_start, 1)
            self.last_failure_info = {
                "reason": f"Unexpected error: {type(e).__name__}",
                "details": str(e)[:500],
                "exit_code": None,
                "duration_seconds": elapsed,
            }
            if on_status:
                on_status(f"Unexpected error: {e}")
            return None

    def _parse_output(self, stdout: str, on_status: callable = None) -> dict | None:
        """
        Parse Claude CLI JSON output.
        --output-format json returns: {"type":"result","result":"<json_string>","...}
        """
        stdout = stdout.strip()
        if not stdout:
            if on_status:
                on_status("Empty output from Claude CLI")
            return None

        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            # Maybe it's raw JSON without envelope
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                if on_status:
                    on_status(f"Failed to parse JSON output (first 200 chars): {stdout[:200]}")
                return None

        # Handle envelope format
        if isinstance(envelope, dict) and "result" in envelope:
            result = envelope["result"]
            if isinstance(result, dict):
                return result
            if isinstance(result, str):
                # Result is a JSON string inside the envelope
                try:
                    return json.loads(result)
                except json.JSONDecodeError:
                    # Try to extract JSON from within the string
                    return self._extract_json_from_text(result, on_status)
        elif isinstance(envelope, dict) and "paper_id" in envelope:
            # Direct extraction JSON (no envelope)
            return envelope

        if on_status:
            on_status("Could not find extraction data in Claude output")
        return None

    def _extract_json_from_text(self, text: str, on_status: callable = None) -> dict | None:
        """Try to extract a JSON object from text that might contain markdown or other wrapping."""
        # Look for the outermost { ... }
        start = text.find("{")
        if start == -1:
            return None

        # Find matching closing brace
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        if on_status:
                            on_status("Found JSON-like structure but couldn't parse it")
                        return None
        return None

    def _ensure_relevance_score(self, extraction: dict):
        """Compute weighted relevance score if not already computed."""
        rel = extraction.get("9_RELEVANCE", {})
        if not rel:
            return

        try:
            topic = float(rel.get("Topic_Alignment", 0))
            variables = float(rel.get("Variable_Usefulness", 0))
            methodology = float(rel.get("Methodological_Value", 0))
            theory = float(rel.get("Theoretical_Contribution", 0))
            recency = float(rel.get("Recency", 0))
            quality = float(rel.get("Publication_Quality", 0))

            score = (
                topic * 0.25
                + variables * 0.20
                + methodology * 0.20
                + theory * 0.15
                + recency * 0.10
                + quality * 0.10
            )
            score = round(score, 2)
            rel["Weighted_Score"] = score

            if score >= 4.5:
                rel["Relevance_Tier"] = "Essential"
            elif score >= 3.5:
                rel["Relevance_Tier"] = "Highly Relevant"
            elif score >= 2.5:
                rel["Relevance_Tier"] = "Moderate"
            else:
                rel["Relevance_Tier"] = "Low"
        except (ValueError, TypeError):
            pass

    def _save_extraction(self, extraction: dict) -> Path:
        """Save extraction JSON locally."""
        paper_id = extraction.get("paper_id", "unknown")
        # Sanitize filename
        safe_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in paper_id)
        filepath = EXTRACTIONS_DIR / f"{safe_id}.json"

        # Handle duplicates
        counter = 2
        while filepath.exists():
            filepath = EXTRACTIONS_DIR / f"{safe_id}_{counter}.json"
            counter += 1

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(extraction, f, indent=2, ensure_ascii=False)

        return filepath
