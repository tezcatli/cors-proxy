"""
IGDB API client.
Public API: fetch_by_id, fetch_by_name, IgdbResult.
"""

import re
import time
import threading
import datetime
from collections import namedtuple

import requests
from config import Config
from utils import norm_key

import logging

logger = logging.getLogger(__name__)

IgdbResult = namedtuple('IgdbResult', ['id', 'name', 'slug', 'data', 'is_child'])

_IGDB_BASE = 'https://api.igdb.com/v4'
_TWITCH    = 'https://id.twitch.tv/oauth2/token'
# ESRB labels keyed by the legacy age_ratings.rating enum…
_ESRB      = {6: 'RP', 7: 'EC', 8: 'E', 9: 'E10+', 10: 'T', 11: 'M', 12: 'AO'}
# …and by the new age_ratings.rating_category ids (organization 1 = ESRB).
_ESRB_NEW  = {1: 'RP', 2: 'EC', 3: 'E', 4: 'E10+', 5: 'T', 6: 'M', 7: 'AO'}
_session   = requests.Session()


# ── HTTP retry (transient upstream failures) ──────────────────────────────────

_MAX_TRIES       = 3
_RETRY_STATUSES  = {429, 500, 502, 503, 504}


def _with_retry(do_request):
    """Call `do_request` (returns a Response); retry on connection errors and
    429/5xx with exponential backoff. Returns the Response (raise_for_status'd)."""
    last_exc = None
    for attempt in range(_MAX_TRIES):
        try:
            resp = do_request()
        except requests.RequestException as exc:
            last_exc = exc
        else:
            if resp.status_code not in _RETRY_STATUSES:
                resp.raise_for_status()
                return resp
            last_exc = requests.HTTPError(f'HTTP {resp.status_code} from upstream')
        if attempt < _MAX_TRIES - 1:
            time.sleep(0.5 * (2 ** attempt))   # 0.5s, 1s
    raise last_exc or RuntimeError('IGDB request failed')


# ── OAuth token ───────────────────────────────────────────────────────────────

_token_lock    = threading.Lock()
_token: str | None = None
_token_expires = 0.0


def _get_token() -> str:
    global _token, _token_expires
    with _token_lock:
        if _token and time.monotonic() < _token_expires:
            return _token
        resp = _with_retry(lambda: _session.post(_TWITCH, params={
            'client_id':     Config.IGDB_CLIENT_ID,
            'client_secret': Config.IGDB_CLIENT_SECRET,
            'grant_type':    'client_credentials',
        }, timeout=10))
        body           = resp.json()
        _token         = body['access_token']
        # Subtract 5 minutes so we refresh before the token actually expires
        _token_expires = time.monotonic() + body['expires_in'] - 300
        return _token


# ── Rate limiter ──────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self, rate: float):
        self._interval = 1.0 / rate
        self._last     = 0.0
        self._lock     = threading.Lock()

    def wait(self):
        with self._lock:
            now  = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


_rate_limiter = _RateLimiter(4)


# ── Platform brand family ─────────────────────────────────────────────────────

def _platform_family(name: str) -> str | None:
    """Brand-family key the frontend maps to a monochrome platform icon.
    Covers a whole brand (every PlayStation/Xbox/Nintendo generation) so the
    distinct platform labels still share one recognisable glyph. None → generic."""
    n = name.lower()
    if 'playstation' in n:                                    return 'playstation'
    if 'xbox' in n:                                           return 'xbox'
    if any(k in n for k in ('switch', 'nintendo', 'wii',
                            'game boy', 'gamecube')):          return 'nintendo'
    if 'windows' in n or 'linux' in n or 'steam' in n \
            or re.search(r'\bpc\b', n):                       return 'pc'
    if any(k in n for k in ('mac', 'ios', 'iphone', 'ipad', 'apple')): return 'apple'
    if 'android' in n:                                        return 'android'
    return None


