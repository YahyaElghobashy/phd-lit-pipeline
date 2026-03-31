#!/usr/bin/env python3
"""
PhD Literature Discovery Pipeline — Google Scholar Scraper
============================================================
Headless Chrome scraper using Playwright for Google Scholar searches.
Supports human CAPTCHA intervention when needed.

Usage:
    python google_scholar_scraper.py --query "your research topic keywords" --max-results 10
    python google_scholar_scraper.py --query "women directors firm performance" --headless
"""
from __future__ import annotations

import argparse
import random
import re
import sys
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from rich.console import Console
from rich.table import Table
from rich import box

from discovery_config import (
    SCHOLAR_MIN_DELAY,
    SCHOLAR_MAX_DELAY,
    SCHOLAR_CAPTCHA_TIMEOUT,
)

console = Console()

# User agents to rotate through
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


class GoogleScholarScraper:
    """
    Google Scholar scraper using Playwright (Chromium).

    Features:
    - Parses titles, authors, year, snippet, citation count, PDF links
    - Returns normalized paper dicts matching the pipeline's standard format
    - Detects CAPTCHAs and pauses for human intervention
    - Random delays between requests to avoid detection
    """

    def __init__(self, headless: bool = False):
        """
        Args:
            headless: If True, run browser in headless mode.
                      Default False — allows human CAPTCHA solving.
        """
        self._headless = headless
        self._browser = None
        self._context = None
        self._page = None

    def _ensure_browser(self):
        """Launch browser if not already running."""
        if self._browser is not None:
            return

        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        ua = random.choice(_USER_AGENTS)

        self._browser = self._playwright.chromium.launch(
            headless=self._headless,
        )
        self._context = self._browser.new_context(
            user_agent=ua,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        self._page = self._context.new_page()

    def close(self):
        """Close the browser."""
        if self._browser:
            self._browser.close()
            self._browser = None
        if hasattr(self, "_playwright") and self._playwright:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def search(
        self,
        query: str,
        max_results: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[dict]:
        """
        Search Google Scholar and return normalized paper dicts.

        Args:
            query: Search query string
            max_results: Maximum papers to return
            year_from: Filter by year >= this
            year_to: Filter by year <= this

        Returns:
            List of normalized paper dicts
        """
        self._ensure_browser()
        papers = []

        # Build URL
        url = f"https://scholar.google.com/scholar?q={quote_plus(query)}&hl=en"
        if year_from:
            url += f"&as_ylo={year_from}"
        if year_to:
            url += f"&as_yhi={year_to}"

        console.print(f"  [blue]Navigating to Google Scholar...[/]")

        page_num = 0
        while len(papers) < max_results:
            page_url = url if page_num == 0 else f"{url}&start={page_num * 10}"

            # Random delay before navigation
            delay = random.uniform(SCHOLAR_MIN_DELAY, SCHOLAR_MAX_DELAY)
            if page_num > 0:
                console.print(f"  [dim]Waiting {delay:.1f}s before next page...[/]")
                time.sleep(delay)

            try:
                self._page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                console.print(f"  [red]Navigation failed: {e}[/]")
                break

            # Check for CAPTCHA
            if self._detect_captcha():
                resolved = self._wait_for_human_captcha()
                if not resolved:
                    console.print("  [red]CAPTCHA not resolved — aborting[/]")
                    break

            # Parse results from this page
            page_papers = self._parse_results_page()

            if not page_papers:
                break  # No more results

            papers.extend(page_papers)
            console.print(f"  [green]Page {page_num + 1}: {len(page_papers)} results (total: {len(papers)})[/]")

            page_num += 1

            # Check if there's a "Next" button
            next_btn = self._page.query_selector('button[aria-label="Next"]') or self._page.query_selector('.gs_ico_nav_next')
            if not next_btn:
                break

        return papers[:max_results]

    def _detect_captcha(self) -> bool:
        """Check if Google is showing a CAPTCHA page."""
        try:
            content = self._page.content()
            captcha_indicators = [
                "unusual traffic",
                "not a robot",
                "captcha",
                "recaptcha",
                "sorry/index",
                "automated requests",
            ]
            content_lower = content.lower()
            return any(indicator in content_lower for indicator in captcha_indicators)
        except Exception:
            return False

    def _wait_for_human_captcha(self) -> bool:
        """
        Wait for a human to solve the CAPTCHA.

        If running headless, this won't work — the user needs headed mode.
        Prints a prompt and polls the page every 2s for up to CAPTCHA_TIMEOUT.
        """
        console.print()
        console.print("[bold yellow]" + "=" * 60 + "[/]")
        console.print("[bold yellow]  CAPTCHA DETECTED — Human intervention needed![/]")
        console.print("[bold yellow]  Please solve the CAPTCHA in the browser window.[/]")
        console.print("[bold yellow]" + "=" * 60 + "[/]")
        console.print()

        if self._headless:
            console.print("[red]Cannot solve CAPTCHA in headless mode. Re-run without --headless.[/]")
            return False

        start = time.time()
        while time.time() - start < SCHOLAR_CAPTCHA_TIMEOUT:
            time.sleep(2)
            if not self._detect_captcha():
                console.print("[green]  CAPTCHA resolved! Resuming...[/]")
                time.sleep(1)  # Brief pause after CAPTCHA
                return True
            elapsed = int(time.time() - start)
            if elapsed % 10 == 0:
                remaining = int(SCHOLAR_CAPTCHA_TIMEOUT - elapsed)
                console.print(f"  [dim]Waiting for CAPTCHA... ({remaining}s remaining)[/]")

        console.print("[red]  CAPTCHA timeout — giving up[/]")
        return False

    def _parse_results_page(self) -> list[dict]:
        """Parse all result entries from the current page."""
        papers = []

        # Google Scholar results are in div.gs_r elements
        result_elements = self._page.query_selector_all("div.gs_r.gs_or.gs_scl")

        for el in result_elements:
            paper = self._parse_single_result(el)
            if paper:
                papers.append(paper)

        return papers

    def _parse_single_result(self, element) -> dict | None:
        """Parse a single Google Scholar result element into a normalized dict."""
        try:
            # Title and URL
            title_el = element.query_selector("h3.gs_rt a")
            if not title_el:
                # Try alternate selector (some results don't have links)
                title_el = element.query_selector("h3.gs_rt")
                if not title_el:
                    return None

            title = title_el.inner_text().strip()
            # Clean up title (remove [PDF], [HTML], [BOOK] prefixes)
            title = re.sub(r'^\[(PDF|HTML|BOOK|CITATION)\]\s*', '', title)

            url = ""
            if title_el.get_attribute("href"):
                url = title_el.get_attribute("href")

            # Authors, source, year line
            meta_el = element.query_selector("div.gs_a")
            authors = ""
            year = ""
            journal = ""
            if meta_el:
                meta_text = meta_el.inner_text()
                # Format varies: "A Author, B Author - Journal Name, Year - publisher"
                # or "A Author… - …, Year - …"
                # Extract year from anywhere in the meta text first
                year_match = re.search(r'\b(19|20)\d{2}\b', meta_text)
                if year_match:
                    year = year_match.group()

                parts = meta_text.split(" - ")
                if parts:
                    authors = parts[0].strip()
                if len(parts) >= 2:
                    # Journal is the second part (minus the year)
                    journal_part = parts[1].strip()
                    journal = re.sub(r',?\s*(19|20)\d{2}', '', journal_part).strip().rstrip(',')

            # Snippet/abstract
            snippet_el = element.query_selector("div.gs_rs")
            snippet = snippet_el.inner_text().strip() if snippet_el else ""

            # Citation count
            cite_count = "0"
            cite_links = element.query_selector_all("div.gs_fl.gs_flb a")
            for link in cite_links:
                link_text = link.inner_text()
                cite_match = re.search(r'Cited by (\d+)', link_text)
                if cite_match:
                    cite_count = cite_match.group(1)
                    break

            # PDF link (if available — shown as [PDF] link on the right)
            pdf_url = ""
            pdf_link = element.query_selector("div.gs_or_ggsm a")
            if pdf_link:
                pdf_url = pdf_link.get_attribute("href") or ""

            # Build paper_id
            first_author = "Unknown"
            if authors:
                first = authors.split(",")[0].strip()
                parts = first.split()
                first_author = parts[-1] if parts else "Unknown"

            keyword = ""
            if title:
                skip_words = {"the", "a", "an", "of", "in", "for", "to", "and", "or", "is", "are", "on", "how", "does"}
                words = re.sub(r'[^\w\s]', '', title).split()
                for w in words:
                    if w.lower() not in skip_words and len(w) > 2:
                        keyword = w
                        break

            paper_id = f"{first_author}_{year}_{keyword}" if first_author and year else f"Unknown_{title[:20]}"

            return {
                "paper_id": paper_id,
                "title": title,
                "DOI": "",  # Google Scholar doesn't expose DOIs directly
                "Full_Citation_APA7": "",
                "Authors": authors,
                "Year": year,
                "Journal": journal,
                "Journal_Tier": "",
                "Paper_Type": "Journal Article",
                "Citation_Count": cite_count,
                "Search_Query_Source": "",
                "Date_Extracted": datetime.now().strftime("%Y-%m-%d"),
                "Extracted_By": "API Discovery - Google Scholar",
                "abstract": snippet,
                "is_oa": "Yes" if pdf_url else "No",
                "oa_url": pdf_url,
                "_scholar_url": url,
            }

        except Exception as e:
            console.print(f"  [dim]Parse error: {e}[/]")
            return None


# ─── DISPLAY ────────────────────────────────────────────────

def show_results(papers: list[dict]):
    """Display scraped results in a Rich table."""
    table = Table(
        title="Google Scholar Results",
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold magenta",
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#", width=4, justify="right")
    table.add_column("Title", max_width=50, overflow="fold")
    table.add_column("Authors", max_width=25, overflow="fold")
    table.add_column("Year", width=6, justify="center")
    table.add_column("Cites", width=6, justify="right")
    table.add_column("PDF", width=4, justify="center")

    for i, p in enumerate(papers, 1):
        authors = p.get("Authors", "")
        if len(authors) > 30:
            authors = authors[:30] + "..."
        pdf = "Y" if p.get("oa_url") else ""

        table.add_row(
            str(i),
            p.get("title", "")[:80],
            authors,
            p.get("Year", ""),
            p.get("Citation_Count", "0"),
            pdf,
        )

    console.print(table)


# ─── CLI ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Google Scholar Scraper")
    parser.add_argument("--query", "-q", required=True, help="Search query")
    parser.add_argument("--max-results", "-n", type=int, default=10, help="Max results")
    parser.add_argument("--year-from", type=int, help="Year from filter")
    parser.add_argument("--year-to", type=int, help="Year to filter")
    parser.add_argument("--headless", action="store_true", help="Run headless (no CAPTCHA support)")
    args = parser.parse_args()

    console.print(f"[bold magenta]Google Scholar Search[/]")
    console.print(f"  Query: {args.query}")
    console.print(f"  Max results: {args.max_results}")
    if args.headless:
        console.print(f"  [yellow]Headless mode — CAPTCHA solving disabled[/]")
    console.print()

    with GoogleScholarScraper(headless=args.headless) as scraper:
        papers = scraper.search(
            query=args.query,
            max_results=args.max_results,
            year_from=args.year_from,
            year_to=args.year_to,
        )

    if papers:
        show_results(papers)
        console.print(f"\n[bold green]Found {len(papers)} papers[/]")
    else:
        console.print("[yellow]No results found[/]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
