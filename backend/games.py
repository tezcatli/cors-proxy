import json
import datetime
import pathlib
import queue as _queue_mod
import threading
import time

import requests as http
from flask import Blueprint, abort, jsonify, request, Response, stream_with_context

from auth import require_auth
from config import Config
from limiter import limiter
from corrections import find_by_podcast
from db import get_db, utcnow
from igdb import fetch_by_id, fetch_by_name, fetch_time_to_beat
import hltb
import metacritic
from models import Chapter, Episode, GameAppearance, IgdbEntry, PodcastGame
from podcasts import PODCASTS, podcast_meta
from rss import parse_feed, assign_url_slugs, is_game_catalog_excluded, find_chapter_for_game
from utils import make_slug

import logging

logger = logging.getLogger(__name__)

games_bp = Blueprint('games', __name__, url_prefix='/silence/games')
games_bp.before_request(require_auth)


# ── In-memory state ───────────────────────────────────────────────────────────
# All four structures are rebuilt from the RSS feed and/or DB at startup.
# HTTP requests read only from memory — no per-request DB queries.

_state_lock = threading.Lock()

_cached_episodes: list[Episode] = []           # source of truth; owns all Episode objects
_episode_index:   dict[str, Episode] = {}      # episode.slug → Episode (same objects)
_game_index:      dict[str, PodcastGame] = {}  # name_slug    → PodcastGame
_cached_at:       datetime.datetime | None = None

# Keyed by podcast_slug (make_slug(name) + '-' + episode.slug, the RSS guid).
# Loaded from DB at startup; written when a new IGDB resolution completes.
_igdb_cache: dict[str, IgdbEntry] = {}

# Monotonic version of the data the read payloads derive from (episodes + IGDB
# cache). Bumped under _state_lock on every feed re-parse / IGDB resolution, and
# used to key the cached responses below so repeated reads (incl. 304
# revalidations) skip re-serialising and re-hashing the (large) payloads.
_data_version:  int = 0
# Serialised-response caches: (key, body_text, etag). Feed key = _data_version;
# catalog key = (_data_version, pending) since the body carries `pending`.
_catalog_cache: tuple | None = None
_feed_cache:    tuple | None = None
# Pending count memo: (version, minute_bucket, value).
_pending_cache: tuple[int, int, int] | None = None

# ── SSE subscriber management ─────────────────────────────────────────────────

_resolution_subs:      list[_queue_mod.Queue] = []
_resolution_subs_lock: threading.Lock         = threading.Lock()


def _broadcast(event: dict) -> None:
    with _resolution_subs_lock:
        for q in _resolution_subs:
            q.put_nowait(event)


# ── AI chapter injection ──────────────────────────────────────────────────────

def _seconds_to_ts(secs: float) -> str:
    s = int(secs)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def _load_ai_chapter_index() -> dict[str, list]:
    path = pathlib.Path(__file__).parent / 'chapters.json'
    if not path.exists():
        logger.warning('chapters.json not found at %s', path)
        return {}
    with path.open(encoding='utf-8') as f:
        data = json.load(f)
    index = {}
    for ep in data.get('episodes', []):
        slug = make_slug(ep.get('title', ''))
        if slug:
            index[slug] = ep.get('chapters', [])
    return index


def _inject_ai_chapters(episodes: list[Episode], ai_index: dict) -> None:
    injected = 0
    for episode in episodes:
        # chapters.json is keyed by make_slug(title); episode.slug is now the guid,
        # so match on the title slug here.
        title_slug = make_slug(episode.title)
        if episode.chapters or title_slug not in ai_index:
            continue
        raw_chapters = ai_index[title_slug]
        chapters = [
            Chapter(
                timestamp=_seconds_to_ts(c['start_s']),
                timestamp_seconds=int(c['start_s']),
                title=c['title'],
                game_name=c.get('game_name'),
            )
            for c in raw_chapters
            if c.get('start_s') is not None and c.get('title')
            and c['title'] not in ('Publicité', 'Transition')
        ]
        episode.chapters = chapters
        for mention in episode.games:
            matched = find_chapter_for_game(mention.name, chapters)
            if matched:
                mention.timestamp = matched.timestamp
                mention.timestamp_seconds = matched.timestamp_seconds
        injected += 1
    if injected:
        logger.info('Injected AI chapters into %d episodes', injected)