# ── IGDB POST ─────────────────────────────────────────────────────────────────

def _post(body: str, endpoint: str = 'games') -> list[dict]:
    token = _get_token()
    logger.debug('IGDB query (%s): %s', endpoint, body.strip())

    def do():
        _rate_limiter.wait()   # honor the 4 req/s budget on every attempt
        return _session.post(
            f'{_IGDB_BASE}/{endpoint}',
            headers={
                'Client-ID':     Config.IGDB_CLIENT_ID,
                'Authorization': f'Bearer {token}',
                'Content-Type':  'text/plain',
            },
            data=body,
            timeout=Config.REQUEST_TIMEOUT,
        )

    return _with_retry(do).json()


# ── Subtitle stripping ────────────────────────────────────────────────────────

_SUBTITLE_RE = re.compile(r'\s*[:\-–].+$')

def _strip_subtitle(name: str) -> str:
    return _SUBTITLE_RE.sub('', name).strip()


# ── Result ranking ────────────────────────────────────────────────────────────

def _rank_results(results: list[dict], query: str) -> list[dict]:
    """Sort results by how closely they match query; best match first."""
    q    = norm_key(query)
    base = norm_key(_strip_subtitle(query))

    def score(game: dict) -> int:
        name = norm_key(game.get('name', ''))
        if name == q:                                   return 4
        if name == base:                                return 3
        if name.startswith(q) or q.startswith(name):   return 2
        if name.startswith(base) or base.startswith(name): return 1
        return 0

    return sorted(results, key=score, reverse=True)


# ── Normalise IGDB result → frontend shape ────────────────────────────────────

def _to_game_data(game: dict) -> dict:
    cover_image_id = (game.get('cover') or {}).get('image_id')

    screenshots    = game.get('screenshots') or []
    screenshot_ids = [s['image_id'] for s in screenshots if s.get('image_id')]
    bg_image_id    = screenshot_ids[0] if screenshot_ids else None

    metacritic = None
    if game.get('aggregated_rating') and game.get('aggregated_rating_count', 0) >= 3:
        metacritic = round(game['aggregated_rating'])

    rating = round(game['rating'] / 20, 1) if game.get('rating') else None

    released = None
    if game.get('first_release_date'):
        released = str(datetime.datetime.fromtimestamp(
            game['first_release_date'], datetime.timezone.utc).year)

    genres    = [x['name'] for x in (game.get('genres') or [])][:3]

    # One chip per platform/generation: the short IGDB abbreviation as label, plus a
    # brand-family key the frontend turns into a monochrome icon (None → generic).
    platforms = []
    _seen_labels = set()
    for p in (game.get('platforms') or []):
        name  = p.get('name', '')
        label = p.get('abbreviation') or name
        if not label or label in _seen_labels:
            continue
        _seen_labels.add(label)
        platforms.append({'label': label, 'family': _platform_family(name)})
    platforms = platforms[:6]

    esrb = None
    for age_rating in (game.get('age_ratings') or []):
        # New schema: organization 1 = ESRB, rating_category id → label.
        if age_rating.get('organization') == 1:
            esrb = _ESRB_NEW.get(age_rating.get('rating_category'))
        # Legacy schema: category 1 = ESRB, rating enum → label.
        elif age_rating.get('category') == 1:
            esrb = _ESRB.get(age_rating.get('rating'))
        if esrb:
            break

    raw_desc    = (game.get('summary') or '').strip()
    description = raw_desc[:500] if raw_desc else None

    developer = publisher = None
    for company_role in (game.get('involved_companies') or []):
        company = company_role.get('company')
        if not company:
            continue
        company_name = company.get('name')
        if company_role.get('developer') and not developer:
            developer = company_name
        if company_role.get('publisher') and not publisher:
            publisher = company_name

    modes        = [m['name'] for m in (game.get('game_modes') or [])][:3]
    themes       = [t['name'] for t in (game.get('themes') or [])][:4]
    perspectives = [p['name'] for p in (game.get('player_perspectives') or [])][:3]
    franchise    = ((game.get('collection') or {}).get('name')
                    or next((f['name'] for f in (game.get('franchises') or []) if f.get('name')), None))
    storyline    = (game.get('storyline') or '').strip() or None
    artwork_ids  = [a['image_id'] for a in (game.get('artworks') or []) if a.get('image_id')]

    # Trailer: prefer a video whose name reads like a trailer, else the first video.
    videos  = game.get('videos') or []
    trailer = next((v for v in videos if v.get('video_id')
                    and any(k in (v.get('name') or '').lower() for k in ('trailer', 'bande'))), None) \
              or next((v for v in videos if v.get('video_id')), None)
    trailer_id = trailer.get('video_id') if trailer else None

    # Websites — category/type ids: 1 official, 3 wikipedia, 13 steam.
    steam_url = official_url = wiki_url = None
    for website in (game.get('websites') or []):
        cat = website.get('type') if website.get('type') is not None else website.get('category')
        url = website.get('url')
        if not url:
            continue
        if   cat == 13 and not steam_url:    steam_url    = url
        elif cat == 1  and not official_url: official_url = url
        elif cat == 3  and not wiki_url:     wiki_url     = url

    return dict(
        coverImageId=cover_image_id,
        bgImageId=bg_image_id,
        screenshotIds=screenshot_ids,
        artworkIds=artwork_ids,
        trailerId=trailer_id,
        metacritic=metacritic,
        rating=rating,
        genres=genres,
        released=released,
        platforms=platforms,
        esrb=esrb,
        description=description,
        storyline=storyline,
        developer=developer,
        publisher=publisher,
        modes=modes,
        themes=themes,
        perspectives=perspectives,
        franchise=franchise,
        steamUrl=steam_url,
        officialUrl=official_url,
        wikiUrl=wiki_url,
    )


