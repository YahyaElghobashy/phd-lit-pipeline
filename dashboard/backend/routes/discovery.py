"""Dashboard API — Discovery routes (OpenAlex search + gap-driven discovery)."""
from __future__ import annotations

import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/discover", tags=["discovery"])

# Add pipeline dir to path so we can import api_clients (stateless, safe)
PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))


# ── Request Models ────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    max_results: int = 20
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    min_citations: int = 0


class QueryGenRequest(BaseModel):
    gap_ids: list[str]
    force: bool = False  # If True, regenerate even if cached


class UpdateQueriesRequest(BaseModel):
    queries: list[str]


class GapSearchRequest(BaseModel):
    queries: dict[str, list[str]]  # gap_id -> [query strings]
    gap_statements: dict[str, str] = {}  # gap_id -> statement (for relevance)
    max_results: int = 25
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    min_citations: int = 0
    skip_relevance: bool = False


class PipelineRequest(BaseModel):
    action: str  # "full" | "download" | "extract" | "analyze"
    gap_limit: int = 5
    dry_run: bool = False
    min_citations: int = 0
    skip_extraction: bool = False


# ── Existing: Ad-hoc OpenAlex search ──────────────────────────────────────

@router.post("/search")
async def discover_search(req: SearchRequest):
    """Search OpenAlex for papers matching the query."""
    try:
        from api_clients import OpenAlexClient

        client = OpenAlexClient(mailto="yara.aboubakr@research.edu")
        results = client.search(
            query=req.query,
            max_results=req.max_results,
            year_from=req.year_from,
            year_to=req.year_to,
            min_citations=req.min_citations,
        )
        return {"query": req.query, "count": len(results), "papers": results}
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="api_clients.py not found. Discovery module not yet installed.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 1. Gaps with matrix state ────────────────────────────────────────────

@router.get("/gaps")
async def discover_gaps():
    """Return gaps from GAP_TRACKER enriched with GAP_MATRIX state."""
    try:
        from ..services.matrix_reader import get_gaps_with_matrix_state
        return get_gaps_with_matrix_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 2. Claude Sonnet query generation (with cache) ───────────────────────

@router.post("/generate-queries")
async def generate_queries(req: QueryGenRequest):
    """Generate search queries for selected gaps using Claude Sonnet.

    Uses a local JSON cache to avoid re-calling Claude for gaps that
    already have queries.  Pass force=true to regenerate.
    """
    if not req.gap_ids:
        raise HTTPException(status_code=400, detail="No gap IDs provided")

    try:
        from ..services.query_cache import (
            get_cached_queries,
            set_cached_queries,
        )

        # 1. Check cache
        cached = {} if req.force else get_cached_queries(req.gap_ids)
        need_generation = [gid for gid in req.gap_ids if gid not in cached]

        queries_map: dict[str, list[str]] = dict(cached)  # start with cached

        # 2. Generate for uncached gaps only
        if need_generation:
            from gap_query_builder import GapReader, GapQueryBuilder

            reader = GapReader()
            all_gaps = reader.get_all_gaps()
            selected = [g for g in all_gaps if g.get("gap_id") in need_generation]

            # Fallback: build from pipeline_state if not found in sheet
            if len(selected) < len(need_generation):
                found_ids = {g["gap_id"] for g in selected}
                try:
                    from ..services.state_reader import get_gaps as get_state_gaps
                    state_gaps = get_state_gaps()
                    for sg in state_gaps:
                        if sg.get("gap_id") in need_generation and sg["gap_id"] not in found_ids:
                            selected.append({
                                "gap_id": sg.get("gap_id", ""),
                                "gap_type": sg.get("gap_type", ""),
                                "gap_statement": sg.get("gap_statement", ""),
                                "severity": sg.get("severity", ""),
                                "status": sg.get("status", ""),
                            })
                except Exception:
                    pass

            if not selected and not cached:
                raise HTTPException(
                    status_code=404,
                    detail=f"No matching gaps found for IDs: {req.gap_ids[:3]}",
                )

            if selected:
                builder = GapQueryBuilder()
                results = builder.build_queries(selected)

                for item in results:
                    gid = item.get("gap_id", "")
                    query_list = item.get("queries", [])
                    queries = [q["query"] if isinstance(q, dict) else str(q) for q in query_list]
                    queries_map[gid] = queries
                    # Cache the newly generated queries
                    set_cached_queries(gid, queries)

        return {
            "queries": queries_map,
            "gap_count": len(queries_map),
            "from_cache": len(cached),
            "newly_generated": len(queries_map) - len(cached),
        }

    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Gap query modules not available: {e}",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 2b. Query cache CRUD ─────────────────────────────────────────────────