# ── RSS state helpers ─────────────────────────────────────────────────────────

def _feed_is_stale() -> bool:
    return (
        _cached_at is None
        or (utcnow() - _cached_at).total_seconds() >= Config.RSS_TTL_HOURS * 3600
    )


def _build_indexes(episodes: list[Episode]) -> tuple[dict, dict]:
    """Build episode_index and game_index from a list of Episode objects."""
    episode_index: dict[str, Episode]     = {}
    game_index:    dict[str, PodcastGame] = {}

    for episode in episodes:
        episode_index[episode.slug] = episode
        # Register the pretty url_slug too, so /games/episode resolves either the
        # guid (legacy/cached links) or the human-readable slug.
        if episode.url_slug:
            episode_index[episode.url_slug] = episode

        if is_game_catalog_excluded(episode.title):
            continue

        for mention in episode.games:
            name_slug    = make_slug(mention.name)
            # Per-episode cache/appearance key (episode.slug is the stable guid).
            # Same game in the same episode collides → deduped; distinct episodes
            # (incl. same-day) get distinct keys and are both kept.
            podcast_slug = f'{name_slug}-{episode.slug}'

            if name_slug not in game_index:
                game_index[name_slug] = PodcastGame(name_slug=name_slug, name=mention.name)
            else:
                existing = game_index[name_slug]
                # Drop only a true intra-episode duplicate (same game twice in one item).
                if any(a.podcast_slug == podcast_slug for a in existing.appearances):
                    logger.info('Duplicate mention %r in episode %r, skipping', podcast_slug, episode.title)
                    continue

            game = game_index[name_slug]
            game.appearances.append(GameAppearance(
                episode=episode,
                mention=mention,
                podcast_slug=podcast_slug,
            ))
            if episode.pub_ts and (game.latest_pub_ts is None or episode.pub_ts > game.latest_pub_ts):
                game.latest_pub_ts = episode.pub_ts
            game.episode_count += 1

    return episode_index, game_index


# Per-podcast HTTP cache validators and last-parsed episode lists. The cached
# episode lists let a 304 ("unchanged") keep that feed's episodes while another
# feed is re-parsed — every refresh recombines all feeds into one catalog.
_feed_meta:     dict[str, dict] = {}            # podcast_id -> {etag, last_modified}
_feed_episodes: dict[str, list[Episode]] = {}   # podcast_id -> last parsed episodes


def _fetch_feed(podcast) -> bool:
    """Fetch one podcast's feed; (re)parse it into `_feed_episodes` on a 200.

    Returns True when the feed changed (200, re-parsed), False on 304/unchanged.
    Raises on network/HTTP/parse errors — caller decides how to handle.
    """
    headers = {'User-Agent': 'PodcastCatalog/1.0'}
    meta = _feed_meta.get(podcast.id, {})
    if meta.get('etag'):          headers['If-None-Match']    = meta['etag']
    if meta.get('last_modified'): headers['If-Modified-Since'] = meta['last_modified']

    resp = http.get(podcast.feed_url, timeout=Config.REQUEST_TIMEOUT, headers=headers)
    if resp.status_code == 304 and podcast.id in _feed_episodes:
        logger.info('Feed %s unchanged (304); keeping cached episodes', podcast.id)
        return False
    resp.raise_for_status()
    _feed_meta[podcast.id] = {
        'etag':          resp.headers.get('ETag'),
        'last_modified': resp.headers.get('Last-Modified'),
    }
    _feed_episodes[podcast.id] = parse_feed(
        resp.content, extractor=podcast.extractor, podcast_id=podcast.id)
    return True


