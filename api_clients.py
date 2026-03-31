"""
PhD Literature Discovery Pipeline — Academic API Clients
==========================================================
OpenAlex (primary search), CrossRef (enrichment), Unpaywall (OA PDF URLs).
All clients return normalized dicts. Rate limiting built in.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from functools import wraps
from typing import Optional

import requests

from discovery_config import (
    OPENALEX_BASE_URL,
    CROSSREF_BASE_URL,
    UNPAYWALL_BASE_URL,
    API_MAILTO,
    OPENALEX_RATE_LIMIT,
    CROSSREF_RATE_LIMIT,
    UNPAYWALL_RATE_LIMIT,
    API_REQUEST_TIMEOUT,
    API_MAX_RETRIES,
    API_RETRY_BASE_DELAY,
    OPENALEX_TYPE_MAP,
)


# ─── RETRY DECORATOR ────────────────────────────────────────

def retry_on_api_error(max_retries: int = API_MAX_RETRIES, base_delay: float = API_RETRY_BASE_DELAY):
    """Retry HTTP calls with exponential backoff on transient errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, ValueError) as e:
                    last_error = e
                    error_str = str(e).lower()
                    retryable = any(x in error_str for x in [
                        "429", "rate limit", "quota",
                        "500", "503", "service unavailable",
                        "timeout", "timed out",
                        "connection", "reset by peer",
                    ])
                    if not retryable and isinstance(e, requests.HTTPError):
                        raise
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                    else:
                        raise
            raise last_error
        return wrapper
    return decorator


# ─── HELPER: Reconstruct abstract from OpenAlex inverted index ─

def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """
    OpenAlex stores abstracts as {word: [position, ...]} inverted index.
    Reconstruct to plain text by reversing the mapping.
    """
    if not inverted_index:
        return ""

    # Build position → word mapping
    position_map: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            position_map[pos] = word

    if not position_map:
        return ""

    # Reconstruct in order
    max_pos = max(position_map.keys())
    words = [position_map.get(i, "") for i in range(max_pos + 1)]
    return " ".join(w for w in words if w)


def _normalize_doi(doi: str | None) -> str:
    """Strip URL prefix from DOI, return bare DOI or empty string."""
    if not doi:
        return ""
    doi = doi.strip()
    # Remove common prefixes
    for prefix in ["https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"]:
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def _extract_authors(authorships: list[dict]) -> str:
    """Extract semicolon-joined author names from OpenAlex authorships."""
    names = []
    for a in authorships:
        author = a.get("author", {})
        name = author.get("display_name", "")
        if name:
            names.append(name)
    return "; ".join(names)


def _build_apa_citation(paper: dict) -> str:
    """Build an approximate APA7 citation from OpenAlex metadata."""
    authors = _extract_authors(paper.get("authorships", []))
    year = paper.get("publication_year", "n.d.")
    title = paper.get("title", "Untitled")

    # Get journal
    journal = ""
    primary_loc = paper.get("primary_location", {}) or {}
    source = primary_loc.get("source", {}) or {}
    journal = source.get("display_name", "")

    doi = _normalize_doi(paper.get("doi"))

    # Shorten author list for citation
    author_list = authors.split("; ")
    if len(author_list) > 3:
        citation_authors = f"{author_list[0]} et al."
    elif len(author_list) == 0:
        citation_authors = "Unknown"
    else:
        citation_authors = "; ".join(author_list)

    parts = [f"{citation_authors} ({year}). {title}."]
    if journal:
        parts.append(f" *{journal}*.")
    if doi:
        parts.append(f" https://doi.org/{doi}")

    return "".join(parts)


