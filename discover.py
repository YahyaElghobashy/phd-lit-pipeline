#!/usr/bin/env python3
"""
PhD Literature Discovery Pipeline — CLI Entry Point
=====================================================
Discovers new papers relevant to PhD research gaps via academic APIs,
downloads open-access PDFs, extracts structured data, and validates
gap novelty.

Usage:
    python discover.py --query "your research topic keywords" --dry-run
    python discover.py --query "women directors financial performance" --max-results 20
    python discover.py --query "your research domain specific terms" --year-range 2015 2026 --min-citations 10
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from api_clients import OpenAlexClient, CrossRefClient, UnpaywallClient
from discovery_config import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_YEAR_RANGE,
    DEFAULT_MIN_CITATIONS,
    AUTO_SPREADSHEET_ID,
)

console = Console()


# ─── TERMINAL UI ─────────────────────────────────────────────

def show_discovery_header(query: str, dry_run: bool, max_results: int, year_range: tuple, min_citations: int):
    """Display discovery pipeline header banner."""
    content = Text()
    content.append("PhD LITERATURE DISCOVERY PIPELINE\n", style="bold magenta")
    content.append("Automated Gap Validation & Research Discovery\n\n", style="dim")
    content.append(f"🔍 Query: {query}\n")
    content.append(f"📊 Max results: {max_results}\n")
    content.append(f"📅 Year range: {year_range[0]}–{year_range[1]}\n")
    content.append(f"📈 Min citations: {min_citations}\n")
    if dry_run:
        content.append("\n⚠️  DRY RUN — no downloads or sheet writes\n", style="yellow bold")

    console.print(Panel(content, border_style="magenta", box=box.DOUBLE))
    console.print()


def show_results_table(papers: list[dict], title: str = "Search Results"):
    """Display papers in a Rich table."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold magenta",
        header_style="bold cyan",
        expand=True,
    )

    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title", max_width=50, overflow="fold")
    table.add_column("Authors", max_width=25, overflow="fold")
    table.add_column("Year", width=6, justify="center")
    table.add_column("Journal", max_width=25, overflow="fold")
    table.add_column("Cites", width=6, justify="right")
    table.add_column("OA", width=4, justify="center")
    table.add_column("DOI", max_width=20, overflow="fold")

    for i, p in enumerate(papers, 1):
        # Truncate authors to first author + et al.
        authors = p.get("Authors", "")
        if "; " in authors:
            first = authors.split("; ")[0]
            authors = f"{first} et al."

        oa = "✅" if p.get("is_oa") == "Yes" else "❌"

        table.add_row(
            str(i),
            p.get("title", "")[:80],
            authors[:40],
            p.get("Year", ""),
            p.get("Journal", "")[:35],
            p.get("Citation_Count", "0"),
            oa,
            p.get("DOI", "")[:25],
        )

    console.print(table)
    console.print()


def show_summary(papers: list[dict], duration: float):
    """Show search summary statistics."""
    total = len(papers)
    oa_count = sum(1 for p in papers if p.get("is_oa") == "Yes")
    with_doi = sum(1 for p in papers if p.get("DOI"))
    with_abstract = sum(1 for p in papers if p.get("abstract"))

    avg_citations = 0
    if total > 0:
        citations = [int(p.get("Citation_Count", 0) or 0) for p in papers]
        avg_citations = sum(citations) / total

    content = Text()
    content.append("SEARCH SUMMARY\n\n", style="bold green")
    content.append(f"📄 Papers found: {total}\n")
    content.append(f"🔓 Open access: {oa_count}/{total}\n")
    content.append(f"🔗 With DOI: {with_doi}/{total}\n")
    content.append(f"📝 With abstract: {with_abstract}/{total}\n")
    content.append(f"📊 Avg citations: {avg_citations:.1f}\n")
    content.append(f"⏱️  Duration: {duration:.1f}s\n")

    console.print(Panel(content, border_style="green", box=box.ROUNDED))


# ─── CLI COMMANDS ────────────────────────────────────────────