def _refresh_feed() -> None:
    """Fetch every registered podcast, then recombine all feeds into one catalog.

    Each feed is fetched independently (per-feed ETag); a single feed failing
    doesn't abort the others as long as we already have cached episodes for it.
    If *no* feed yields any episodes, the whole refresh raises so the caller can
    keep serving the previous cache rather than blanking it.
    """
    global _cached_episodes, _episode_index, _game_index, _cached_at, _data_version

    errors: list[str] = []
    for podcast in PODCASTS:
        try:
            _fetch_feed(podcast)
        except Exception as exc:
            errors.append(f'{podcast.id}: {exc}')
            logger.warning('Feed fetch failed for %s: %s', podcast.id, exc)

    # Combine every feed's episodes (cached lists survive a 304 or a failed fetch).
    episodes = [ep for podcast in PODCASTS for ep in _feed_episodes.get(podcast.id, [])]
    if not episodes:
        raise RuntimeError('No episodes from any feed: ' + '; '.join(errors) if errors
                           else 'No episodes from any feed')

    # Interleave both feeds newest-first; otherwise each feed's block would stay
    # contiguous (e.g. all SOJ before any FDG) and the second podcast would be
    # buried at the bottom of the episodes feed. Stable sort keeps ties/undated
    # items in their existing intra-feed order.
    episodes.sort(key=lambda e: e.pub_ts or 0, reverse=True)

    assign_url_slugs(episodes)
    ai_index = _load_ai_chapter_index()
    _inject_ai_chapters(episodes, ai_index)
    episode_index, game_index = _build_indexes(episodes)
    with _state_lock:
        _cached_episodes = episodes
        _episode_index   = episode_index
        _game_index      = game_index
        _cached_at       = utcnow()
        _data_version   += 1
    _prune_igdb_cache()


# ── IGDB cache helpers ────────────────────────────────────────────────────────

def _load_igdb_cache_from_db() -> None:
    global _igdb_cache
    with get_db() as conn:
        rows = conn.execute(
            'SELECT slug, igdb_id, igdb_slug, name, igdb_data, is_child, cached_at FROM igdb_cache'
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
        )
    with _state_lock:
        _igdb_cache = cache


def _prune_igdb_cache() -> None:
    """Drop igdb_cache rows (memory + DB) whose podcast_slug no longer matches any
    current appearance, so the cache stays bounded as the feed evolves. No-op when
    there are no appearances (e.g. an empty/odd parse) so a transient feed can't
    wipe the cache."""
    global _data_version
    with _state_lock:
        valid = {a.podcast_slug for game in _game_index.values() for a in game.appearances}
        if not valid:
            return
        stale = [slug for slug in _igdb_cache if slug not in valid]
        for slug in stale:
            del _igdb_cache[slug]
        if stale:
            _data_version += 1
    if stale:
        with get_db() as conn:
            ph = ','.join('?' * len(stale))
            conn.execute(f'DELETE FROM igdb_cache WHERE slug IN ({ph})', stale)
        logger.info('Pruned %d orphaned igdb_cache row(s)', len(stale))


def _best_igdb_entry(game: PodcastGame) -> IgdbEntry | None:
    """Pick the best resolved IgdbEntry for a game across all its appearances.

    Prefers non-child entries; among equals, takes the most recently cached.
    """
    candidates = [
        _igdb_cache[a.podcast_slug]
        for a in game.appearances
        if a.podcast_slug in _igdb_cache and _igdb_cache[a.podcast_slug].igdb_slug
    ]
    if not candidates:
        return None
    # Non-child (canonical game) preferred over child (DLC/version redirected to parent)
    non_child = [e for e in candidates if not e.is_child]
    pool      = non_child if non_child else candidates
    return max(pool, key=lambda e: e.cached_at)


def _primary_and_entry(
    matched_games: list[PodcastGame],
    best_by_game: dict[str, IgdbEntry | None],
) -> tuple[PodcastGame, IgdbEntry | None]:
    """The representative game for a catalog group (a non-child if any) and its best entry.

    `best_by_game` maps name_slug → best IgdbEntry, precomputed once per build so
    `_best_igdb_entry` isn't recomputed here.
    """
    primary = next(
        (g for g in matched_games if (e := best_by_game.get(g.name_slug)) and not e.is_child),
        matched_games[0],
    )
    return primary, best_by_game.get(primary.name_slug)


