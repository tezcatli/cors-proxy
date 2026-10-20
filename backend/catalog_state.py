"""The in-memory catalog every /games request reads, and the IGDB cache's DB mirror.

The IGDB cache is two stores, because they are two decisions with their own keys
and lifetimes: `resolutions` (which game an appearance is — settled once, changed
only by a correction or an explicit refresh) and `games` (that game's data, shared
by all its appearances and renewed by id when it expires).

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
from models import Episode, IgdbEntry, IgdbGame, PodcastGame, Resolution

logger = logging.getLogger(__name__)

lock = threading.Lock()

episodes:      list[Episode] = []           # source of truth; owns all Episode objects
episode_index: dict[str, Episode] = {}      # episode.slug AND url_slug → same Episode
game_index:    dict[str, PodcastGame] = {}  # name_slug → PodcastGame
cached_at:     datetime.datetime | None = None

# Loaded from DB at startup; written as resolutions and fetches complete.
resolutions: dict[str, Resolution] = {}     # podcast_slug → which IGDB game it is
games:       dict[int, IgdbGame]   = {}     # igdb_id → that game's data

# Monotonic version of the data the read payloads derive from (episodes + IGDB
# stores). Bumped under `lock` on every feed re-parse that changed something /
# IGDB resolution, and used to key the cached responses in games.py so repeated
# reads (incl. 304 revalidations) skip re-serialising and re-hashing.
data_version: int = 0


def bump_version() -> None:
    """Invalidate the derived response caches without touching the IGDB cache."""
    global data_version
    with lock:
        data_version += 1


def entries() -> dict[str, IgdbEntry]:
    """A consistent snapshot of every appearance's resolution joined with its game."""
    with lock:
        return {slug: IgdbEntry(r, games.get(r.igdb_id) if r.igdb_id else None)
                for slug, r in resolutions.items()}


def entry(podcast_slug: str) -> IgdbEntry | None:
    with lock:
        r = resolutions.get(podcast_slug)
        return IgdbEntry(r, games.get(r.igdb_id) if r.igdb_id else None) if r else None


def store_resolution(resolution: Resolution) -> None:
    global data_version
    with lock:
        resolutions[resolution.podcast_slug] = resolution
        data_version += 1
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO resolutions '
            '(slug, igdb_id, is_child, resolved_at, correction_sig, method) VALUES (?,?,?,?,?,?)',
            (resolution.podcast_slug, resolution.igdb_id, int(resolution.is_child),
             resolution.resolved_at, resolution.correction_sig, resolution.method))


def store_game(game: IgdbGame) -> None:
    global data_version
    with lock:
        games[game.igdb_id] = game
        data_version += 1
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO igdb_games '
            '(igdb_id, igdb_slug, name, data, fetched_at, enriched) VALUES (?,?,?,?,?,?)',
            (game.igdb_id, game.igdb_slug, game.name, json.dumps(game.data),
             game.fetched_at, int(game.enriched)))


def load_igdb_cache_from_db() -> None:
    global resolutions, games
    with get_db() as conn:
        res_rows  = conn.execute('SELECT slug, igdb_id, is_child, resolved_at, correction_sig, '
                                 'method FROM resolutions').fetchall()
        game_rows = conn.execute('SELECT igdb_id, igdb_slug, name, data, fetched_at, enriched '
                                 'FROM igdb_games').fetchall()
    loaded_res = {row['slug']: Resolution(
        podcast_slug=row['slug'],
        igdb_id=row['igdb_id'],
        is_child=bool(row['is_child']),
        resolved_at=row['resolved_at'],
        correction_sig=row['correction_sig'],
        method=row['method'],
    ) for row in res_rows}
    loaded_games = {row['igdb_id']: IgdbGame(
        igdb_id=row['igdb_id'],
        igdb_slug=row['igdb_slug'],
        name=row['name'],
        data=json.loads(row['data']),
        fetched_at=row['fetched_at'],
        enriched=bool(row['enriched']),
    ) for row in game_rows}
    with lock:
        resolutions = loaded_res
        games       = loaded_games


def prune_igdb_cache() -> None:
    """Drop the resolutions no current appearance has, then the games no
    resolution points at, so both stay bounded as the feeds evolve. No-op when
    there are no appearances (e.g. an empty/odd parse) so a transient feed can't
    wipe the cache."""
    global data_version
    with lock:
        valid = {a.podcast_slug for game in game_index.values() for a in game.appearances}
        if not valid:
            return
        stale = [slug for slug in resolutions if slug not in valid]
        for slug in stale:
            del resolutions[slug]
        wanted = {r.igdb_id for r in resolutions.values()}
        unused = [igdb_id for igdb_id in games if igdb_id not in wanted]
        for igdb_id in unused:
            del games[igdb_id]
        if stale or unused:
            data_version += 1
    _delete_rows('resolutions', 'slug', stale)
    _delete_rows('igdb_games', 'igdb_id', unused)
    if stale or unused:
        logger.info('Pruned %d orphaned resolution(s) and %d unused game(s)',
                    len(stale), len(unused))


def purge_cache(podcast_slugs: list[str]) -> None:
    """Drop these appearances' resolutions so they re-resolve from scratch. Their
    games stay: whichever game they land on next, its data is still good."""
    global data_version
    if not podcast_slugs:
        return
    with lock:
        for ps in podcast_slugs:
            resolutions.pop(ps, None)
        data_version += 1
    _delete_rows('resolutions', 'slug', podcast_slugs)


_EXPIRED = '1970-01-01T00:00:00'


def expire_games(igdb_ids) -> None:
    """Mark these games stale, so the next resolution or sweep re-fetches and
    re-scrapes them. Their data keeps being served meanwhile — deleting them
    would drop every appearance on them out of its catalog group until then."""
    ids = [i for i in set(igdb_ids) if i is not None]
    with lock:
        for igdb_id in ids:
            if igdb_id in games:
                games[igdb_id].fetched_at = _EXPIRED
    if ids:
        with get_db() as conn:
            ph = ','.join('?' * len(ids))
            conn.execute(f'UPDATE igdb_games SET fetched_at = ? WHERE igdb_id IN ({ph})',
                         [_EXPIRED, *ids])


def drop_game(igdb_id: int) -> None:
    """IGDB no longer has this game: forget it, and every resolution onto it, so
    those appearances are searched again."""
    global data_version
    with lock:
        games.pop(igdb_id, None)
        slugs = [s for s, r in resolutions.items() if r.igdb_id == igdb_id]
        for slug in slugs:
            del resolutions[slug]
        data_version += 1
    _delete_rows('igdb_games', 'igdb_id', [igdb_id])
    _delete_rows('resolutions', 'slug', slugs)


def _delete_rows(table: str, column: str, keys: list) -> None:
    if not keys:
        return
    with get_db() as conn:
        ph = ','.join('?' * len(keys))
        conn.execute(f'DELETE FROM {table} WHERE {column} IN ({ph})', keys)