def cmd_search(args):
    """Execute a search query against OpenAlex."""
    query = args.query
    max_results = args.max_results
    year_range = (args.year_range[0], args.year_range[1]) if args.year_range else DEFAULT_YEAR_RANGE
    min_citations = args.min_citations

    show_discovery_header(query, args.dry_run, max_results, year_range, min_citations)

    # Search OpenAlex
    client = OpenAlexClient()
    console.print("[bold blue]Searching OpenAlex...[/]")
    start = time.time()

    try:
        papers = client.search(
            query=query,
            max_results=max_results,
            year_from=year_range[0],
            year_to=year_range[1],
            min_citations=min_citations,
        )
    except Exception as e:
        console.print(f"[bold red]OpenAlex search failed: {e}[/]")
        return 1

    duration = time.time() - start
    console.print(f"[green]Found {len(papers)} papers in {duration:.1f}s[/]\n")

    if not papers:
        console.print("[yellow]No results found. Try a broader query.[/]")
        return 0

    # Show results
    show_results_table(papers)

    # Check Unpaywall for OA URLs (enrich existing OA data)
    if not args.dry_run and papers:
        unpaywall = UnpaywallClient()
        oa_enriched = 0
        papers_with_doi = [p for p in papers if p.get("DOI")]

        if papers_with_doi:
            console.print(f"[bold blue]Checking Unpaywall for {len(papers_with_doi)} papers with DOIs...[/]")
            for p in papers_with_doi:
                try:
                    pdf_url = unpaywall.get_oa_url(p["DOI"])
                    if pdf_url:
                        p["oa_url"] = pdf_url
                        if p.get("is_oa") != "Yes":
                            p["is_oa"] = "Yes"
                            oa_enriched += 1
                except Exception:
                    pass  # Non-critical, skip silently

            if oa_enriched > 0:
                console.print(f"[green]Unpaywall found {oa_enriched} additional OA papers[/]\n")

    # Summary
    show_summary(papers, time.time() - start)

    return 0


# ─── MAIN ────────────────────────────────────────────────────

def cmd_setup_sheet(args):
    """Create the Automated Extraction Google Sheet."""
    from sheet_setup import create_auto_sheet, verify_auto_sheet
    sheet_id = create_auto_sheet(dry_run=args.dry_run)
    if sheet_id and not args.dry_run:
        verify_auto_sheet(sheet_id)
    return 0


def cmd_dedup_test(args):
    """Test deduplication against a query's results."""
    from deduplicator import Deduplicator

    if not args.query:
        console.print("[red]--query is required for dedup test[/]")
        return 1

    query = args.query
    max_results = args.max_results

    console.print(f"[bold blue]Searching OpenAlex for: {query}[/]")
    client = OpenAlexClient()
    papers = client.search(query=query, max_results=max_results)
    console.print(f"[green]Found {len(papers)} papers[/]\n")

    console.print("[bold blue]Running deduplication...[/]")
    dedup = Deduplicator(auto_sheet_id=AUTO_SPREADSHEET_ID)
    dedup.load_existing()

    new_papers, duplicates = dedup.filter_new(papers)

    console.print(f"\n[bold green]New papers: {len(new_papers)}[/]")
    console.print(f"[bold yellow]Duplicates filtered: {len(duplicates)}[/]")

    if duplicates:
        console.print("\n[bold yellow]Duplicate details:[/]")
        for p in duplicates[:10]:  # Show first 10
            console.print(f"  ❌ {p.get('title', '')[:60]}...")
            console.print(f"     Reason: {p.get('dup_reason', 'unknown')}", style="dim")

    if new_papers:
        console.print(f"\n[bold green]New papers preview (first 5):[/]")
        show_results_table(new_papers[:5], title="New (Non-Duplicate) Papers")

    return 0