# ── IGDB resolution ───────────────────────────────────────────────────────────

def _resolve_one(podcast_slug: str, name: str, pub_ts: int | None) -> None:
    global _data_version
    logger.info('Resolving IGDB for slug=%r name=%r', podcast_slug, name)
    correction = find_by_podcast(name, pub_ts)
    try:
        if correction and correction.get('igdb_id'):
            # A pinned id is authoritative — don't let canonical resolution redirect
            # it (e.g. a remake IGDB models as a "port" of an earlier version).
            result = fetch_by_id(correction['igdb_id'], canonical=False)
        else:
            search_name = (correction or {}).get('search_name') or name
            hint_date   = (correction or {}).get('hint_date')
            effective_ts = (
                int(datetime.datetime.fromisoformat(hint_date)
                    .replace(tzinfo=datetime.timezone.utc).timestamp())
                if hint_date else pub_ts
            )
            result = fetch_by_name(search_name, effective_ts)
    except Exception as exc:
        logger.warning('IGDB resolution failed slug=%r name=%r: %s', podcast_slug, name, exc)
        return

    if result and result.data is not None:
        # Real Metacritic score (overrides the IGDB aggregate already in the blob),
        # and durée de vie — HowLongToBeat primary, IGDB time-to-beat fallback. Both
        # best-effort: any failure leaves the IGDB value / hides the stat.
        mc = metacritic.fetch_metascore(result.name)
        if mc is not None:
            result.data['metacritic'] = mc
        result.data['timeToBeatHours'] = (
            hltb.fetch_time_to_beat(result.name, result.data.get('released'))
            or fetch_time_to_beat(result.id)
        )

    igdb_slug = (result.slug or make_slug(result.name)) if result else None
    now       = utcnow().isoformat()

    entry = IgdbEntry(
        podcast_slug=podcast_slug,
        igdb_id=result.id             if result else None,
        igdb_slug=igdb_slug,
        name=result.name              if result else None,
        data=result.data              if result else None,
        is_child=result.is_child      if result else False,
        cached_at=now,
    )
    with _state_lock:
        _igdb_cache[podcast_slug] = entry
        _data_version += 1

    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO igdb_cache '
            '(slug, igdb_id, igdb_slug, name, igdb_data, is_child, cached_at) VALUES (?,?,?,?,?,?,?)',
            (podcast_slug, entry.igdb_id, entry.igdb_slug, entry.name,
             json.dumps(entry.data) if entry.data else None,
             int(entry.is_child), now)
        )

    _broadcast({
        'type':     'resolved',
        'nameSlug': make_slug(name),
        'igdbSlug': igdb_slug,
        'igdb':     {'metacritic': entry.data.get('metacritic'),
                     'coverImageId': entry.data.get('coverImageId')} if entry.data else None,
    })


_resolve_lock   = threading.Lock()
_resolve_thread: threading.Thread | None = None
_resolve_stop:   threading.Event  | None = None


def _fresh_slugs(cache_items) -> set:
    """Cache keys resolved within the IGDB TTL window. Compares parsed datetimes,
    not ISO strings, so a whole-second timestamp (no fractional part) can't
    mis-sort against a fractional cutoff."""
    cutoff = utcnow() - datetime.timedelta(hours=Config.IGDB_TTL_HOURS)
    return {
        slug for slug, entry in cache_items
        if datetime.datetime.fromisoformat(entry.cached_at) > cutoff
    }


def _count_appearances_not_in(excluded: set) -> int:
    """Count appearances whose cache key isn't in `excluded`. Caller holds _state_lock."""
    return sum(
        1 for game in _game_index.values()
        for a in game.appearances
        if a.podcast_slug not in excluded
    )