def _normalize_paper(raw: dict) -> dict:
    """
    Convert an OpenAlex work record to our normalized paper dict.

    Returns a dict with keys matching 1_IDENTIFICATION columns + extras.
    """
    doi = _normalize_doi(raw.get("doi"))
    authors = _extract_authors(raw.get("authorships", []))
    year = raw.get("publication_year")
    title = raw.get("title", "")

    # Journal from primary_location
    primary_loc = raw.get("primary_location", {}) or {}
    source = primary_loc.get("source", {}) or {}
    journal = source.get("display_name", "")

    # Paper type
    raw_type = raw.get("type", "article")
    paper_type = OPENALEX_TYPE_MAP.get(raw_type, "Journal Article")

    # Citation count
    cited_by = raw.get("cited_by_count", 0)

    # Open access
    oa_info = raw.get("open_access", {}) or {}
    is_oa = "Yes" if oa_info.get("is_oa") else "No"
    oa_url = oa_info.get("oa_url", "")

    # Abstract
    abstract = _reconstruct_abstract(raw.get("abstract_inverted_index"))

    # Build paper ID: FirstAuthor_Year_Keyword
    first_author = ""
    if raw.get("authorships"):
        first_author_name = raw["authorships"][0].get("author", {}).get("display_name", "")
        # Take last name
        parts = first_author_name.split()
        first_author = parts[-1] if parts else "Unknown"

    # Short keyword from title
    keyword = ""
    if title:
        # Take first meaningful word (skip common starters)
        skip_words = {"the", "a", "an", "on", "of", "in", "for", "to", "and", "is", "are", "do", "does", "how", "what", "why", "when"}
        words = re.sub(r'[^\w\s]', '', title).split()
        for w in words:
            if w.lower() not in skip_words and len(w) > 2:
                keyword = w
                break
        if not keyword and words:
            keyword = words[0]

    paper_id = f"{first_author}_{year}_{keyword}" if first_author and year else f"Unknown_{title[:20]}"

    return {
        "paper_id": paper_id,
        "title": title,
        "DOI": doi,
        "Full_Citation_APA7": _build_apa_citation(raw),
        "Authors": authors,
        "Year": str(year) if year else "",
        "Journal": journal,
        "Journal_Tier": "",  # API doesn't have ABS rankings
        "Paper_Type": paper_type,
        "Citation_Count": str(cited_by),
        "Search_Query_Source": "",  # filled by caller
        "Date_Extracted": datetime.now().strftime("%Y-%m-%d"),
        "Extracted_By": "API Discovery - OpenAlex",
        "abstract": abstract,
        "is_oa": is_oa,
        "oa_url": oa_url,
        "openalex_id": raw.get("id", ""),
        "relevance_score": raw.get("relevance_score"),
    }


# ─── OPENALEX CLIENT ────────────────────────────────────────

