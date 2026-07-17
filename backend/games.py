import json
import datetime
import pathlib
import queue as _queue_mod
import threading
import time

import requests as http
from flask import Blueprint, abort, jsonify, request, Response, stream_with_context

from auth import require_admin, require_auth
from config import Config
from limiter import limiter
import corrections
from corrections import find_by_podcast, unmatched_slugs
from db import get_db, utcnow
from igdb import fetch_by_id, fetch_by_name, fetch_time_to_beat, search_games
import hltb
import metacritic
from models import Chapter, Episode, GameAppearance, IgdbEntry, PodcastGame
from podcasts import PODCAST_BY_ID, PODCASTS, podcast_meta
from rss import parse_feed, assign_url_slugs, is_game_catalog_excluded, find_chapter_for_game
from utils import make_slug, norm, norm_key

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

            game_index[name_slug].appearances.append(GameAppearance(
                episode=episode,
                mention=mention,
                podcast_slug=podcast_slug,
            ))

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


_refresh_lock = threading.Lock()


def _refresh_feed() -> None:
    """Fetch every registered podcast, then recombine all feeds into one catalog.

    Each feed is fetched independently (per-feed ETag); a single feed failing
    doesn't abort the others as long as we already have cached episodes for it.
    If *no* feed yields any episodes, the whole refresh raises so the caller can
    keep serving the previous cache rather than blanking it.

    Serialized: a caller that waited on the lock while another thread refreshed
    piggybacks on that result instead of re-fetching (the concurrent callers are
    a stale-catalog request, the periodic thread, and POST /refresh — all of
    which just want "fresh now").
    """
    global _cached_episodes, _episode_index, _game_index, _cached_at, _data_version

    before = _cached_at
    with _refresh_lock:
        if _cached_at is not before:
            return

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
        dead = unmatched_slugs(game_index.keys())
        if dead:
            logger.warning('%d correction(s) match no game name in the feed: %s',
                           len(dead), ', '.join(dead))
        _prune_igdb_cache()


# ── IGDB cache helpers ────────────────────────────────────────────────────────