def _resolve_pending(stop: threading.Event) -> None:
    try:
        with _state_lock:
            games      = dict(_game_index)
            cache_snap = list(_igdb_cache.items())
        if not games:
            return

        fresh_slugs = _fresh_slugs(cache_snap)

        for name_slug, game in games.items():
            if stop.is_set():
                break
            pending = [a for a in game.appearances if a.podcast_slug not in fresh_slugs]
            for appearance in pending:
                if stop.is_set():
                    break
                _resolve_one(
                    appearance.podcast_slug,
                    game.name,
                    appearance.episode.pub_ts,
                )
    finally:
        _broadcast({'type': 'done'})
        global _resolve_stop
        with _resolve_lock:
            if _resolve_stop is stop:
                _resolve_stop = None


def _schedule_resolve(force: bool = False) -> None:
    global _resolve_thread, _resolve_stop
    with _resolve_lock:
        if not force and _resolve_thread and _resolve_thread.is_alive():
            return
        if _resolve_stop:
            _resolve_stop.set()
        stop            = threading.Event()
        _resolve_stop   = stop
        _resolve_thread = threading.Thread(target=_resolve_pending, args=(stop,), daemon=True)
        _resolve_thread.start()


# ── Periodic re-resolve (retry transient failures without a manual refresh) ────

_periodic_stop: threading.Event | None = None


def _periodic_resolve(stop: threading.Event) -> None:
    interval = Config.RESOLVE_RETRY_MINUTES * 60
    while not stop.wait(interval):
        try:
            # Proactively pick up newly published episodes during idle periods.
            if _feed_is_stale():
                try:
                    _refresh_feed()
                except Exception as exc:
                    logger.warning('Periodic feed refresh failed: %s', exc)
            # Use the same TTL-aware notion the catalog/SSE use, so never-cached
            # AND TTL-expired appearances both get picked up (a resolve refreshes
            # cached_at, so this self-limits to once per TTL period).
            pending = _count_pending()
            if pending:
                logger.info('Periodic re-resolve: %d pending appearance(s)', pending)
                _schedule_resolve()
        except Exception:
            logger.exception('Periodic re-resolve tick failed')


def _start_periodic_resolve() -> None:
    global _periodic_stop
    if _periodic_stop:
        return
    _periodic_stop = threading.Event()
    threading.Thread(target=_periodic_resolve, args=(_periodic_stop,), daemon=True).start()


# ── Startup ───────────────────────────────────────────────────────────────────

def _startup() -> None:
    _load_igdb_cache_from_db()
    if _feed_is_stale():
        try:
            _refresh_feed()
        except Exception as exc:
            logger.warning('Startup RSS fetch failed: %s', exc)
    _schedule_resolve()
    _start_periodic_resolve()


def startup_warmup() -> None:
    threading.Thread(target=_startup, daemon=True).start()


# ── Response serialisation ────────────────────────────────────────────────────

def _serialise_appearance(appearance: GameAppearance) -> dict:
    """Game-detail episode = the unified episode shape carrying this game's mention."""
    ep = appearance.episode
    return _serialise_episode(ep, _build_resolved(ep), mention=appearance.mention)


def _build_resolved(episode: Episode) -> dict[str, tuple[str, str, str | None]]:
    """Build a timestamp → (igdb_name, igdb_slug, cover_image_id) map for one episode."""
    resolved: dict[str, tuple[str, str, str | None]] = {}
    for mention in episode.games:
        podcast_slug = f'{make_slug(mention.name)}-{episode.slug}'
        entry        = _igdb_cache.get(podcast_slug)
        if entry and entry.igdb_slug and mention.timestamp:
            cover_image_id = entry.data.get('coverImageId') if entry.data else None
            resolved[mention.timestamp] = (entry.name or mention.name, entry.igdb_slug, cover_image_id)
    return resolved


