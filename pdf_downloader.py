"""
PhD Literature Discovery Pipeline — PDF Downloader
=====================================================
Downloads open-access PDFs from Unpaywall/OpenAlex URLs.
Saves to Literature Review/Automated Extraction/ folder.
Generates metadata-only JSONs for papers without downloadable PDFs.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)

from discovery_config import (
    PDF_DOWNLOAD_DIR,
    DISCOVERIES_DIR,
    PDF_DOWNLOAD_DELAY,
    API_REQUEST_TIMEOUT,
    API_MAILTO,
)
from api_clients import UnpaywallClient, retry_on_api_error

console = Console()


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters not allowed in filenames."""
    # Replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name)
    name = name.strip('._')
    return name[:100]  # Limit length


def _generate_filename(paper: dict) -> str:
    """
    Generate PDF filename: FirstAuthor_Year_ShortKeyword.pdf

    Examples:
        Adams_2015_BoardDiversity.pdf
        Carter_2010_GenderEthnic.pdf
    """
    authors = paper.get("Authors", "")
    year = paper.get("Year", "")
    title = paper.get("title", "")

    # First author last name
    first_author = "Unknown"
    if authors:
        first = authors.split(";")[0].strip()
        parts = first.split()
        if parts:
            # Handle "Last, First" or "First Last"
            if "," in first:
                first_author = parts[0].rstrip(",")
            else:
                first_author = parts[-1]

    # Short keyword from title
    keyword = ""
    if title:
        skip_words = {
            "the", "a", "an", "of", "in", "for", "to", "and", "or", "is",
            "are", "on", "at", "by", "with", "from", "how", "does", "do",
        }
        words = re.sub(r'[^\w\s]', '', title).split()
        meaningful = [w for w in words if w.lower() not in skip_words and len(w) > 2]
        # Take first 2 meaningful words, CamelCase
        keyword = "".join(w.capitalize() for w in meaningful[:2])

    if not keyword:
        keyword = "Paper"

    filename = f"{_sanitize_filename(first_author)}_{year}_{_sanitize_filename(keyword)}.pdf"
    return filename