def cmd_build_queries(args):
    """Generate search queries from research gaps."""
    from gap_query_builder import GapQueryBuilder, GapReader, show_query_results

    reader = GapReader()
    gaps = reader.get_unresolved_gaps()

    if args.dry_run:
        console.print(f"[bold green]{len(gaps)} unresolved gaps found:[/]\n")
        for g in gaps[:20]:
            console.print(f"  {g['gap_id']} [{g['gap_type']}] {g['gap_statement'][:80]}...")
        if len(gaps) > 20:
            console.print(f"\n  [dim]... and {len(gaps) - 20} more[/]")
        console.print(f"\n[dim]Would generate ~{len(gaps) * 3} queries[/]")
        return 0

    limit = args.max_results  # reuse max-results as gap limit
    if limit and limit < len(gaps):
        gaps = gaps[:limit]

    builder = GapQueryBuilder()
    results = builder.build_queries(gaps)
    show_query_results(results)
    return 0


def cmd_run(args):
    """
    Full discovery pipeline: gaps → queries → search → dedup → download → extract → novelty.

    Steps:
    1. Read unresolved gaps from GAP_TRACKER
    2. Convert gaps to search queries (Claude Sonnet)
    3. Search OpenAlex for each query
    4. Deduplicate against both sheets
    5. Download PDFs to Automated Extraction folder
    6. Full 12-section extraction (Claude Opus 4.6)
    7. Gap novelty assessment (Claude Opus 4.6)
    """
    from gap_query_builder import GapQueryBuilder, GapReader
    from deduplicator import Deduplicator
    from pdf_downloader import PDFDownloader
    from discovery_state import DiscoveryState
    from discovery_config import PDF_DOWNLOAD_DIR
    from discovery_report import DiscoveryRunReport

    state = DiscoveryState()
    state.register_shutdown_handler()

    # Initialize run report
    report = DiscoveryRunReport(args={
        "dry_run": args.dry_run,
        "gap_limit": getattr(args, "gap_limit", 0),
        "max_results": args.max_results,
        "min_citations": args.min_citations,
        "year_range": list(args.year_range) if args.year_range else list(DEFAULT_YEAR_RANGE),
        "skip_extraction": getattr(args, "skip_extraction", False),
        "skip_novelty": getattr(args, "skip_novelty", False),
    })

    year_range = (args.year_range[0], args.year_range[1]) if args.year_range else DEFAULT_YEAR_RANGE
    gap_limit = args.gap_limit if hasattr(args, 'gap_limit') and args.gap_limit else 0

    # ─── Header ──────────────────────────────────────────────
    content = Text()
    content.append("PhD LITERATURE DISCOVERY PIPELINE\n", style="bold magenta")
    content.append("Automated Gap Validation & Research Discovery\n\n", style="dim")
    content.append(f"📅 Year range: {year_range[0]}–{year_range[1]}\n")
    content.append(f"📊 Max results per query: {args.max_results}\n")
    content.append(f"📈 Min citations: {args.min_citations}\n")
    content.append(f"📁 Download dir: {PDF_DOWNLOAD_DIR}\n")
    if args.dry_run:
        content.append("\n⚠️  DRY RUN — search only, no downloads\n", style="yellow bold")
    if gap_limit:
        content.append(f"🔢 Gap limit: {gap_limit}\n")
    # Show resume info
    if state.data["gaps_processed"]:
        content.append(f"\n🔄 Resuming: {len(state.data['gaps_processed'])} gaps already processed\n", style="cyan")
    console.print(Panel(content, border_style="magenta", box=box.DOUBLE))
    console.print()

    run_start = time.time()

    # ─── Step 1: Read gaps ───────────────────────────────────
    report.start_step("1_read_gaps")
    console.rule("[bold cyan]Step 1: Reading Gaps", style="cyan")
    reader = GapReader()
    all_gaps = reader.get_unresolved_gaps()
    console.print(f"  Found {len(all_gaps)} unresolved gaps\n")

    if gap_limit:
        all_gaps = all_gaps[:gap_limit]
        console.print(f"  [dim]Limited to first {gap_limit} gaps[/]\n")

    # Filter out already-processed gaps (resume support)
    gaps_to_process = [g for g in all_gaps if not state.is_gap_processed(g["gap_id"])]
    if len(gaps_to_process) < len(all_gaps):
        console.print(f"  [dim]Skipping {len(all_gaps) - len(gaps_to_process)} already-processed gaps[/]\n")

    if not gaps_to_process:
        console.print("[green]All gaps already processed! Use --reset to start fresh.[/]")
        return 0

    report.record_gaps(gaps_to_process)
    report.end_step("1_read_gaps")

    # ─── Step 2: Generate queries ────────────────────────────
    report.start_step("2_generate_queries")
    console.rule("[bold cyan]Step 2: Generating Search Queries", style="cyan")
    builder = GapQueryBuilder()
    query_results = builder.build_queries(gaps_to_process)

    total_queries = sum(len(r.get("queries", [])) for r in query_results)
    console.print(f"\n  Generated {total_queries} queries for {len(query_results)} gaps\n")
    report.record_queries(query_results)
    report.end_step("2_generate_queries")

    # ─── Step 3: Multi-Source Search ───────────────────────────
    report.start_step("3_search_openalex")
    sources = [s.strip() for s in args.sources.split(",")]
    console.rule(f"[bold cyan]Step 3: Searching ({', '.join(sources)})", style="cyan")

    # Initialize search clients
    search_clients = {}
    if "openalex" in sources:
        search_clients["openalex"] = OpenAlexClient()
    if "semantic_scholar" in sources:
        from api_clients import SemanticScholarClient
        search_clients["semantic_scholar"] = SemanticScholarClient()
    if "core" in sources:
        from api_clients import COREClient
        search_clients["core"] = COREClient()

    # Concept IDs for OpenAlex filtering
    concept_ids = None
    if "openalex" in sources and not getattr(args, 'no_concept_filter', False):
        from discovery_config import OPENALEX_CONCEPT_IDS
        concept_ids = OPENALEX_CONCEPT_IDS
        console.print(f"  [dim]OpenAlex concept filter: {concept_ids}[/]")

    all_papers = []  # All raw results
    seen_dois = set()  # Track DOIs to avoid cross-query duplicates
    seen_titles = set()  # Also track titles for papers without DOIs

    def _add_paper(p, gap_id, query_str):
        """Add paper to results if not a duplicate."""
        p["Search_Query_Source"] = query_str
        p["_gap_id"] = gap_id
        doi = p.get("DOI", "")
        title_key = p.get("title", "").strip().lower()[:80]
        if doi and doi not in seen_dois:
            seen_dois.add(doi)
            if title_key:
                seen_titles.add(title_key)
            all_papers.append(p)
        elif not doi and title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            all_papers.append(p)

    for gap_result in query_results:
        gap_id = gap_result.get("gap_id", "?")
        queries = gap_result.get("queries", [])
        console.print(f"\n  [bold]{gap_id}[/] — {len(queries)} queries")

        for q in queries:
            query_str = q.get("query", "")
            angle = q.get("angle", "")

            # Skip already-searched queries (resume support)
            if state.is_query_searched(query_str):
                console.print(f"    [dim]Skipping (already searched): {query_str}[/]")
                continue

            # Search each enabled source
            for source_name, client in search_clients.items():
                try:
                    if source_name == "openalex":
                        papers = client.search(
                            query=query_str,
                            max_results=args.max_results,
                            year_from=year_range[0],
                            year_to=year_range[1],
                            min_citations=args.min_citations,
                            concept_ids=concept_ids,
                        )
                    elif source_name == "semantic_scholar":
                        papers = client.search(
                            query=query_str,
                            max_results=min(args.max_results, 50),
                            year_from=year_range[0],
                            year_to=year_range[1],
                            min_citations=args.min_citations,
                        )
                    elif source_name == "core":
                        papers = client.search(
                            query=query_str,
                            max_results=min(args.max_results, 20),
                        )
                    else:
                        papers = []

                    console.print(f"    [{angle}] \"{query_str}\" ({source_name}) → {len(papers)} results")

                    for p in papers:
                        _add_paper(p, gap_id, query_str)

                except Exception as e:
                    console.print(f"    [red]{source_name} failed: {e}[/]")

            state.mark_query_searched(query_str)

        state.mark_gap_processed(gap_id)

    # Google Scholar (if enabled) — handled separately due to browser lifecycle
    if "scholar" in sources:
        console.print(f"\n  [bold blue]Google Scholar search...[/]")
        try:
            from google_scholar_scraper import GoogleScholarScraper
            with GoogleScholarScraper(headless=False) as scraper:
                for gap_result in query_results:
                    gap_id = gap_result.get("gap_id", "?")
                    queries = gap_result.get("queries", [])
                    for q in queries[:1]:  # Only first query per gap (Scholar is rate-sensitive)
                        query_str = q.get("query", "")
                        try:
                            papers = scraper.search(
                                query=query_str,
                                max_results=min(args.max_results, 10),
                                year_from=year_range[0],
                                year_to=year_range[1],
                            )
                            console.print(f"    [scholar] \"{query_str}\" → {len(papers)} results")
                            for p in papers:
                                _add_paper(p, gap_id, query_str)
                        except Exception as e:
                            console.print(f"    [red]Scholar failed: {e}[/]")
        except ImportError:
            console.print("  [yellow]Google Scholar scraper not available (install playwright)[/]")

    console.print(f"\n  [bold green]Total unique papers found: {len(all_papers)}[/]\n")
    state.update_stats(total_gaps=len(gaps_to_process), total_queries=total_queries, total_results=len(all_papers))
    report.record_search(all_papers)
    report.end_step("3_search_openalex")

    if not all_papers:
        console.print("[yellow]No papers found. Try broader queries.[/]")
        report_path = report.save()
        console.print(f"  [dim]Report: {report_path}[/]")
        return 0

    # ─── Step 3b: Relevance Screening ──────────────────────────
    skip_screening = hasattr(args, 'skip_screening') and args.skip_screening
    if not skip_screening and all_papers:
        console.rule("[bold cyan]Step 3b: Relevance Screening", style="cyan")
        try:
            from relevance_screener import screen_batch
            threshold = getattr(args, 'relevance_threshold', 0.5)
            console.print(f"  [dim]Threshold: {threshold}[/]")

            relevant_papers, filtered_papers = screen_batch(all_papers, threshold=threshold)
            console.print(f"  Relevant: [bold green]{len(relevant_papers)}[/]")
            console.print(f"  Filtered out: [yellow]{len(filtered_papers)}[/]")

            if filtered_papers:
                console.print("\n  [dim]Sample filtered:[/]")
                for p in filtered_papers[:5]:
                    score = p.get('_relevance_score', 0)
                    console.print(f"    [{score:.2f}] {p.get('title', '')[:60]}")

            all_papers = relevant_papers
        except Exception as e:
            console.print(f"  [yellow]Screening failed ({e}) — passing all papers through[/]")
    elif skip_screening:
        console.print("\n[dim]Relevance screening skipped (--skip-screening)[/]")

    # ─── Step 4: Deduplicate ─────────────────────────────────
    report.start_step("4_dedup")
    console.rule("[bold cyan]Step 4: Deduplication", style="cyan")
    dedup = Deduplicator(auto_sheet_id=AUTO_SPREADSHEET_ID)
    dedup.load_existing()

    new_papers, duplicates = dedup.filter_new(all_papers)
    console.print(f"  New papers: [bold green]{len(new_papers)}[/]")
    console.print(f"  Duplicates filtered: [yellow]{len(duplicates)}[/]")
    state.update_stats(unique_new=len(new_papers))
    report.record_dedup(new_papers, len(duplicates))
    report.end_step("4_dedup")

    if duplicates:
        console.print("\n  [dim]Sample duplicates:[/]")
        for p in duplicates[:5]:
            console.print(f"    ❌ {p.get('title', '')[:50]}... — {p.get('dup_reason', '')[:50]}")

    if not new_papers:
        console.print("\n[yellow]All papers are duplicates. No new papers to download.[/]")
        _show_run_summary(state, time.time() - run_start)
        return 0

    # ─── Step 5: Show new papers ─────────────────────────────
    show_results_table(new_papers[:20], title=f"New Papers to Process ({len(new_papers)} total)")

    if args.dry_run:
        console.print("[yellow]DRY RUN complete — no downloads performed.[/]")
        _show_run_summary(state, time.time() - run_start)
        report_path = report.save()
        console.print(f"  [dim]Report: {report_path}[/]")
        return 0

    # ─── Step 6: Download PDFs ───────────────────────────────
    report.start_step("5_download")
    console.rule("[bold cyan]Step 5: Downloading PDFs & Checking Unpaywall", style="cyan")
    downloader = PDFDownloader()

    # Filter to papers with DOIs (cascading PDF chain can find most via DOI)
    # or papers that already have OA URLs
    downloadable = [p for p in new_papers if p.get("is_oa") == "Yes" or p.get("DOI")]
    console.print(f"  Papers with DOI or OA URL: {len(downloadable)}")
    console.print(f"  Papers without DOI/OA: {len(new_papers) - len(downloadable)}\n")

    use_scihub = not getattr(args, 'no_scihub', False)
    dl_results = downloader.download_batch(downloadable, use_scihub=use_scihub)

    # Track results in state
    for paper, path in dl_results["downloaded"]:
        state.mark_downloaded(paper["paper_id"], str(path))
    state.update_stats(
        downloaded=state.data["run_stats"]["downloaded"] + len(dl_results["downloaded"]),
        no_pdf=state.data["run_stats"]["no_pdf"] + len(dl_results["no_pdf"]),
    )

    # Record downloads in report
    for paper, path in dl_results["downloaded"]:
        report.record_download(paper.get("paper_id", ""), paper.get("title", ""), "downloaded", str(path))
    for paper in dl_results["no_pdf"]:
        report.record_download(paper.get("paper_id", ""), paper.get("title", ""), "no_pdf")
    report.end_step("5_download")

    # Save metadata for papers without DOI
    for p in new_papers:
        if not p.get("DOI") and p.get("is_oa") != "Yes":
            downloader.save_metadata_json(p)

    # ─── Step 7: Extract PDFs ────────────────────────────────
    skip_extraction = hasattr(args, 'skip_extraction') and args.skip_extraction
    if dl_results["downloaded"] and not skip_extraction:
        report.start_step("6_extraction")
        console.rule("[bold cyan]Step 6: Full 12-Section Extraction", style="cyan")
        from discovery_extractor import DiscoveryExtractor, show_extraction_summary

        extractor = DiscoveryExtractor(auto_sheet_id=AUTO_SPREADSHEET_ID)

        # Only extract papers not already extracted (resume support)
        to_extract = []
        for paper, pdf_path in dl_results["downloaded"]:
            pid = paper.get("paper_id", "unknown")
            if not state.is_extracted(pid):
                to_extract.append((paper, pdf_path))
            else:
                console.print(f"  [dim]Skipping (already extracted): {pid}[/]")

        if to_extract:
            console.print(f"  Papers to extract: {len(to_extract)}\n")
            ext_results = extractor.extract_batch(to_extract)

            # Track in state
            for ext in ext_results["extractions"]:
                pid = ext.get("paper_id", "")
                json_path = ext.get("_extraction_file", "")
                if pid:
                    state.mark_extracted(pid, json_path)

            # Record in report
            for ext in ext_results["extractions"]:
                pid = ext.get("paper_id", "")
                rel = ext.get("9_RELEVANCE", {})
                report.record_extraction(
                    pid, "extracted",
                    relevance_tier=rel.get("Relevance_Tier", ""),
                    relevance_score=str(rel.get("Weighted_Score", "")),
                )
            for _ in range(ext_results["failed"]):
                report.record_extraction("unknown", "failed")

            show_extraction_summary(ext_results)
            report.end_step("6_extraction")
        else:
            console.print("  [dim]All downloaded papers already extracted[/]")
    elif skip_extraction:
        console.print("\n[yellow]Extraction skipped (--skip-extraction flag)[/]")

    # ─── Step 8: Gap Matrix Analysis ─────────────────────────
    skip_novelty = hasattr(args, 'skip_novelty') and args.skip_novelty
    if not skip_novelty and not args.dry_run:
        report.start_step("7_novelty")
        console.rule("[bold cyan]Step 7: Gap Matrix Analysis", style="cyan")
        from gap_matrix_analyzer import GapMatrixAnalyzer
        from discovery_config import DISCOVERIES_DIR

        matrix_analyzer = GapMatrixAnalyzer()
        matrix_totals = matrix_analyzer.analyze_all_missing(extraction_dir=DISCOVERIES_DIR)

        if matrix_totals["assessments"]:
            # Group assessments by paper for report
            by_paper: dict[str, list] = {}
            for a in matrix_totals["assessments"]:
                pid = a.get("gap_id", "unknown")  # Assessments are per-gap
                by_paper.setdefault(pid, []).append(a)
            for pid, assessments in by_paper.items():
                report.record_novelty(pid, assessments)

        console.print(
            f"  [bold green]Matrix: {matrix_totals['written']} evidence rows, "
            f"{matrix_totals['papers_processed']} papers analyzed[/]\n"
        )
        report.end_step("7_novelty")
    elif skip_novelty:
        console.print("\n[yellow]Gap matrix analysis skipped (--skip-novelty flag)[/]")

    # ─── Summary & Report ────────────────────────────────────
    _show_run_summary(state, time.time() - run_start)

    report_path = report.save()
    console.print(f"  [bold cyan]📋 Run report saved: {report_path.name}[/]")
    console.print(f"  [dim]{report_path}[/]\n")

    return 0