def _serialise_episode(
    episode: Episode,
    resolved: dict[str, tuple[str, str, str | None]],
    mention=None,
) -> dict:
    """Serialise an Episode to the single canonical JSON shape used everywhere.

    resolved maps timestamp_str → (igdb_name, igdb_slug, cover_image_id) for
    chapter/game annotation. `mention`, when given (game-detail context), fills
    the top-level timestamp fields with that game's position in the episode;
    otherwise they default to None/0 (feed / whole-episode context).
    """
    chapters = []
    for chapter in episode.chapters:
        ch: dict = {
            'timestamp':        chapter.timestamp,
            'timestampSeconds': chapter.timestamp_seconds,
            'title':            chapter.title,
        }
        if resolved and chapter.timestamp in resolved:
            igdb_name, igdb_slug, cover_image_id = resolved[chapter.timestamp]
            ch['resolvedName'] = igdb_name
            ch['slug']         = igdb_slug
            if cover_image_id:
                ch['coverImageId'] = cover_image_id
        chapters.append(ch)

    games = []
    for g in episode.games:
        entry: dict = {'name': g.name, 'timestamp': g.timestamp, 'timestampSeconds': g.timestamp_seconds}
        if resolved and g.timestamp and g.timestamp in resolved:
            entry['slug'] = resolved[g.timestamp][1]
        games.append(entry)

    return {
        'title':            episode.title,
        'slug':             episode.slug,
        'urlSlug':          episode.url_slug,
        'audioUrl':         episode.audio_url,
        'pubTs':            episode.pub_ts,
        'imageUrl':         episode.image_url,
        'description':      episode.description,
        'chapters':         chapters,
        'games':            games,
        'podcast':          podcast_meta(episode.podcast_id),
        'timestamp':        mention.timestamp        if mention else None,
        'timestampSeconds': mention.timestamp_seconds if mention else 0,
    }


def _serialise_episode_slim(episode: Episode) -> dict:
    """Lightweight episode shape for the feed *list* (`GET /games/episodes`).

    Omits `description` and `chapters` — together ~70% of the full feed payload —
    since the list cards (EpisodeFeedCard) never read them; they're served by the
    single-episode endpoint instead. Also skips the per-episode `_build_resolved`
    IGDB scan (run for every episode otherwise). `games` is kept (names power the
    feed's client-side search)."""
    return {
        'title':            episode.title,
        'slug':             episode.slug,
        'urlSlug':          episode.url_slug,
        'audioUrl':         episode.audio_url,
        'pubTs':            episode.pub_ts,
        'imageUrl':         episode.image_url,
        'games':            [{'name': g.name, 'timestamp': g.timestamp,
                              'timestampSeconds': g.timestamp_seconds}
                             for g in episode.games],
        'podcast':          podcast_meta(episode.podcast_id),
        'timestamp':        None,
        'timestampSeconds': 0,
    }


# ── Catalog building ──────────────────────────────────────────────────────────

def _build_catalog() -> list[dict]:
    with _state_lock:
        games = dict(_game_index)

    # Resolve each game's best entry exactly once; reused for grouping and below.
    best_by_game = {name_slug: _best_igdb_entry(game) for name_slug, game in games.items()}

    groups: dict[str, list[PodcastGame]] = {}
    for name_slug, game in games.items():
        entry = best_by_game[name_slug]
        slug  = entry.igdb_slug if entry else game.name_slug
        groups.setdefault(slug, []).append(game)

    result = []
    for slug, matched_games in groups.items():
        primary, entry = _primary_and_entry(matched_games, best_by_game)
        igdb_slim = {
            'metacritic':   entry.data.get('metacritic'),
            'coverImageId': entry.data.get('coverImageId'),
        } if entry and entry.data else None
        # Count distinct episodes (by guid) — two name variants co-occurring in one
        # episode must not double-count it.
        episode_slugs = {a.episode.slug for g in matched_games for a in g.appearances}
        pub_tss       = [g.latest_pub_ts for g in matched_games if g.latest_pub_ts is not None]
        # Source podcasts that cover this game (drives badges + the header filter).
        podcasts = sorted({a.episode.podcast_id
                           for g in matched_games for a in g.appearances
                           if a.episode.podcast_id})
        result.append({
            'slug':         slug,
            'name':         _display_name(primary, entry),
            'igdb':         igdb_slim,
            'episodeCount': len(episode_slugs),
            'latestPubTs':  max(pub_tss) if pub_tss else None,
            'podcasts':     podcasts,
        })

    return sorted(result, key=lambda g: g['name'].lower())