class PDFDownloader:
    """Downloads open-access PDFs and manages the download directory."""

    def __init__(self, download_dir: Path = PDF_DOWNLOAD_DIR):
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._unpaywall = UnpaywallClient()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": f"PhDDiscoveryPipeline/1.0 (mailto:{API_MAILTO})",
        })

    def download_paper(self, paper: dict) -> Optional[Path]:
        """
        Download a paper's PDF if available.

        Args:
            paper: Normalized paper dict with 'oa_url', 'DOI', 'is_oa' fields

        Returns:
            Path to downloaded PDF, or None if not available/failed
        """
        doi = paper.get("DOI", "")
        title = paper.get("title", "")[:60]

        # Step 1: Get PDF URL
        pdf_url = paper.get("oa_url", "")

        # Step 2: If no URL yet, try Unpaywall
        if not pdf_url and doi:
            try:
                pdf_url = self._unpaywall.get_oa_url(doi)
                if pdf_url:
                    paper["oa_url"] = pdf_url
                    paper["is_oa"] = "Yes"
            except Exception:
                pass

        if not pdf_url:
            console.print(f"    [dim]No OA PDF URL for: {title}...[/]")
            return None

        # Step 3: Generate filename and check if already downloaded
        filename = _generate_filename(paper)
        dest_path = self.download_dir / filename

        # Handle collision
        if dest_path.exists():
            console.print(f"    [dim]Already downloaded: {filename}[/]")
            return dest_path

        # Step 4: Download
        console.print(f"    [blue]Downloading: {filename}[/]")
        try:
            return self._download_file(pdf_url, dest_path)
        except Exception as e:
            console.print(f"    [red]Download failed: {e}[/]")
            # Clean up partial download
            if dest_path.exists():
                dest_path.unlink()
            return None

    @retry_on_api_error(max_retries=2, base_delay=3.0)
    def _download_file(self, url: str, dest_path: Path) -> Optional[Path]:
        """Download a file with progress display and validation."""
        resp = self._session.get(url, stream=True, timeout=60, allow_redirects=True)
        resp.raise_for_status()

        # Check content type — must be PDF
        content_type = resp.headers.get("Content-Type", "").lower()
        if "html" in content_type and "pdf" not in content_type:
            # Probably a landing page, not a PDF
            console.print(f"    [yellow]URL returned HTML, not PDF — skipping[/]")
            return None

        total_size = int(resp.headers.get("Content-Length", 0))

        with open(dest_path, "wb") as f:
            if total_size > 0:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[blue]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console,
                    transient=True,
                ) as progress:
                    task = progress.add_task("Downloading...", total=total_size)
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
            else:
                # No content-length; download without progress bar
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

        # Validate: check file is actually a PDF (starts with %PDF)
        with open(dest_path, "rb") as f:
            header = f.read(5)

        if header != b"%PDF-":
            console.print(f"    [yellow]Downloaded file is not a valid PDF — removing[/]")
            dest_path.unlink()
            return None

        size_mb = dest_path.stat().st_size / (1024 * 1024)
        console.print(f"    [green]✓ Saved ({size_mb:.1f} MB)[/]")
        return dest_path

    def save_metadata_json(self, paper: dict) -> Path:
        """
        Save a metadata-only JSON for papers without downloadable PDFs.
        Stored in discoveries/ directory.
        """
        DISCOVERIES_DIR.mkdir(parents=True, exist_ok=True)

        paper_id = paper.get("paper_id", "unknown")
        filename = _sanitize_filename(paper_id) + "_metadata.json"
        dest_path = DISCOVERIES_DIR / filename

        metadata = {
            "paper_id": paper_id,
            "source": "API Discovery - OpenAlex",
            "has_pdf": False,
            "metadata": {
                "title": paper.get("title", ""),
                "DOI": paper.get("DOI", ""),
                "Authors": paper.get("Authors", ""),
                "Year": paper.get("Year", ""),
                "Journal": paper.get("Journal", ""),
                "Paper_Type": paper.get("Paper_Type", ""),
                "Citation_Count": paper.get("Citation_Count", ""),
                "abstract": paper.get("abstract", ""),
                "is_oa": paper.get("is_oa", "No"),
                "oa_url": paper.get("oa_url", ""),
                "openalex_id": paper.get("openalex_id", ""),
                "Full_Citation_APA7": paper.get("Full_Citation_APA7", ""),
                "Search_Query_Source": paper.get("Search_Query_Source", ""),
                "Date_Extracted": paper.get("Date_Extracted", ""),
                "Extracted_By": paper.get("Extracted_By", ""),
            },
        }

        with open(dest_path, "w") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return dest_path

    def download_batch(
        self,
        papers: list[dict],
        on_progress: callable = None,
    ) -> dict:
        """
        Download PDFs for a batch of papers.

        Returns:
            {
                "downloaded": [(paper, path), ...],
                "no_pdf": [paper, ...],
                "failed": [paper, ...],
            }
        """
        results = {"downloaded": [], "no_pdf": [], "failed": []}

        for i, paper in enumerate(papers, 1):
            title = paper.get("title", "")[:50]
            console.print(f"\n  [{i}/{len(papers)}] {title}...")

            if on_progress:
                on_progress(i, len(papers), paper)

            pdf_path = self.download_paper(paper)

            if pdf_path:
                results["downloaded"].append((paper, pdf_path))
            else:
                # Save metadata JSON for papers without PDFs
                meta_path = self.save_metadata_json(paper)
                results["no_pdf"].append(paper)
                console.print(f"    [dim]Saved metadata: {meta_path.name}[/]")

            # Rate limit between downloads
            if i < len(papers):
                time.sleep(PDF_DOWNLOAD_DELAY)

        return results
