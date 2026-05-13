import json
import datetime
import threading

import requests as http
from flask import Blueprint, abort, jsonify, request

from auth import require_auth
from config import Config
from corrections import find_by_podcast
from db import get_db, utcnow
from igdb import fetch_by_id, fetch_by_name
from models import Episode, GameAppearance, IgdbEntry, PodcastGame
from rss import parse_feed
from utils import make_slug

import logging

logger = logging.getLogger(__name__)

games_bp = Blueprint('games', __name__, url_prefix='/games')
games_bp.before_request(require_auth)

_RSS_URL = 'https://feeds.acast.com/public/shows/silence-on-joue'


# ── In-memory state ───────────────────────────────────────────────────────────
# All four structures are rebuilt from the RSS feed and/or DB at startup.
# HTTP requests read only from memory — no per-request DB queries.

_state_lock = threading.Lock()

_cached_episodes: list[Episode] = []           # source of truth; owns all Episode objects
_episode_index:   dict[str, Episode] = {}      # episode.slug → Episode (same objects)
_game_index:      dict[str, PodcastGame] = {}  # name_slug    → PodcastGame
_cached_at:       datetime.datetime | None = None

# Keyed by date-qualified podcast_slug (make_slug(name) + '-' + YYYYMMDD).
# Loaded from DB at startup; written when a new IGDB resolution completes.
_igdb_cache: dict[str, IgdbEntry] = {}


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

        date_str = (
            datetime.datetime.fromtimestamp(episode.pub_ts, datetime.timezone.utc)
            .strftime('%Y%m%d')
            if episode.pub_ts else 'nopubts'
        )

        for mention in episode.games:
            name_slug    = make_slug(mention.name)
            podcast_slug = f'{name_slug}-{date_str}'

            if name_slug not in game_index:
                game_index[name_slug] = PodcastGame(name_slug=name_slug, name=mention.name)
            else:
                existing = game_index[name_slug]
                # Keep the first-seen raw name but log if the same (name, date) appears twice
                if any(a.podcast_slug == podcast_slug for a in existing.appearances):
                    logger.info('Duplicate podcast_slug %r in episode %r, skipping', podcast_slug, episode.title)
                    continue

            game = game_index[name_slug]
            game.appearances.append(GameAppearance(
                episode=episode,
                mention=mention,
                podcast_slug=podcast_slug,
            ))
            if episode.pub_ts and episode.pub_ts > game.latest_pub_ts:
                game.latest_pub_ts = episode.pub_ts
            game.episode_count += 1

    return episode_index, game_index


def _refresh_feed() -> None:
    global _cached_episodes, _episode_index, _game_index, _cached_at
    resp = http.get(_RSS_URL, timeout=Config.REQUEST_TIMEOUT,
                    headers={'User-Agent': 'SilenceOnJoue/1.0'})
    resp.raise_for_status()
    episodes                        = parse_feed(resp.content)
    episode_index, game_index       = _build_indexes(episodes)
    with _state_lock:
        _cached_episodes = episodes
        _episode_index   = episode_index
        _game_index      = game_index
        _cached_at       = utcnow()


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


# ── IGDB resolution ───────────────────────────────────────────────────────────

def _resolve_one(podcast_slug: str, name: str, pub_ts: int | None) -> None:
    logger.info('Resolving IGDB for slug=%r name=%r', podcast_slug, name)
    correction = find_by_podcast(name, pub_ts)
    try:
        if correction and correction.get('igdb_id'):
            result = fetch_by_id(correction['igdb_id'])
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

    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO igdb_cache '
            '(slug, igdb_id, igdb_slug, name, igdb_data, is_child, cached_at) VALUES (?,?,?,?,?,?,?)',
            (podcast_slug, entry.igdb_id, entry.igdb_slug, entry.name,
             json.dumps(entry.data) if entry.data else None,
             int(entry.is_child), now)
        )


_resolve_lock   = threading.Lock()
_resolve_thread: threading.Thread | None = None
_resolve_stop:   threading.Event  | None = None


def _resolve_pending(stop: threading.Event) -> None:
    try:
        with _state_lock:
            games = dict(_game_index)
        if not games:
            return

        ttl_cutoff = (
            utcnow() - datetime.timedelta(hours=Config.IGDB_TTL_HOURS)
        ).isoformat()
        fresh_slugs = {
            slug for slug, entry in _igdb_cache.items()
            if entry.cached_at > ttl_cutoff
        }

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