# ── Canonical game selection ──────────────────────────────────────────────────

def _resolve_canonical(game: dict) -> dict:
    """Return version_parent > parent_game (unless remake/remaster) > self.

    Categories 8 (remake) and 9 (remaster) are intentional standalone titles,
    so we don't redirect them to their parent game.
    """
    category = game.get('category') if game.get('category') is not None \
               else (game.get('game_type') or {}).get('id', 0)

    version_parent = game.get('version_parent')
    if isinstance(version_parent, dict) and version_parent.get('id'):
        return version_parent

    if category not in (8, 9):
        parent_game = game.get('parent_game')
        if isinstance(parent_game, dict) and parent_game.get('id'):
            return parent_game

    return game


def _build_result(game: dict, canonical: bool = True) -> IgdbResult:
    # `canonical=False` builds the fetched game verbatim, skipping the
    # parent/version redirect — used when a human correction pins an exact
    # igdb_id and that choice must not be overridden (e.g. IGDB modelling a
    # standalone remake as a "port" of an earlier version).
    target = _resolve_canonical(game) if canonical else game
    return IgdbResult(
        id=target['id'],
        name=target['name'],
        slug=target.get('slug'),
        data=_to_game_data(target),
        is_child=(target is not game),
    )


# ── Query helpers ─────────────────────────────────────────────────────────────

# The fields fetched for one game. The parent_game/version_parent expansions
# request the SAME set inline (plus their own id) so canonical resolution never
# needs a second API call — generated from one base list instead of by hand.
_GAME_FIELDS = (
    'name, slug, category, game_type.id, '
    'aggregated_rating, aggregated_rating_count, rating, first_release_date, summary, '
    'genres.name, platforms.name, cover.image_id, screenshots.image_id, '
    'age_ratings.category, age_ratings.rating, age_ratings.organization, age_ratings.rating_category, '
    'involved_companies.developer, involved_companies.publisher, involved_companies.company.name, '
    'game_modes.name, websites.category, websites.type, websites.url, '
    'videos.video_id, videos.name, artworks.image_id, themes.name, '
    'player_perspectives.name, collection.name, franchises.name, storyline, '
    'platforms.abbreviation'
)