def _display_name(game: PodcastGame, entry: IgdbEntry | None) -> str:
    """Resolve the display name: corrections override > IGDB canonical > raw podcast name."""
    if entry and not entry.is_child:
        # A correction may override the display name for a (non-child) resolution.
        first_pub_ts = game.appearances[0].episode.pub_ts if game.appearances else None
        corr         = find_by_podcast(game.name, first_pub_ts)
        if corr and corr.get('display_name'):
            return corr['display_name']
    if entry and entry.name:
        return entry.name
    return game.name


def _match_games(slug: str) -> tuple[list[PodcastGame], bool]:
    """Games whose best IGDB entry resolves to `slug` (igdb_slug, resolved=True),
    or the single name_slug match as a fallback (resolved=False). Aborts 404 when
    neither matches."""
    with _state_lock:
        games = dict(_game_index)
    matched = [
        game for game in games.values()
        if (entry := _best_igdb_entry(game)) and entry.igdb_slug == slug
    ]
    if matched:
        return matched, True
    name_slug = make_slug(slug)
    if name_slug in games:
        return [games[name_slug]], False
    abort(404, 'Game not found')


def _load_game(slug: str) -> dict:
    """Game-detail response `{name, slug, igdb, episodes}` for an igdb_slug (or a
    name_slug fallback for an unresolved game). `igdb` is the data dict or None."""
    matched, resolved = _match_games(slug)
    episodes = [_serialise_appearance(a) for game in matched for a in game.appearances]
    if resolved:
        best_by_game   = {g.name_slug: _best_igdb_entry(g) for g in matched}
        primary, entry = _primary_and_entry(matched, best_by_game)
        return {
            'name':     _display_name(primary, entry),
            'slug':     slug,
            'igdb':     entry.data if entry else None,
            'episodes': episodes,
        }
    return {
        'name':     matched[0].name,
        'slug':     make_slug(slug),
        'igdb':     None,
        'episodes': episodes,
    }


# ── Pending count ─────────────────────────────────────────────────────────────