# ── Startup ───────────────────────────────────────────────────────────────────

def _startup() -> None:
    _load_igdb_cache_from_db()
    if _feed_is_stale():
        try:
            _refresh_feed()
        except Exception as exc:
            logger.warning('Startup RSS fetch failed: %s', exc)
    _schedule_resolve()


def startup_warmup() -> None:
    threading.Thread(target=_startup, daemon=True).start()


# ── Response serialisation ────────────────────────────────────────────────────

def _serialise_appearance(appearance: GameAppearance) -> dict:
    ep = appearance.episode
    return {
        'title':            ep.title,
        'slug':             ep.slug,
        'audioUrl':         ep.audio_url,
        'pubTs':            ep.pub_ts,
        'imageUrl':         ep.image_url,
        'description':      ep.description,
        'chapters':         [{'timestamp': c.timestamp, 'timestampSeconds': c.timestamp_seconds,
                              'title': c.title} for c in ep.chapters],
        'timestamp':        appearance.mention.timestamp,
        'timestampSeconds': appearance.mention.timestamp_seconds,
    }


def _build_resolved(episode: Episode) -> dict[str, tuple[str, str, str | None]]:
    """Build a timestamp → (igdb_name, igdb_slug, cover_image_id) map for one episode."""
    date_str = (
        datetime.datetime.fromtimestamp(episode.pub_ts, datetime.timezone.utc).strftime('%Y%m%d')
        if episode.pub_ts else 'nopubts'
    )
    resolved: dict[str, tuple[str, str, str | None]] = {}
    for mention in episode.games:
        podcast_slug = f'{make_slug(mention.name)}-{date_str}'
        entry        = _igdb_cache.get(podcast_slug)
        if entry and entry.igdb_slug and mention.timestamp:
            cover_image_id = entry.data.get('coverImageId') if entry.data else None
            resolved[mention.timestamp] = (entry.name or mention.name, entry.igdb_slug, cover_image_id)
    return resolved