@router.get("/cached-queries")
async def get_all_cached_queries():
    """Return all cached queries for all gaps."""
    try:
        from ..services.query_cache import get_all_cached
        return get_all_cached()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/queries/{gap_id}")
async def update_gap_queries(gap_id: str, req: UpdateQueriesRequest):
    """Manually update queries for a gap (edit/add/remove)."""
    try:
        from ..services.query_cache import set_cached_queries
        set_cached_queries(gap_id, req.queries)
        return {"gap_id": gap_id, "queries": req.queries, "status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/queries/{gap_id}")
async def delete_gap_queries(gap_id: str):
    """Delete cached queries for a gap so they can be regenerated."""
    try:
        from ..services.query_cache import delete_cached_queries
        delete_cached_queries([gap_id])
        return {"gap_id": gap_id, "status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 3. Batch search with deduplication + AI relevance ────────────────────

@router.post("/search-gaps")
async def search_gaps(req: GapSearchRequest):
    """Search OpenAlex for all gap queries, deduplicate, and optionally
    score relevance with Claude Sonnet."""
    try:
        from api_clients import OpenAlexClient

        client = OpenAlexClient(mailto="yara.aboubakr@research.edu")

        all_results = []
        seen_dois: set[str] = set()
        total_found = 0

        for gap_id, queries in req.queries.items():
            for query in queries:
                results = client.search(
                    query=query,
                    max_results=req.max_results,
                    year_from=req.year_from,
                    year_to=req.year_to,
                    min_citations=req.min_citations,
                )
                total_found += len(results)

                for paper in results:
                    doi = paper.get("doi", "") or paper.get("DOI", "")
                    if doi and doi in seen_dois:
                        continue
                    if doi:
                        seen_dois.add(doi)
                    paper["source_gap_id"] = gap_id
                    all_results.append(paper)

        # Deduplicator pass
        try:
            from deduplicator import Deduplicator
            dedup = Deduplicator()
            unique = []
            for paper in all_results:
                is_dup, _reason = dedup.is_duplicate(paper)
                paper["is_known"] = is_dup
                unique.append(paper)
        except ImportError:
            unique = all_results
            for p in unique:
                p["is_known"] = False

        # AI relevance scoring (optional)
        if not req.skip_relevance and req.gap_statements and unique:
            try:
                from ..services.relevance import assess_relevance
                new_papers = [p for p in unique if not p.get("is_known")]
                if new_papers:
                    scores = assess_relevance(new_papers, req.gap_statements)
                    score_map = {s["paper_index"]: s for s in scores}
                    for i, paper in enumerate(new_papers):
                        sc = score_map.get(i, {})
                        paper["relevance_score"] = sc.get("relevance_score", 0)
                        paper["relevance_reason"] = sc.get("reason", "")
            except Exception as e:
                print(f"[search-gaps] Relevance scoring failed: {e}")
                # Continue without scores

        duplicates_removed = total_found - len([p for p in unique if not p.get("is_known")])

        return {
            "results": unique,
            "dedup_stats": {
                "total_found": total_found,
                "duplicates_removed": duplicates_removed,
                "unique": len([p for p in unique if not p.get("is_known")]),
                "already_known": len([p for p in unique if p.get("is_known")]),
            },
        }
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="api_clients.py not found. Discovery module not yet installed.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 4. Pipeline actions ──────────────────────────────────────────────────

@router.post("/run-pipeline")
async def run_pipeline(req: PipelineRequest):
    """Trigger a discovery pipeline action via process_runner."""
    try:
        from ..services.process_runner import active_process

        action_map = {
            "full": "discovery_full",
            "analyze": "discovery_analyze",
        }

        command_type = action_map.get(req.action)
        if not command_type:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

        flags = {}
        if req.action == "full":
            flags["gap_limit"] = req.gap_limit
            if req.dry_run:
                flags["dry_run"] = True
            if req.min_citations > 0:
                flags["min_citations"] = req.min_citations
            if req.skip_extraction:
                flags["skip_extraction"] = True
        elif req.action == "analyze":
            if req.dry_run:
                flags["dry_run"] = True

        result = await active_process.start(command_type, flags)
        if "error" in result:
            raise HTTPException(status_code=409, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 5. Gap matrix data ──────────────────────────────────────────────────

@router.get("/matrix")
async def get_gap_matrix():
    """Read GAP_MATRIX data for dashboard visualization."""
    try:
        from ..services.matrix_reader import get_matrix_data
        return get_matrix_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 6. Gap evidence ─────────────────────────────────────────────────────

@router.get("/evidence/{gap_id}")
async def get_gap_evidence(gap_id: str):
    """Read GAP_EVIDENCE entries for a specific gap."""
    try:
        from ..services.matrix_reader import get_evidence
        return get_evidence(gap_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 7. Retroactive gap analysis ──────────────────────────────────────────

class RetroactiveRequest(BaseModel):
    gap_ids: list[str] = []  # Empty = auto-detect uncovered gaps


@router.post("/retroactive")
async def run_retroactive_analysis(req: RetroactiveRequest):
    """
    Run retroactive gap analysis: check previously-analyzed papers
    against gaps that have zero evidence rows (or specified gap_ids).
    """
    try:
        from gap_matrix_analyzer import GapMatrixAnalyzer
        analyzer = GapMatrixAnalyzer()

        if req.gap_ids:
            result = analyzer.retroactive_analyze(
                new_gap_ids=req.gap_ids,
                current_paper_id="",
            )
        else:
            result = analyzer.retroactive_analyze_all_uncovered()

        return {
            "status": "ok",
            "papers_scanned": result.get("papers_scanned", 0),
            "papers_relevant": result.get("papers_relevant", 0),
            "evidence_written": result.get("evidence_written", 0),
            "gaps_newly_resolved": result.get("gaps_newly_resolved", []),
            "per_paper": result.get("per_paper", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 8. Gap deduplication ─────────────────────────────────────────────────

@router.get("/dedup-stats")
async def get_dedup_stats():
    """Get deduplication log statistics."""
    try:
        from gap_deduplicator import GapDeduplicator
        dedup = GapDeduplicator()
        return dedup.get_log_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DedupBackfillRequest(BaseModel):
    apply: bool = False  # If True, actually merge duplicates


@router.post("/dedup-backfill")
async def run_dedup_backfill(req: DedupBackfillRequest):
    """
    Cluster all existing gaps for semantic duplicates.
    With apply=True, merges duplicates in GAP_TRACKER.
    """
    try:
        from gap_deduplicator import GapDeduplicator
        from populator import SheetPopulator

        dedup = GapDeduplicator()
        pop = SheetPopulator(on_status=lambda msg: None)
        pop._ensure_connected()
        ws = pop._get_worksheet("GAP_TRACKER")
        rows = ws.get_all_records()

        all_gaps = []
        for row in rows:
            gap_id = str(row.get("Gap_ID", "")).strip()
            if not gap_id:
                continue
            all_gaps.append({
                "gap_id": gap_id,
                "gap_type": str(row.get("Gap_Type", "")),
                "gap_statement": str(row.get("Gap_Statement", "")),
            })

        clusters = dedup.backfill_clusters(all_gaps)
        dup_clusters = [c for c in clusters if isinstance(c, dict) and len(c.get("members", [])) > 1]

        if req.apply and dup_clusters:
            from gap_deduplicator import _apply_merges
            _apply_merges(pop, dup_clusters, all_gaps)

        return {
            "status": "ok",
            "total_gaps": len(all_gaps),
            "total_clusters": len(clusters),
            "duplicate_clusters": len(dup_clusters),
            "unique_gaps": len(clusters) - len(dup_clusters),
            "clusters": dup_clusters,
            "applied": req.apply,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
