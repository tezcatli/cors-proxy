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
_ESRB      = {6: 'RP', 7: 'EC', 8: 'E', 9: 'E10+', 10: 'T', 11: 'M', 12: 'AO'}
_session   = requests.Session()


# ── OAuth token ───────────────────────────────────────────────────────────────

_token_lock    = threading.Lock()
_token: str | None = None
_token_expires = 0.0


def _get_token() -> str:
    global _token, _token_expires
    with _token_lock:
        if _token and time.monotonic() < _token_expires:
            return _token
        resp = _session.post(_TWITCH, params={
            'client_id':     Config.IGDB_CLIENT_ID,
            'client_secret': Config.IGDB_CLIENT_SECRET,
            'grant_type':    'client_credentials',
        }, timeout=10)
        resp.raise_for_status()
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


# ── Platform simplification ───────────────────────────────────────────────────

def _simplify_platform(name: str) -> str | None:
    n = name.lower()
    if 'playstation' in n:                        return 'PlayStation'
    if 'xbox' in n:                               return 'Xbox'
    if 'switch' in n or 'nintendo' in n:          return 'Switch'
    if 'windows' in n or re.search(r'\bpc\b', n): return 'PC'
    if 'mac' in n:                                return 'Mac'
    if 'ios' in n or 'iphone' in n:               return 'iOS'
    if 'android' in n:                            return 'Android'
    return None


# ── IGDB POST ─────────────────────────────────────────────────────────────────

def _post(body: str) -> list[dict]:
    _rate_limiter.wait()
    token = _get_token()
    logger.debug('IGDB query: %s', body.strip())
    resp = _session.post(
        f'{_IGDB_BASE}/games',
        headers={
            'Client-ID':     Config.IGDB_CLIENT_ID,
            'Authorization': f'Bearer {token}',
            'Content-Type':  'text/plain',
        },
        data=body,
        timeout=Config.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


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
    platforms = list(dict.fromkeys(filter(None,
        (_simplify_platform(p['name']) for p in (game.get('platforms') or []))
    )))[:4]

    esrb = None
    for age_rating in (game.get('age_ratings') or []):
        if age_rating.get('category') == 1:
            esrb = _ESRB.get(age_rating.get('rating'))
            break

    raw_desc    = (game.get('summary') or '').strip()
    description = raw_desc[:500] if raw_desc else None

    developer = publisher = None
    for company_role in (game.get('involved_companies') or []):
        if not company_role.get('company'):
            continue
        company_name = company_role['company'].get('name')
        if company_role.get('developer') and not developer:
            developer = company_name
        if company_role.get('publisher') and not publisher:
            publisher = company_name

    modes = [m['name'] for m in (game.get('game_modes') or [])][:3]

    steam_url = None
    for website in (game.get('websites') or []):
        if website.get('category') == 13 and website.get('url'):
            steam_url = website['url']
            break

    return dict(
        coverImageId=cover_image_id,
        bgImageId=bg_image_id,
        screenshotIds=screenshot_ids,
        metacritic=metacritic,
        rating=rating,
        genres=genres,
        released=released,
        platforms=platforms,
        esrb=esrb,
        description=description,
        developer=developer,
        publisher=publisher,
        modes=modes,
        steamUrl=steam_url,
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


def _build_result(game: dict) -> IgdbResult:
    canonical = _resolve_canonical(game)
    return IgdbResult(
        id=canonical['id'],
        name=canonical['name'],
        slug=canonical.get('slug'),
        data=_to_game_data(canonical),
        is_child=(canonical is not game),
    )


# ── Query helpers ─────────────────────────────────────────────────────────────

# All fields fetched for a game, including inline parent/version expansions
# so canonical resolution never needs a second API call.
_FIELDS = (
    'fields name, slug, category, game_type.id, '
    'aggregated_rating, aggregated_rating_count, rating, first_release_date, summary, '
    'genres.name, platforms.name, cover.image_id, screenshots.image_id, '
    'age_ratings.category, age_ratings.rating, '
    'involved_companies.developer, involved_companies.publisher, involved_companies.company.name, '
    'game_modes.name, websites.category, websites.url, '

    'parent_game.id, parent_game.name, parent_game.slug, parent_game.category, parent_game.game_type.id, '
    'parent_game.aggregated_rating, parent_game.aggregated_rating_count, parent_game.rating, '
    'parent_game.first_release_date, parent_game.summary, '
    'parent_game.genres.name, parent_game.platforms.name, parent_game.cover.image_id, '
    'parent_game.screenshots.image_id, parent_game.age_ratings.category, parent_game.age_ratings.rating, '
    'parent_game.involved_companies.developer, parent_game.involved_companies.publisher, '
    'parent_game.involved_companies.company.name, '
    'parent_game.game_modes.name, parent_game.websites.category, parent_game.websites.url, '

    'version_parent.id, version_parent.name, version_parent.slug, version_parent.category, version_parent.game_type.id, '
    'version_parent.aggregated_rating, version_parent.aggregated_rating_count, version_parent.rating, '
    'version_parent.first_release_date, version_parent.summary, '
    'version_parent.genres.name, version_parent.platforms.name, version_parent.cover.image_id, '
    'version_parent.screenshots.image_id, version_parent.age_ratings.category, version_parent.age_ratings.rating, '
    'version_parent.involved_companies.developer, version_parent.involved_companies.publisher, '
    'version_parent.involved_companies.company.name, '
    'version_parent.game_modes.name, version_parent.websites.category, version_parent.websites.url; '
)


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

def fetch_by_id(igdb_id: int) -> IgdbResult | None:
    """Direct lookup by IGDB id. Returns IgdbResult or None. Raises RequestException on failure."""
    results = _post(f'{_FIELDS}where id = {int(igdb_id)}; limit 1;')
    if not results:
        return None
    return _build_result(results[0])


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
