import json
import datetime
import pathlib
import queue as _queue_mod
import threading

import requests as http
from flask import Blueprint, abort, jsonify, request, Response, stream_with_context

from auth import require_auth
from config import Config
from limiter import limiter
from corrections import find_by_podcast
from db import get_db, utcnow
from igdb import fetch_by_id, fetch_by_name
from models import Episode, GameAppearance, IgdbEntry, PodcastGame
from rss import parse_feed, is_game_catalog_excluded
from utils import make_slug

import logging

logger = logging.getLogger(__name__)

games_bp = Blueprint('games', __name__, url_prefix='/silence/games')
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
    from rss import find_chapter_for_game
    from models import Chapter as Ch
    injected = 0
    for episode in episodes:
        # chapters.json is keyed by make_slug(title); episode.slug is now the guid,
        # so match on the title slug here.
        title_slug = make_slug(episode.title)
        if episode.chapters or title_slug not in ai_index:
            continue
        raw_chapters = ai_index[title_slug]
        chapters = [
            Ch(
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


_feed_etag:          str | None = None
_feed_last_modified: str | None = None


def _refresh_feed() -> None:
    global _cached_episodes, _episode_index, _game_index, _cached_at
    global _feed_etag, _feed_last_modified

    headers = {'User-Agent': 'SilenceOnJoue/1.0'}
    if _feed_etag:          headers['If-None-Match']     = _feed_etag
    if _feed_last_modified: headers['If-Modified-Since']  = _feed_last_modified

    resp = http.get(_RSS_URL, timeout=Config.REQUEST_TIMEOUT, headers=headers)
    if resp.status_code == 304:
        logger.info('RSS feed unchanged (304); skipping re-parse')
        with _state_lock:
            _cached_at = utcnow()
        return
    resp.raise_for_status()
    _feed_etag          = resp.headers.get('ETag')
    _feed_last_modified = resp.headers.get('Last-Modified')
    episodes                        = parse_feed(resp.content)
    ai_index                        = _load_ai_chapter_index()
    _inject_ai_chapters(episodes, ai_index)
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


def _primary_and_entry(matched_games: list[PodcastGame]) -> tuple[PodcastGame, IgdbEntry | None]:
    """The representative game for a catalog group (a non-child if any) and its best entry."""
    primary = next(
        (g for g in matched_games if (e := _best_igdb_entry(g)) and not e.is_child),
        matched_games[0],
    )
    return primary, _best_igdb_entry(primary)


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
    """Cache keys resolved within the IGDB TTL window."""
    cutoff = (utcnow() - datetime.timedelta(hours=Config.IGDB_TTL_HOURS)).isoformat()
    return {slug for slug, entry in cache_items if entry.cached_at > cutoff}


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


def _count_unresolved() -> int:
    """Appearances never resolved (uncached) — typically the casualties of a
    transient upstream failure, which the periodic pass retries."""
    with _state_lock:
        return _count_appearances_not_in(set(_igdb_cache.keys()))


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
            pending = _count_unresolved()
            if pending:
                logger.info('Periodic re-resolve: %d unresolved appearance(s)', pending)
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
        'audioUrl':         episode.audio_url,
        'pubTs':            episode.pub_ts,
        'imageUrl':         episode.image_url,
        'description':      episode.description,
        'chapters':         chapters,
        'games':            games,
        'timestamp':        mention.timestamp        if mention else None,
        'timestampSeconds': mention.timestamp_seconds if mention else 0,
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
        primary, entry = _primary_and_entry(matched_games)
        igdb_slim = {
            'metacritic':   entry.data.get('metacritic'),
            'coverImageId': entry.data.get('coverImageId'),
        } if entry and entry.data else None
        # Count distinct episodes (by guid) — two name variants co-occurring in one
        # episode must not double-count it.
        episode_slugs = {a.episode.slug for g in matched_games for a in g.appearances}
        pub_tss       = [g.latest_pub_ts for g in matched_games if g.latest_pub_ts is not None]
        result.append({
            'slug':         slug,
            'name':         _display_name(primary, entry),
            'igdb':         igdb_slim,
            'episodeCount': len(episode_slugs),
            'latestPubTs':  max(pub_tss) if pub_tss else None,
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
        primary, entry = _primary_and_entry(matched_games)
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


# ── Pending count ─────────────────────────────────────────────────────────────

def _count_pending() -> int:
    """Count appearances the resolver still considers pending — never resolved OR
    resolved longer ago than IGDB_TTL_HOURS. Matches `_resolve_pending`'s notion
    of "pending" so a catalog with stale entries still opens the SSE stream and
    gets live updates."""
    with _state_lock:
        return _count_appearances_not_in(_fresh_slugs(_igdb_cache.items()))


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _conditional(resp):
    """Attach a content ETag + revalidation header and 304 when If-None-Match matches."""
    resp.headers['Cache-Control'] = 'no-cache'
    resp.add_etag()
    return resp.make_conditional(request)


@games_bp.route('/episodes')
def games_episodes():
    with _state_lock:
        episodes = list(_cached_episodes)
    return _conditional(jsonify([_serialise_episode(ep, _build_resolved(ep)) for ep in episodes]))


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
    return _conditional(jsonify({'games': _build_catalog(), 'pending': _count_pending()}))


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
    # If no thread is alive, nothing will broadcast 'done' — send it ourselves
    if not (_resolve_thread and _resolve_thread.is_alive()):
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
    game_row, episodes = _load_game(slug)
    return jsonify({
        'name':     game_row['display_name'],
        'slug':     game_row['slug'],
        'igdb':     json.loads(game_row['igdb_data']) if game_row['igdb_data'] else None,
        'episodes': episodes,
    })


@games_bp.route('/<string:slug>/igdb-refresh', methods=['POST'])
@limiter.limit("10 per minute")
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
