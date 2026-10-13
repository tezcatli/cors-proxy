"""The in-memory catalog every /games request reads, and the IGDB cache's DB mirror.

All of it is rebuilt from the RSS feeds and the DB at startup; HTTP requests read
only from memory — no per-request DB queries. Writers replace or mutate these
attributes under `lock`; other modules always go through the module
(`state.game_index`), never `from catalog_state import …`, which would freeze a
binding that `feeds.refresh_feed` later replaces.
"""
import datetime
import json
import logging
import threading

from db import get_db
from models import Episode, IgdbEntry, PodcastGame

logger = logging.getLogger(__name__)

lock = threading.Lock()

episodes:      list[Episode] = []           # source of truth; owns all Episode objects
episode_index: dict[str, Episode] = {}      # episode.slug AND url_slug → same Episode
game_index:    dict[str, PodcastGame] = {}  # name_slug → PodcastGame
cached_at:     datetime.datetime | None = None

# Keyed by podcast_slug (make_slug(name) + '-' + episode.slug, the RSS guid).
# Loaded from DB at startup; written when a new IGDB resolution completes.
igdb_cache: dict[str, IgdbEntry] = {}

# Monotonic version of the data the read payloads derive from (episodes + IGDB
# cache). Bumped under `lock` on every feed re-parse that changed something /
# IGDB resolution, and used to key the cached responses in games.py so repeated
# reads (incl. 304 revalidations) skip re-serialising and re-hashing.
data_version: int = 0


def bump_version() -> None:
    """Invalidate the derived response caches without touching the IGDB cache."""
    global data_version
    with lock:
        data_version += 1


def store_entry(entry: IgdbEntry) -> None:
    """Cache one resolution, in memory and in the DB."""
    global data_version
    with lock:
        igdb_cache[entry.podcast_slug] = entry
        data_version += 1
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO igdb_cache '
            '(slug, igdb_id, igdb_slug, name, igdb_data, is_child, cached_at, correction_sig, '
            'enriched, method) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (entry.podcast_slug, entry.igdb_id, entry.igdb_slug, entry.name,
             json.dumps(entry.data) if entry.data else None,
             int(entry.is_child), entry.cached_at, entry.correction_sig, int(entry.enriched),
             entry.method)
        )


def load_igdb_cache_from_db() -> None:
    global igdb_cache
    with get_db() as conn:
        rows = conn.execute(
            'SELECT slug, igdb_id, igdb_slug, name, igdb_data, is_child, cached_at, '
            'correction_sig, enriched, method FROM igdb_cache'
        ).fetchall()
    cache = {}
    for row in rows:
        cache[row['slug']] = IgdbEntry(
            podcast_slug=row['slug'],
            igdb_id=row['igdb_id'],
            igdb_slug=row['igdb_slug'],
            name=row['name'],
            data=json.loads(row['igdb_data']) if row['igdb_data'] else None,
            is_child=bool(row['is_child']),
            cached_at=row['cached_at'],
            # NULL on a legacy row reads as "resolved with no correction".
            correction_sig=row['correction_sig'] or '',
            enriched=bool(row['enriched']),
            method=row['method'],
        )
    with lock:
        igdb_cache = cache


def prune_igdb_cache() -> None:
    """Drop igdb_cache rows (memory + DB) whose podcast_slug no longer matches any
    current appearance, so the cache stays bounded as the feed evolves. No-op when
    there are no appearances (e.g. an empty/odd parse) so a transient feed can't
    wipe the cache."""
    global data_version
    with lock:
        valid = {a.podcast_slug for game in game_index.values() for a in game.appearances}
        if not valid:
            return
        stale = [slug for slug in igdb_cache if slug not in valid]
        for slug in stale:
            del igdb_cache[slug]
        if stale:
            data_version += 1
    if stale:
        _delete_rows(stale)
        logger.info('Pruned %d orphaned igdb_cache row(s)', len(stale))


def purge_cache(podcast_slugs: list[str]) -> None:
    """Drop these cache keys from memory and DB so they re-resolve from scratch."""
    global data_version
    if not podcast_slugs:
        return
    with lock:
        for ps in podcast_slugs:
            igdb_cache.pop(ps, None)
        data_version += 1
    _delete_rows(podcast_slugs)


def _delete_rows(slugs: list[str]) -> None:
    with get_db() as conn:
        ph = ','.join('?' * len(slugs))
        conn.execute(f'DELETE FROM igdb_cache WHERE slug IN ({ph})', slugs)