class OpenAlexClient:
    """Search and retrieve papers from OpenAlex API."""

    def __init__(self, mailto: str = API_MAILTO):
        self.base_url = OPENALEX_BASE_URL
        self.mailto = mailto
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Ensure minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < OPENALEX_RATE_LIMIT:
            time.sleep(OPENALEX_RATE_LIMIT - elapsed)
        self._last_request_time = time.time()

    @retry_on_api_error()
    def search(
        self,
        query: str,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        min_citations: int = 0,
        paper_type: str = "article",
    ) -> list[dict]:
        """
        Search OpenAlex for works matching query.

        Args:
            query: Search string
            max_results: Maximum results to return (max 200 per page)
            year_from: Filter by publication year >= this
            year_to: Filter by publication year <= this
            min_citations: Minimum citation count
            paper_type: OpenAlex type filter (default: article)

        Returns:
            List of normalized paper dicts
        """
        self._rate_limit()

        # Build filters — use default.search in filter for better relevance ranking
        # (OpenAlex 'search' param mixes popularity; 'default.search' filter is pure relevance)
        filters = [f"default.search:{query}"]
        if paper_type:
            filters.append(f"type:{paper_type}")
        if year_from:
            filters.append(f"publication_year:>{year_from - 1}")
        if year_to:
            filters.append(f"publication_year:<{year_to + 1}")
        if min_citations > 0:
            filters.append(f"cited_by_count:>{min_citations - 1}")

        params = {
            "per_page": min(max_results, 200),
            "mailto": self.mailto,
            "sort": "relevance_score:desc",
        }
        if filters:
            params["filter"] = ",".join(filters)

        resp = requests.get(
            f"{self.base_url}/works",
            params=params,
            timeout=API_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        papers = []
        for raw in results:
            paper = _normalize_paper(raw)
            paper["Search_Query_Source"] = query
            papers.append(paper)

        return papers

    @retry_on_api_error()
    def get_by_doi(self, doi: str) -> dict | None:
        """Fetch a single work by DOI."""
        self._rate_limit()
        clean_doi = _normalize_doi(doi)
        if not clean_doi:
            return None

        resp = requests.get(
            f"{self.base_url}/works/https://doi.org/{clean_doi}",
            params={"mailto": self.mailto},
            timeout=API_REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _normalize_paper(resp.json())


# ─── CROSSREF CLIENT ────────────────────────────────────────

class CrossRefClient:
    """Enrich paper metadata from CrossRef."""

    def __init__(self):
        self.base_url = CROSSREF_BASE_URL
        self._last_request_time = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < CROSSREF_RATE_LIMIT:
            time.sleep(CROSSREF_RATE_LIMIT - elapsed)
        self._last_request_time = time.time()

    @retry_on_api_error()
    def enrich(self, doi: str) -> dict:
        """
        Fetch supplemental metadata from CrossRef for a DOI.

        Returns dict with any additional fields not in OpenAlex:
        - subject areas, ISSN, publisher, license info, reference count
        """
        self._rate_limit()
        clean_doi = _normalize_doi(doi)
        if not clean_doi:
            return {}

        resp = requests.get(
            f"{self.base_url}/works/{clean_doi}",
            timeout=API_REQUEST_TIMEOUT,
            headers={"User-Agent": f"PhDDiscoveryPipeline/1.0 (mailto:{API_MAILTO})"},
        )
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()

        msg = resp.json().get("message", {})
        return {
            "subjects": msg.get("subject", []),
            "publisher": msg.get("publisher", ""),
            "issn": msg.get("ISSN", []),
            "license": [l.get("URL", "") for l in msg.get("license", [])],
            "references_count": msg.get("references-count", 0),
        }

    @retry_on_api_error()
    def search(self, query: str, max_results: int = 20) -> list[dict]:
        """
        Search CrossRef as fallback. Returns simplified result list.
        """
        self._rate_limit()

        resp = requests.get(
            f"{self.base_url}/works",
            params={
                "query": query,
                "rows": min(max_results, 100),
            },
            timeout=API_REQUEST_TIMEOUT,
            headers={"User-Agent": f"PhDDiscoveryPipeline/1.0 (mailto:{API_MAILTO})"},
        )
        resp.raise_for_status()

        items = resp.json().get("message", {}).get("items", [])
        results = []
        for item in items:
            doi = _normalize_doi(item.get("DOI", ""))
            title = ""
            if item.get("title"):
                title = item["title"][0] if isinstance(item["title"], list) else item["title"]

            authors_raw = item.get("author", [])
            authors = "; ".join(
                f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
                for a in authors_raw
            )

            year = ""
            date_parts = item.get("published-print", {}).get("date-parts") or item.get("published-online", {}).get("date-parts")
            if date_parts and date_parts[0]:
                year = str(date_parts[0][0])

            results.append({
                "DOI": doi,
                "title": title,
                "Authors": authors,
                "Year": year,
                "Journal": item.get("container-title", [""])[0] if item.get("container-title") else "",
                "Citation_Count": str(item.get("is-referenced-by-count", 0)),
                "source": "CrossRef",
            })

        return results


# ─── UNPAYWALL CLIENT ───────────────────────────────────────

class UnpaywallClient:
    """Find open-access PDF URLs via Unpaywall."""

    def __init__(self, email: str = API_MAILTO):
        self.base_url = UNPAYWALL_BASE_URL
        self.email = email
        self._last_request_time = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < UNPAYWALL_RATE_LIMIT:
            time.sleep(UNPAYWALL_RATE_LIMIT - elapsed)
        self._last_request_time = time.time()

    @retry_on_api_error()
    def get_oa_url(self, doi: str) -> Optional[str]:
        """
        Get best open-access PDF URL for a DOI.

        Returns:
            PDF URL string, or None if no OA version found.
        """
        self._rate_limit()
        clean_doi = _normalize_doi(doi)
        if not clean_doi:
            return None

        resp = requests.get(
            f"{self.base_url}/{clean_doi}",
            params={"email": self.email},
            timeout=API_REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()

        data = resp.json()

        # Try best_oa_location first
        best = data.get("best_oa_location")
        if best:
            pdf_url = best.get("url_for_pdf") or best.get("url")
            if pdf_url:
                return pdf_url

        # Fall back to any OA location with PDF
        for loc in data.get("oa_locations", []):
            pdf_url = loc.get("url_for_pdf")
            if pdf_url:
                return pdf_url

        return None