def _prefixed(prefix: str) -> str:
    # nested objects must request `id` explicitly to be expandable
    return ', '.join([f'{prefix}.id'] + [f'{prefix}.{f.strip()}' for f in _GAME_FIELDS.split(',')])


_FIELDS = 'fields ' + ', '.join(
    [_GAME_FIELDS] + [_prefixed(p) for p in ('parent_game', 'version_parent')]
) + '; '


def _release_window(pub_ts: int) -> tuple[int, int]:
    """Return a (lo, hi) timestamp window around a podcast episode's publication date."""
    lo = pub_ts - 365 * 24 * 3600   # 1 year before episode
    hi = pub_ts + 180 * 24 * 3600   # 6 months after episode
    return lo, hi


def _name_filter(safe: str, safe_base: str | None = None) -> str:
    parts = [f'name ~ "{safe}"', f'name ~ *"{safe}"*']
    if safe_base:
        parts += [f'name ~ "{safe_base}"', f'name ~ *"{safe_base}"*']
    return '(' + ' | '.join(parts) + ')'


def _search_candidates(safe: str, safe_base: str | None, pub_ts: int | None) -> list[dict]:
    """Two-pass IGDB search: text search first, regex fallback second."""
    type_filter = 'game_type != 5'
    if pub_ts:
        lo, hi      = _release_window(pub_ts)
        date_filter = f'& first_release_date >= {lo} & first_release_date <= {hi}'
    else:
        date_filter = ''

    results = _post(f'{_FIELDS}search "{safe}"; where {type_filter} {date_filter};limit 10;')
    if not results:
        results = _post(f'{_FIELDS}where {type_filter} & {_name_filter(safe, safe_base)}{date_filter}; limit 10;')
    return results


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_by_id(igdb_id: int, canonical: bool = True) -> IgdbResult | None:
    """Direct lookup by IGDB id. Returns IgdbResult or None. Raises RequestException on failure.

    `canonical=False` returns the exact id without parent/version redirection — for
    correction-pinned ids a curator chose deliberately."""
    results = _post(f'{_FIELDS}where id = {int(igdb_id)}; limit 1;')
    if not results:
        return None
    return _build_result(results[0], canonical=canonical)


def fetch_by_name(name: str, pub_ts: int | None = None) -> IgdbResult | None:
    """Name search with optional publication-date hint. Returns IgdbResult or None."""
    safe      = name.replace('\\', '').replace('"', '')
    base_name = _strip_subtitle(name)
    safe_base = base_name.replace('\\', '').replace('"', '') if base_name != name else None

    results = _search_candidates(safe, safe_base, pub_ts)
    if not results and pub_ts:
        # Retry without date constraint in case the release date is outside the window
        results = _search_candidates(safe, safe_base, None)
    if not results:
        return None

    if pub_ts:
        lo, hi      = _release_window(pub_ts)
        in_window   = [g for g in results if lo <= (g.get('first_release_date') or 0) <= hi]
        if in_window:
            results = in_window

    return _build_result(_rank_results(results, name)[0])


def fetch_time_to_beat(igdb_id: int) -> int | None:
    """Main-story completion time in hours from IGDB's /game_time_to_beats, or None.
    Best-effort fallback for HowLongToBeat; never raises."""
    try:
        rows = _post(f'fields normally; where game_id = {int(igdb_id)}; limit 1;',
                     endpoint='game_time_to_beats')
    except Exception as exc:
        logger.warning('IGDB time-to-beat failed id=%s: %s', igdb_id, exc)
        return None
    secs = rows[0].get('normally') if rows else None
    return round(secs / 3600) if secs else None