def _serialise_episode(episode: Episode, resolved: dict[str, tuple[str, str, str | None]] | None = None) -> dict:
    """Serialise an Episode to a JSON-ready dict.

    resolved maps timestamp_str → (igdb_name, igdb_slug, cover_image_id) for chapter annotation.
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
        entry: dict = {'name': g.name, 'timestamp': g.timestamp, 'tsSeconds': g.timestamp_seconds}
        if resolved and g.timestamp and g.timestamp in resolved:
            entry['slug'] = resolved[g.timestamp][1]
        games.append(entry)

    return {
        'title':       episode.title,
        'slug':        episode.slug,
        'audioUrl':    episode.audio_url,
        'pubTs':       episode.pub_ts,
        'imageUrl':    episode.image_url,
        'description': episode.description,
        'chapters':    chapters,
        'games':       games,
    }


# ── Catalog building ──────────────────────────────────────────────────────────

def _build_catalog() -> list[dict]:
    with _state_lock:
        games = dict(_game_index)

    groups: dict[str, list[PodcastGame]] = {}
    for game in games.values():
        entry = _best_igdb_entry(game)
        slug  = entry.igdb_slug if entry else game.name_slug
        groups.setdefault(slug, []).append(game)

    result = []
    for slug, matched_games in groups.items():
        primary = next(
            (g for g in matched_games
             if not (_best_igdb_entry(g) or IgdbEntry('', None, None, None, None, True, '')).is_child),
            matched_games[0],
        )
        entry     = _best_igdb_entry(primary)
        igdb_slim = {'metacritic': entry.data.get('metacritic')} if entry and entry.data else None
        result.append({
            'slug':         slug,
            'name':         _display_name(primary, entry),
            'igdb':         igdb_slim,
            'episodeCount': sum(g.episode_count for g in matched_games),
            'latestPubTs':  max(g.latest_pub_ts for g in matched_games),
        })

    return sorted(result, key=lambda g: g['name'].lower())


def _display_name(game: PodcastGame, entry: IgdbEntry | None) -> str:
    """Resolve the display name: corrections override > IGDB canonical > raw podcast name."""
    if entry and not entry.is_child:
        # Check if a correction provides a display_name override
        first_pub_ts = game.appearances[0].episode.pub_ts if game.appearances else None
        corr         = find_by_podcast(game.name, first_pub_ts)
        if corr and corr.get('display_name'):
            return corr['display_name']
        if entry.name:
            return entry.name
    elif entry and entry.is_child and entry.name:
        return entry.name
    return game.name


def _load_game(slug: str) -> tuple[dict, list[dict]]:
    """Return (game_info dict, episodes list) for a given igdb_slug or name_slug."""
    with _state_lock:
        games = dict(_game_index)

    # Try to find all podcast games whose best entry matches this igdb_slug
    matched_games = [
        game for game in games.values()
        if (entry := _best_igdb_entry(game)) and entry.igdb_slug == slug
    ]

    if matched_games:
        episodes = [_serialise_appearance(a) for game in matched_games for a in game.appearances]
        # Use the non-child game for the display name if available
        primary = next((g for g in matched_games
                        if not (_best_igdb_entry(g) or IgdbEntry('', None, None, None, None, True, '')).is_child),
                       matched_games[0])
        entry   = _best_igdb_entry(primary)
        return {
            'display_name': _display_name(primary, entry),
            'slug':         slug,
            'igdb_data':    json.dumps(entry.data) if entry and entry.data else None,
        }, episodes

    # Fall back to name_slug match
    name_slug = make_slug(slug)
    if name_slug in games:
        game     = games[name_slug]
        episodes = [_serialise_appearance(a) for a in game.appearances]
        return {
            'display_name': game.name,
            'slug':         name_slug,
            'igdb_data':    None,
        }, episodes

    abort(404, 'Game not found')


# ── Endpoints ─────────────────────────────────────────────────────────────────

@games_bp.route('/episodes')
def games_episodes():
    with _state_lock:
        episodes = list(_cached_episodes)
    return jsonify([_serialise_episode(ep, _build_resolved(ep)) for ep in episodes])


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
        except http.exceptions.RequestException as exc:
            if not _cached_episodes:
                abort(502, f'RSS feed unavailable: {exc}')
        else:
            _schedule_resolve()
    return jsonify(_build_catalog())


@games_bp.route('/igdb')
def games_igdb():
    slugs = request.args.getlist('slug')
    if not slugs:
        return jsonify({})
    slug_set = set(slugs)
    result   = {}
    with _state_lock:
        for entry in _igdb_cache.values():
            if entry.igdb_slug in slug_set and entry.igdb_slug not in result and entry.data:
                result[entry.igdb_slug] = entry.data
    return jsonify(result)


@games_bp.route('/refresh', methods=['POST'])
def refresh():
    try:
        _refresh_feed()
        _schedule_resolve(force=True)
    except http.exceptions.RequestException as exc:
        abort(502, f'RSS feed unavailable: {exc}')
    return jsonify(_build_catalog())


@games_bp.route('/<string:slug>')
def game_detail(slug):
    game_row, episodes = _load_game(slug)
    return jsonify({
        'name':     game_row['display_name'],
        'slug':     game_row['slug'],
        'igdb':     json.loads(game_row['igdb_data']) if game_row['igdb_data'] else None,
        'episodes': episodes,
    })


@games_bp.route('/<string:slug>/igdb-refresh', methods=['POST'])
def game_igdb_refresh(slug):
    with _state_lock:
        games = dict(_game_index)

    # Collect all podcast_slugs for this igdb_slug (or name_slug fallback)
    matched_games = [
        game for game in games.values()
        if (entry := _best_igdb_entry(game)) and entry.igdb_slug == slug
    ]
    if not matched_games:
        name_slug = make_slug(slug)
        if name_slug in games:
            matched_games = [games[name_slug]]
        else:
            abort(404, 'Game not found')

    # Remove stale entries from memory and DB
    podcast_slugs = [a.podcast_slug for game in matched_games for a in game.appearances]
    with _state_lock:
        for ps in podcast_slugs:
            _igdb_cache.pop(ps, None)
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

    game_row, episodes = _load_game(new_slug)
    return jsonify({
        'name':     game_row['display_name'],
        'slug':     game_row['slug'],
        'igdb':     json.loads(game_row['igdb_data']) if game_row['igdb_data'] else None,
        'episodes': episodes,
    })