def cmd_status(args):
    """Show comprehensive pipeline status."""
    from discovery_report import show_pipeline_status
    show_pipeline_status()
    return 0


def cmd_report(args):
    """Show a specific run report or list all reports."""
    from discovery_report import list_reports, show_report_detail

    reports = list_reports()
    if not reports:
        console.print("[yellow]No discovery run reports found.[/]")
        return 0

    # If --report with no specific file, show the latest
    report_path = reports[0]  # newest first
    show_report_detail(report_path)
    return 0


def cmd_novelty(args):
    """Run gap matrix analysis on all discovery extractions."""
    from gap_matrix_analyzer import GapMatrixAnalyzer
    from discovery_config import DISCOVERIES_DIR

    console.print("[bold magenta]Gap Matrix Analysis[/]\n")
    analyzer = GapMatrixAnalyzer()

    if args.dry_run:
        analyzer.dry_run(extraction_dir=DISCOVERIES_DIR)
        return 0

    totals = analyzer.analyze_all_missing(extraction_dir=DISCOVERIES_DIR)

    if totals.get("assessments"):
        # Show top impacts
        non_zero = [a for a in totals["assessments"] if a.get("pct_eliminated", 0) > 0]
        if non_zero:
            console.print(f"\n  [bold]Top gap impacts ({len(non_zero)} non-zero):[/]")
            top = sorted(non_zero, key=lambda a: a.get("pct_eliminated", 0), reverse=True)[:10]
            for a in top:
                console.print(
                    f"    {a['gap_id']}: [cyan]{a.get('pct_eliminated', 0)}%[/] — "
                    f"{a.get('aspect_addressed', '')[:60]}"
                )

    console.print(
        f"\n[bold green]Done: {totals['written']} evidence rows, "
        f"{totals['papers_processed']} papers analyzed[/]"
    )

    # Show matrix status
    analyzer.show_matrix_status()
    return 0


