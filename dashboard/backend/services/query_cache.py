"""Persistent JSON cache for generated gap queries — avoids re-calling Claude."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CACHE_FILE = PIPELINE_DIR / "discoveries" / "query_cache.json"


def _ensure_dir():
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_cache() -> dict:
    """Load the full cache dict.  Returns {} if file missing or corrupt."""
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(data: dict) -> None:
    _ensure_dir()
    CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_cached_queries(gap_ids: list[str]) -> dict[str, list[str]]:
    """Return cached queries only for gap_ids that are in the cache."""
    cache = load_cache()
    result: dict[str, list[str]] = {}
    for gid in gap_ids:
        entry = cache.get(gid)
        if entry and entry.get("queries"):
            result[gid] = entry["queries"]
    return result


def set_cached_queries(gap_id: str, queries: list[str]) -> None:
    """Store (or overwrite) queries for a single gap."""
    cache = load_cache()
    cache[gap_id] = {
        "queries": queries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_cache(cache)


def get_all_cached() -> dict:
    """Return the full cache (gap_id -> {queries, generated_at})."""
    return load_cache()


def get_all_cached_gap_ids() -> set[str]:
    """Set of gap_ids that have cached queries."""
    return {gid for gid, v in load_cache().items() if v.get("queries")}


def delete_cached_queries(gap_ids: list[str]) -> None:
    """Remove entries for the given gap_ids."""
    cache = load_cache()
    for gid in gap_ids:
        cache.pop(gid, None)
    save_cache(cache)