def _load_igdb_cache_from_db() -> None:
    global _igdb_cache
    with get_db() as conn:
        rows = conn.execute(
            'SELECT slug, igdb_id, igdb_slug, name, igdb_data, is_child, cached_at, '
            'correction_sig FROM igdb_cache'
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


# ── Appearance grouping ───────────────────────────────────────────────────────
# A catalog entry is a group of *appearances* that resolved to the same IGDB game
# — not a group of podcast names. Grouping by name would force every appearance
# of one name onto a single IGDB entry, so a retrospective episode on Silent Hill
# 2 (2001) and a review of the 2024 remake would collapse into one, each hiding
# the other's episodes. `Member` pairs an appearance with its owning PodcastGame
# (needed for the name_slug fallback key and the display name).

Member = tuple[PodcastGame, GameAppearance]


def _group_key(game: PodcastGame, appearance: GameAppearance,
               cache: dict[str, IgdbEntry]) -> str:
    """The catalog slug an appearance belongs to: its own IGDB slug once resolved,
    else the game's name_slug so unresolved appearances of a name stay together."""
    entry = cache.get(appearance.podcast_slug)
    return entry.igdb_slug if entry and entry.igdb_slug else game.name_slug


def _best_member(members: list[Member],
                 cache: dict[str, IgdbEntry]) -> tuple[Member, IgdbEntry] | None:
    """The representative (member, entry) of a group, or None when none resolved.

    Prefers non-child entries (a canonical game over a DLC/version redirected to
    its parent); among equals, the most recently cached.
    """
    candidates = [
        (m, cache[m[1].podcast_slug]) for m in members
        if m[1].podcast_slug in cache and cache[m[1].podcast_slug].igdb_slug
    ]
    if not candidates:
        return None
    non_child = [c for c in candidates if not c[1].is_child]
    pool      = non_child if non_child else candidates
    return max(pool, key=lambda c: c[1].cached_at)


def _group_members() -> tuple[dict[str, list[Member]], dict[str, IgdbEntry]]:
    """Every appearance in the catalog bucketed by group key, plus the IGDB cache
    snapshot the keys were derived from — callers must rank within a group against
    that same snapshot, or a concurrent resolution could move an entry between the
    two reads."""
    with _state_lock:
        games = dict(_game_index)
        cache = dict(_igdb_cache)
    groups: dict[str, list[Member]] = {}
    for game in games.values():
        for appearance in game.appearances:
            groups.setdefault(_group_key(game, appearance, cache), []).append((game, appearance))
    return groups, cache


# ── IGDB resolution ───────────────────────────────────────────────────────────

def _resolve_one(podcast_slug: str, name: str, pub_ts: int | None,
                 podcast_id: str = '') -> None:
    global _data_version
    logger.info('Resolving IGDB for slug=%r name=%r', podcast_slug, name)
    # corrections.json is the only thing that outranks the name search.
    correction = find_by_podcast(name, pub_ts, podcast_id)
    pinned_id  = (correction or {}).get('igdb_id')
    try:
        if pinned_id:
            # A pinned id is authoritative — don't let canonical resolution redirect
            # it (e.g. a remake IGDB models as a "port" of an earlier version).
            result = fetch_by_id(pinned_id, canonical=False)
        else:
            search_name = (correction or {}).get('search_name') or name
            hint_date   = (correction or {}).get('hint_date')
            podcast     = PODCAST_BY_ID.get(podcast_id)
            if hint_date:
                # An explicit curated date always wins, whatever the podcast.
                effective_ts = int(datetime.datetime.fromisoformat(hint_date)
                                   .replace(tzinfo=datetime.timezone.utc).timestamp())
            elif podcast and not podcast.use_date_hint:
                # Retrospective show: the episode date isn't evidence of the game's
                # release date, so search undated and let the ranker prefer the
                # earliest same-name entry.
                effective_ts = None
            else:
                effective_ts = pub_ts
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

    # Fingerprint the correction actually used, so a later sweep can tell when a
    # shipped corrections.json rules differently on this appearance than it did here.
    sig = corrections.fingerprint(correction)

    entry = IgdbEntry(
        podcast_slug=podcast_slug,
        igdb_id=result.id             if result else None,
        igdb_slug=igdb_slug,
        name=result.name              if result else None,
        data=result.data              if result else None,
        is_child=result.is_child      if result else False,
        cached_at=now,
        correction_sig=sig,
    )
    with _state_lock:
        _igdb_cache[podcast_slug] = entry
        _data_version += 1

    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO igdb_cache '
            '(slug, igdb_id, igdb_slug, name, igdb_data, is_child, cached_at, correction_sig) '
            'VALUES (?,?,?,?,?,?,?,?)',
            (podcast_slug, entry.igdb_id, entry.igdb_slug, entry.name,
             json.dumps(entry.data) if entry.data else None,
             int(entry.is_child), now, sig)
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


def _appearance_pending(game, appearance, cache, fresh_slugs) -> bool:
    """Whether the resolver should (re)resolve this appearance.

    Pending when it is TTL-stale or never cached (`fresh_slugs`), or when the
    correction in force now fingerprints differently than when it was last
    resolved — the latter is how a corrections.json shipped to an already-deployed
    instance takes effect: an added, changed *or removed* correction shifts the
    fingerprint and re-resolves exactly the affected appearances, nothing else."""
    if appearance.podcast_slug not in fresh_slugs:
        return True
    cached = cache.get(appearance.podcast_slug)
    if cached is None:
        return True
    current = corrections.fingerprint(find_by_podcast(
        game.name, appearance.episode.pub_ts, appearance.episode.podcast_id))
    return cached.correction_sig != current


def _count_appearances_pending(cache, fresh_slugs) -> int:
    """Count appearances the resolver considers pending. Caller holds _state_lock."""
    return sum(
        1 for game in _game_index.values()
        for a in game.appearances
        if _appearance_pending(game, a, cache, fresh_slugs)
    )


def _resolve_pending(stop: threading.Event) -> None:
    try:
        with _state_lock:
            games      = dict(_game_index)
            cache_snap = list(_igdb_cache.items())
        if not games:
            return

        cache       = dict(cache_snap)
        fresh_slugs = _fresh_slugs(cache_snap)

        for game in games.values():
            if stop.is_set():
                break
            pending = [a for a in game.appearances
                       if _appearance_pending(game, a, cache, fresh_slugs)]
            for appearance in pending:
                if stop.is_set():
                    break
                _resolve_one(
                    appearance.podcast_slug,
                    game.name,
                    appearance.episode.pub_ts,
                    appearance.episode.podcast_id,
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
    result = []
    groups, cache = _group_members()
    for slug, members in groups.items():
        best  = _best_member(members, cache)
        entry = best[1] if best else None
        igdb_slim = {
            'metacritic':   entry.data.get('metacritic'),
            'coverImageId': entry.data.get('coverImageId'),
        } if entry and entry.data else None
        # Count distinct episodes (by guid) — two name variants co-occurring in one
        # episode must not double-count it.
        episode_slugs = {a.episode.slug for _, a in members}
        pub_tss       = [a.episode.pub_ts for _, a in members if a.episode.pub_ts is not None]
        # Source podcasts that cover this game (drives badges + the header filter).
        podcasts = sorted({a.episode.podcast_id for _, a in members if a.episode.podcast_id})
        result.append({
            'slug':         slug,
            'name':         _group_display_name(members, best),
            'igdb':         igdb_slim,
            'episodeCount': len(episode_slugs),
            'latestPubTs':  max(pub_tss) if pub_tss else None,
            'podcasts':     podcasts,
        })

    return sorted(result, key=lambda g: g['name'].lower())


def _group_display_name(members: list[Member],
                        best: tuple[Member, IgdbEntry] | None) -> str:
    """Display name for a catalog group: corrections override > IGDB canonical >
    raw podcast name. The correction is looked up against the representative
    appearance's own wording and episode date, since a dated correction only
    applies to the episode it was written for."""
    if best:
        (game, appearance), entry = best
        if not entry.is_child:
            corr = find_by_podcast(appearance.mention.name, appearance.episode.pub_ts,
                                   appearance.episode.podcast_id)
            if corr and corr.get('display_name'):
                return corr['display_name']
        if entry.name:
            return entry.name
        return game.name
    return members[0][0].name


def _match_appearances(slug: str) -> tuple[list[Member], dict[str, IgdbEntry], bool]:
    """The appearances that make up the catalog entry `slug`, the cache snapshot
    they were grouped against, and whether the match was a resolved igdb_slug.

    Falls back to the name_slug group (unresolved appearances of that name) and,
    for a name whose appearances have since all resolved, to every appearance of
    the name — so an old /game/<name_slug> link still lands somewhere sensible
    instead of 404ing. Aborts 404 when nothing matches.
    """
    groups, cache = _group_members()
    if slug in groups and any(
            (e := cache.get(a.podcast_slug)) and e.igdb_slug == slug for _, a in groups[slug]):
        return groups[slug], cache, True
    name_slug = make_slug(slug)
    if name_slug in groups:
        return groups[name_slug], cache, False
    with _state_lock:
        game = _game_index.get(name_slug)
    if game:
        return [(game, a) for a in game.appearances], cache, False
    abort(404, 'Game not found')


def _load_game(slug: str) -> dict:
    """Game-detail response for an igdb_slug (or a name_slug fallback for an
    unresolved game). `igdb` is the data dict or None; `nameSlugs` lists the raw
    podcast names behind the entry, which the corrections API keys on."""
    members, cache, resolved = _match_appearances(slug)
    # Newest first: a group can mix appearances from several name variants and
    # both podcasts, whose per-name order says nothing about the group's.
    ordered    = sorted(members, key=lambda m: m[1].episode.pub_ts or 0, reverse=True)
    correction = _correction_for(members)
    payload = {
        'episodes':  [_serialise_appearance(a) for _, a in ordered],
        'nameSlugs': sorted({g.name_slug for g, _ in members}),
        # Lets the admin UI offer "remove the correction" without a second call,
        # and pre-fill the picker's « Nom affiché » field with the current
        # override (top-level `name` may already *be* that override).
        'corrected':   correction is not None,
        'displayName': (correction or {}).get('display_name'),
    }
    # `resolved` guarantees a member entry carries this igdb_slug, so best is set.
    if resolved and (best := _best_member(members, cache)):
        # igdbName is the entry's true IGDB name — what the picker shows as the
        # current resolution, unaffected by a display_name override.
        return {**payload, 'slug': slug, 'igdbName': best[1].name,
                'name': _group_display_name(members, best), 'igdb': best[1].data}
    return {**payload, 'slug': make_slug(slug), 'igdbName': None,
            'name': members[0][0].name, 'igdb': None}


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
        value = _count_appearances_pending(_igdb_cache, _fresh_slugs(_igdb_cache.items()))
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


# ── Admin: resolution stats & corrections ─────────────────────────────────────

_ROMAN = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
          'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}


def _numerals(text: str) -> str:
    """norm() with standalone roman numerals folded to digits: the podcast writes
    «Hades 2», IGDB says «Hades II». Only whole tokens convert, and both sides get
    the same treatment, so this can only ever make a comparison more lenient."""
    return ' '.join(_ROMAN.get(w, w) for w in norm(text).split())


# Share of words the two names have in common, above which they're taken to be
# the same game. Tuned against the live catalog: 0.5 clears reorderings and
# plurals ("Senua's Saga Hellblade II" / "Hellblade II: Senua's Saga") while
# still flagging "Astrobot" → "Astrobotanica".
_SUSPECT_OVERLAP = 0.5


def _is_suspect(podcast_name: str, igdb_name: str) -> bool:
    """True when the IGDB name looks unrelated to the podcast name.

    A flag for human review, not a verdict — so it is deliberately biased toward
    letting things through: a false positive buries the real misses in noise,
    while a miss is still correctable from the game's own page. Passes when the
    names differ only in spacing ("Astrobot"/"Astro Bot"), numeral style
    ("Hades 2"/"Hades II"), a subtitle ("Kirby" → "Kirby and the Forgotten
    World"), or word order/plurals. Flags "Astrobot" → "Astrobotanica".
    """
    if norm_key(podcast_name) == norm_key(igdb_name):
        return False
    a, b = _numerals(podcast_name), _numerals(igdb_name)
    if not a or not b or a == b:
        return False
    # Whole-word prefix or containment: a subtitle or a series name.
    if b.startswith(f'{a} ') or a.startswith(f'{b} '):
        return False
    if f' {a} ' in f' {b} ' or f' {b} ' in f' {a} ':
        return False
    # Otherwise fall back to how many words they share, which survives reordering
    # and plural/spelling drift that prefix matching can't.
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / max(len(wa), len(wb)) < _SUSPECT_OVERLAP


def _correction_for(members: list[Member]) -> dict | None:
    """The corrections.json entry ruling on these appearances, if any. Such a
    resolution is intentional however little the names look alike («Les gardiens
    de la galaxie» → «Marvel's Guardians of the Galaxy»), so it stays out of the
    review queue — and it drives the UI's "remove the correction" affordance and
    the display-name field."""
    return next((c for g, a in members
                 if (c := find_by_podcast(g.name, a.episode.pub_ts,
                                          a.episode.podcast_id))), None)


def _group_summary(slug: str, members: list[Member],
                   best: tuple[Member, IgdbEntry] | None) -> dict:
    # Report the group under its representative name — the one that actually
    # produced the resolution — not whichever variant happens to sort first.
    # `nameSlugs` lists them all: a group merging several spellings has no single
    # correction target, and the client must not silently pin only one of them.
    game  = best[0][0] if best else members[0][0]
    entry = best[1]    if best else None
    correction = _correction_for(members)

    # Classified here rather than filtered here: the admin console shows every
    # group and filters client-side, so a correctly-resolved game stays findable.
    if entry is None:
        status = 'unresolved'
    elif _is_suspect(game.name, entry.name or '') and not correction:
        status = 'suspect'
    else:
        status = 'resolved'

    # Newest appearance — the episode a reviewer would open to judge the match.
    newest = max(members, key=lambda m: m[1].episode.pub_ts or 0)[1].episode
    return {
        'status':       status,
        'corrected':    correction is not None,
        'displayName':  (correction or {}).get('display_name'),
        'slug':         slug,
        'name':         game.name,
        'nameSlug':     game.name_slug,
        'nameSlugs':    sorted({g.name_slug for g, _ in members}),
        'igdbName':     entry.name      if entry else None,
        'igdbSlug':     entry.igdb_slug if entry else None,
        'coverImageId': (entry.data or {}).get('coverImageId') if entry else None,
        'released':     (entry.data or {}).get('released') if entry else None,
        'podcasts':     sorted({a.episode.podcast_id for _, a in members if a.episode.podcast_id}),
        'episodeCount': len({a.episode.slug for _, a in members}),
        'latestPubTs':  newest.pub_ts,
        'episodeSlug':  newest.url_slug or newest.slug,
        'episodeTitle': newest.title,
    }


@games_bp.route('/resolution-stats')
def resolution_stats():
    require_admin()
    groups, cache = _group_members()
    fresh = _fresh_slugs(cache.items())

    # Per-podcast tallies are counted over appearances (an appearance belongs to
    # exactly one podcast), while the lists below are per catalog entry.
    per_podcast = {
        p.id: {'id': p.id, 'label': p.label, 'name': p.name,
               'appearances': 0, 'resolved': 0, 'failed': 0,
               'pending': 0, 'corrected': 0}
        for p in PODCASTS
    }
    rows = []

    for slug, members in groups.items():
        best = _best_member(members, cache)

        for game, appearance in members:
            stats = per_podcast.get(appearance.episode.podcast_id)
            if stats is None:
                continue
            stats['appearances'] += 1
            cached = cache.get(appearance.podcast_slug)
            if cached is not None:
                # A cached row with no igdb_id is a negative cache: IGDB was asked
                # and had nothing. Never-cached rows are neither — only pending.
                stats['failed' if cached.igdb_id is None else 'resolved'] += 1
            if _appearance_pending(game, appearance, cache, fresh):
                stats['pending'] += 1
            if find_by_podcast(game.name, appearance.episode.pub_ts,
                               appearance.episode.podcast_id):
                stats['corrected'] += 1

        rows.append(_group_summary(slug, members, best))

    # Every group, classified by `status` rather than split into fixed lists: the
    # console filters client-side, so a correctly-resolved game stays searchable
    # (the old suspects/unresolved split made ~1500 games unreachable). Newest
    # first — the default review order.
    rows.sort(key=lambda r: r['latestPubTs'] or 0, reverse=True)

    return jsonify({
        'podcasts':  list(per_podcast.values()),
        'games':     rows,
        # False in prod: corrections.json ships in the read-only image layer, so
        # curation happens in dev and lands in git. Drives the UI's read-only state.
        'writable':  corrections.is_writable(),
        'pending':   _count_pending(),
        'resolving': bool(_resolve_thread and _resolve_thread.is_alive()),
    })


@games_bp.route('/igdb-search')
def igdb_search():
    require_admin()
    query = (request.args.get('q') or '').strip()
    if not query:
        abort(400, 'q parameter is required')
    try:
        results = search_games(query)
    except Exception as exc:
        logger.warning('IGDB search failed q=%r: %s', query, exc)
        abort(502, f'IGDB search failed: {exc}')
    return jsonify({'results': results})


def _correction_target(payload: dict) -> tuple[PodcastGame, str, list[Member]]:
    """Validate a correction request → (game, podcast_id, affected appearances).

    podcast_id '' scopes the correction to every podcast. Validated against the
    live catalog, so a name that no longer exists in the feed can't be written —
    the failure mode a hand-edited corrections.json has (see `unmatched_slugs`)."""
    name_slug  = (payload.get('nameSlug') or '').strip()
    podcast_id = (payload.get('podcastId') or '').strip()
    if not name_slug:
        abort(400, 'nameSlug is required')
    if podcast_id and podcast_id not in PODCAST_BY_ID:
        abort(400, f'Unknown podcastId: {podcast_id}')
    with _state_lock:
        game = _game_index.get(name_slug)
    if game is None:
        abort(404, 'Game not found')
    members = [(game, a) for a in game.appearances
               if not podcast_id or a.episode.podcast_id == podcast_id]
    if not members:
        abort(404, 'No appearances for that podcast')
    return game, podcast_id, members


def _require_writable():
    if not corrections.is_writable():
        abort(409, 'corrections.json is read-only in this deployment. Curate it in '
                   'dev, where the repo is bind-mounted, then commit and deploy.')


def _bump_version() -> None:
    """Invalidate the derived response caches without touching the IGDB cache."""
    global _data_version
    with _state_lock:
        _data_version += 1


def _reresolve(members: list[Member], name_slug: str) -> dict:
    """Purge + re-resolve synchronously so the response reflects the edited file."""
    _purge_cache([a.podcast_slug for _, a in members])
    _resolve_members(members)
    _, cache = _group_members()
    best = _best_member(members, cache)
    return _load_game(best[1].igdb_slug if best and best[1].igdb_slug else name_slug)


def _settled(members: list[Member], name_slug: str) -> dict:
    """The group's detail as it stands, without re-resolving."""
    _, cache = _group_members()
    best = _best_member(members, cache)
    return _load_game(best[1].igdb_slug if best and best[1].igdb_slug else name_slug)


@games_bp.route('/corrections', methods=['PUT'])
@limiter.limit("30 per minute")
def set_correction():
    require_admin()
    _require_writable()
    payload = request.get_json(silent=True) or {}
    game, podcast_id, members = _correction_target(payload)

    igdb_id = payload.get('igdbId')
    if igdb_id is not None:
        try:
            igdb_id = int(igdb_id)
        except (TypeError, ValueError):
            abort(400, 'igdbId must be an integer')
    # Absent = leave the display name alone; '' = drop the override.
    display_name = payload.get('displayName', corrections._UNSET)
    if igdb_id is None and display_name is corrections._UNSET:
        abort(400, 'pass igdbId and/or displayName')

    # Keyed on the feed's own wording, which is what corrections.json matches on.
    corrections.upsert(game.name, podcast_id, igdb_id=igdb_id, display_name=display_name)

    if igdb_id is None:
        # A rename doesn't change which IGDB game this is — display_name is applied
        # at response time by _group_display_name. Re-resolving would burn a round
        # of IGDB + Metacritic + HLTB calls to arrive at the same entry.
        _bump_version()
        return jsonify(_settled(members, game.name_slug))
    return jsonify(_reresolve(members, game.name_slug))


@games_bp.route('/corrections', methods=['DELETE'])
@limiter.limit("30 per minute")
def delete_correction():
    require_admin()
    _require_writable()
    payload = request.get_json(silent=True) or {}
    game, podcast_id, members = _correction_target(payload)
    if not corrections.remove(game.name, podcast_id):
        abort(404, 'No correction at that scope')
    return jsonify(_reresolve(members, game.name_slug))


@games_bp.route('/podcasts/<string:podcast_id>/igdb-refresh', methods=['POST'])
@limiter.limit("2 per minute")
def podcast_igdb_refresh(podcast_id):
    require_admin()
    if podcast_id not in PODCAST_BY_ID:
        abort(404, 'Unknown podcast')
    with _state_lock:
        podcast_slugs = [a.podcast_slug for game in _game_index.values()
                         for a in game.appearances
                         if a.episode.podcast_id == podcast_id]
    _purge_cache(podcast_slugs)
    # Background sweep (this can be hundreds of rate-limited IGDB calls); the
    # client watches /resolution-stream for progress.
    _schedule_resolve(force=True)
    return jsonify({'purged': len(podcast_slugs)})


@games_bp.route('/<string:slug>')
def game_detail(slug):
    return jsonify(_load_game(slug))


def _purge_cache(podcast_slugs: list[str]) -> None:
    """Drop these cache keys from memory and DB so they re-resolve from scratch."""
    global _data_version
    if not podcast_slugs:
        return
    with _state_lock:
        for ps in podcast_slugs:
            _igdb_cache.pop(ps, None)
        _data_version += 1
    with get_db() as conn:
        ph = ','.join('?' * len(podcast_slugs))
        conn.execute(f'DELETE FROM igdb_cache WHERE slug IN ({ph})', podcast_slugs)


def _resolve_members(members: list[Member]) -> None:
    for game, appearance in members:
        _resolve_one(appearance.podcast_slug, game.name,
                     appearance.episode.pub_ts, appearance.episode.podcast_id)


@games_bp.route('/<string:slug>/igdb-refresh', methods=['POST'])
@limiter.limit("10 per minute")
def game_igdb_refresh(slug):
    # Collect this entry's appearances (by igdb_slug, or the name_slug fallback)
    members, _, _ = _match_appearances(slug)
    _purge_cache([a.podcast_slug for _, a in members])
    _resolve_members(members)

    # Re-resolution may have moved the entry to a different igdb_slug
    _, cache = _group_members()
    best     = _best_member(members, cache)
    new_slug = best[1].igdb_slug if best else make_slug(slug)

    return jsonify(_load_game(new_slug))