def _show_run_summary(state, duration: float):
    """Show end-of-run summary."""
    from discovery_state import DiscoveryState
    stats = state.data["run_stats"]

    content = Text()
    content.append("DISCOVERY RUN SUMMARY\n\n", style="bold green")
    content.append(f"🔬 Gaps processed: {stats['total_gaps']}\n")
    content.append(f"🔍 Queries executed: {stats['total_queries']}\n")
    content.append(f"📄 Total results: {stats['total_results']}\n")
    content.append(f"✨ Unique new papers: {stats['unique_new']}\n")
    content.append(f"📥 PDFs downloaded: {stats['downloaded']}\n")
    content.append(f"📋 Metadata-only: {stats['no_pdf']}\n")
    content.append(f"⏱️  Duration: {duration:.1f}s\n")

    console.print()
    console.print(Panel(content, border_style="green", box=box.ROUNDED))


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="PhD Literature Discovery Pipeline — Find papers relevant to research gaps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python discover.py --run --gap-limit 3 --dry-run          # Full pipeline dry-run (3 gaps)
  python discover.py --run --gap-limit 5 --min-citations 10  # Run for 5 gaps, min 10 citations
  python discover.py --query "your research topic" --dry-run  # Ad-hoc search
  python discover.py --setup-sheet                            # Create auto extraction sheet
  python discover.py --build-queries --dry-run                # Preview gap queries
  python discover.py --dedup --query "your research topic" # Test dedup
  python discover.py --novelty                                # Run novelty assessment
  python discover.py --status                                 # Pipeline status dashboard
  python discover.py --report                                 # View latest run report
  python discover.py --reset                                  # Clear state, start fresh
        """,
    )

    # Mode flags
    parser.add_argument(
        "--run",
        action="store_true",
        help="Full pipeline: gaps → queries → search → dedup → download",
    )
    parser.add_argument(
        "--setup-sheet",
        action="store_true",
        help="Create the Automated Extraction Google Sheet",
    )
    parser.add_argument(
        "--dedup",
        action="store_true",
        help="Test deduplication: search + filter against existing sheets",
    )
    parser.add_argument(
        "--build-queries",
        action="store_true",
        help="Convert research gaps to search queries via Claude Sonnet",
    )
    parser.add_argument(
        "--gap-limit",
        type=int,
        default=0,
        help="Limit number of gaps to process (default: all)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset discovery state (start fresh)",
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip Claude Opus 4.6 extraction (download only)",
    )
    parser.add_argument(
        "--skip-novelty",
        action="store_true",
        help="Skip gap novelty assessment",
    )
    parser.add_argument(
        "--novelty",
        action="store_true",
        help="Run gap novelty assessment on all discoveries (standalone)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show pipeline status: state, files, extractions, novelty coverage",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Show the latest run report (or list all reports)",
    )

    # Search params
    parser.add_argument(
        "--query", "-q",
        type=str,
        default="",
        help="Search query string",
    )
    parser.add_argument(
        "--max-results", "-n",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=f"Maximum results per query (default: {DEFAULT_MAX_RESULTS})",
    )
    parser.add_argument(
        "--year-range", "-y",
        type=int,
        nargs=2,
        metavar=("FROM", "TO"),
        default=list(DEFAULT_YEAR_RANGE),
        help=f"Publication year range (default: {DEFAULT_YEAR_RANGE[0]} {DEFAULT_YEAR_RANGE[1]})",
    )
    parser.add_argument(
        "--min-citations", "-c",
        type=int,
        default=DEFAULT_MIN_CITATIONS,
        help=f"Minimum citation count (default: {DEFAULT_MIN_CITATIONS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only — no downloads, no sheet writes, no sheet creation",
    )

    # Multi-source options
    parser.add_argument(
        "--sources",
        type=str,
        default="openalex,semantic_scholar",
        help="Comma-separated search sources: openalex,semantic_scholar,core,scholar (default: openalex,semantic_scholar)",
    )
    parser.add_argument(
        "--no-concept-filter",
        action="store_true",
        help="Disable OpenAlex concept filtering (configured research domain concepts)",
    )
    parser.add_argument(
        "--no-scihub",
        action="store_true",
        help="Disable Sci-Hub in the PDF acquisition chain",
    )
    parser.add_argument(
        "--skip-screening",
        action="store_true",
        help="Skip abstract-based relevance screening",
    )
    parser.add_argument(
        "--relevance-threshold",
        type=float,
        default=0.5,
        help="Relevance screening threshold (default: 0.5)",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.reset:
            from discovery_state import DiscoveryState
            DiscoveryState().reset()
            console.print("[green]Discovery state reset.[/]")
            exit_code = 0
        elif args.run:
            exit_code = cmd_run(args)
        elif args.status:
            exit_code = cmd_status(args)
        elif args.report:
            exit_code = cmd_report(args)
        elif args.novelty:
            exit_code = cmd_novelty(args)
        elif args.setup_sheet:
            exit_code = cmd_setup_sheet(args)
        elif args.build_queries:
            exit_code = cmd_build_queries(args)
        elif args.dedup:
            exit_code = cmd_dedup_test(args)
        elif args.query:
            exit_code = cmd_search(args)
        else:
            parser.print_help()
            exit_code = 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/]")
        exit_code = 130

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