def _count_pending() -> int:
    """Count appearances the resolver still considers pending — never resolved OR
    resolved longer ago than IGDB_TTL_HOURS. Matches `_resolve_pending`'s notion
    of "pending" so the catalog gate, the SSE endpoint, and the periodic retry all
    agree.

    Memoised against (data version, minute bucket): it changes only on a version
    bump or a TTL-boundary crossing, so a full rescan of the cache + appearances
    runs at most once per minute per version (≤60 s staleness, self-healing)."""
    global _pending_cache
    bucket = int(time.monotonic() // 60)
    with _state_lock:
        if _pending_cache and _pending_cache[0] == _data_version and _pending_cache[1] == bucket:
            return _pending_cache[2]
        value = _count_appearances_not_in(_fresh_slugs(_igdb_cache.items()))
        _pending_cache = (_data_version, bucket, value)
        return value


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _conditional_cached(cache, key, build_payload):
    """Conditional JSON response backed by a cached serialised body + ETag.

    `cache` is the current `(key, body_text, etag)` tuple (or None). On a hit the
    body is neither re-serialised nor re-hashed. Returns `(response, cache_tuple)`;
    the caller stores the returned tuple back under the lock.
    """
    if cache and cache[0] == key:
        resp = Response(cache[1], mimetype='application/json')
        resp.set_etag(cache[2])
    else:
        resp = jsonify(build_payload())
        resp.add_etag()
        cache = (key, resp.get_data(as_text=True), resp.get_etag()[0])
    resp.headers['Cache-Control'] = 'no-cache'
    return resp.make_conditional(request), cache


@games_bp.route('/episodes')
def games_episodes():
    global _feed_cache
    with _state_lock:
        version  = _data_version
        cache    = _feed_cache
        episodes = list(_cached_episodes)
    resp, new_cache = _conditional_cached(
        cache, version,
        lambda: [_serialise_episode_slim(ep) for ep in episodes],
    )
    if new_cache is not cache:
        with _state_lock:
            _feed_cache = new_cache
    return resp


@games_bp.route('/episode')
def games_episode():
    slug = request.args.get('slug')
    if not slug:
        abort(400, 'slug parameter is required')
    with _state_lock:
        episode = _episode_index.get(slug)
    if episode is None:
        abort(404, 'Episode not found')

    return jsonify(_serialise_episode(episode, _build_resolved(episode)))


@games_bp.route('', strict_slashes=False)
def catalog():
    if _feed_is_stale():
        try:
            _refresh_feed()
        except Exception as exc:   # network error, malformed XML, etc.
            if not _cached_episodes:
                abort(502, f'RSS feed unavailable: {exc}')
            logger.warning('Feed refresh failed; serving cached catalog: %s', exc)
        else:
            _schedule_resolve()
    global _catalog_cache
    pending = _count_pending()
    with _state_lock:
        cache = _catalog_cache
        key   = (_data_version, pending)
    resp, new_cache = _conditional_cached(
        cache, key,
        lambda: {'games': _build_catalog(), 'pending': pending},
    )
    if new_cache is not cache:
        with _state_lock:
            _catalog_cache = new_cache
    return resp


@games_bp.route('/refresh', methods=['POST'])
@limiter.limit("10 per minute")
def refresh():
    try:
        _refresh_feed()
    except Exception as exc:   # network error, malformed XML, etc.
        if not _cached_episodes:
            abort(502, f'RSS feed unavailable: {exc}')
        logger.warning('Manual refresh failed; serving cached catalog: %s', exc)
    else:
        _schedule_resolve(force=True)
    return jsonify({'games': _build_catalog(), 'pending': _count_pending()})


@games_bp.route('/resolution-stream')
def resolution_stream():
    q = _queue_mod.Queue()
    with _resolution_subs_lock:
        _resolution_subs.append(q)
    # If no resolver is running: start one when there's pending work (it will
    # broadcast 'resolved' events + a final 'done'), otherwise close out
    # immediately with our own 'done'. This keeps the stream consistent with the
    # catalog's `pending` gate — a reopen never returns an instant 'done' while
    # work remains, which would spin the client.
    if not (_resolve_thread and _resolve_thread.is_alive()):
        if _count_pending():
            _schedule_resolve()
        else:
            q.put_nowait({'type': 'done'})

    def generate():
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f'data: {json.dumps(event)}\n\n'
                    if event.get('type') == 'done':
                        break
                except _queue_mod.Empty:
                    yield ': heartbeat\n\n'
        finally:
            with _resolution_subs_lock:
                if q in _resolution_subs:
                    _resolution_subs.remove(q)

    r = Response(stream_with_context(generate()), mimetype='text/event-stream')
    r.headers['Cache-Control']     = 'no-cache'
    r.headers['X-Accel-Buffering'] = 'no'
    return r


@games_bp.route('/<string:slug>')
def game_detail(slug):
    return jsonify(_load_game(slug))


@games_bp.route('/<string:slug>/igdb-refresh', methods=['POST'])
@limiter.limit("10 per minute")
def game_igdb_refresh(slug):
    global _data_version
    # Collect all podcast_slugs for this igdb_slug (or name_slug fallback)
    matched_games, _ = _match_games(slug)

    # Remove stale entries from memory and DB
    podcast_slugs = [a.podcast_slug for game in matched_games for a in game.appearances]
    with _state_lock:
        for ps in podcast_slugs:
            _igdb_cache.pop(ps, None)
        _data_version += 1
    with get_db() as conn:
        ph = ','.join('?' * len(podcast_slugs))
        conn.execute(f'DELETE FROM igdb_cache WHERE slug IN ({ph})', podcast_slugs)

    # Re-resolve each appearance
    for game in matched_games:
        for appearance in game.appearances:
            _resolve_one(appearance.podcast_slug, game.name, appearance.episode.pub_ts)

    # Determine new igdb_slug for the redirect
    entry    = _best_igdb_entry(matched_games[0])
    new_slug = entry.igdb_slug if entry else make_slug(slug)

    return jsonify(_load_game(new_slug))
