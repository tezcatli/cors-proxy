import re
import time
import threading
import datetime
from collections import namedtuple
import requests as http
from config import Config
from utils import norm_key as _norm_key

IgdbResult = namedtuple('IgdbResult', ['id', 'name', 'slug', 'parent_game_id', 'version_parent_id', 'category', 'data'])

_IGDB_BASE = 'https://api.igdb.com/v4'
_TWITCH    = 'https://id.twitch.tv/oauth2/token'
_ESRB      = {6: 'RP', 7: 'EC', 8: 'E', 9: 'E10+', 10: 'T', 11: 'M', 12: 'AO'}

# ── OAuth ─────────────────────────────────────────────────────────────────────
_token_lock    = threading.Lock()
_token         = None
_token_expires = 0.0


def _get_token():
    global _token, _token_expires
    with _token_lock:
        if _token and time.monotonic() < _token_expires:
            return _token
        r = http.post(_TWITCH, params={
            'client_id':     Config.IGDB_CLIENT_ID,
            'client_secret': Config.IGDB_CLIENT_SECRET,
            'grant_type':    'client_credentials',
        }, timeout=10)
        r.raise_for_status()
        data           = r.json()
        _token         = data['access_token']
        _token_expires = time.monotonic() + data['expires_in'] - 300
        return _token


# ── Rate limiter ──────────────────────────────────────────────────────────────
class _Throttle:
    def __init__(self, rate):
        self._interval = 1.0 / rate
        self._last     = 0.0
        self._lock     = threading.Lock()

    def acquire(self):
        with self._lock:
            wait = self._interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


_throttle = _Throttle(4)


# ── Platform simplification ───────────────────────────────────────────────────
def _platform(name):
    n = name.lower()
    if 'playstation' in n:                   return 'PlayStation'
    if 'xbox' in n:                          return 'Xbox'
    if 'switch' in n or 'nintendo' in n:     return 'Switch'
    if 'windows' in n or re.search(r'\bpc\b', n): return 'PC'
    if 'mac' in n:                           return 'Mac'
    if 'ios' in n or 'iphone' in n:          return 'iOS'
    if 'android' in n:                       return 'Android'
    return None


# ── IGDB POST ─────────────────────────────────────────────────────────────────
def _igdb(query):
    _throttle.acquire()
    token = _get_token()
    r = http.post(
        f'{_IGDB_BASE}/games',
        headers={
            'Client-ID':     Config.IGDB_CLIENT_ID,
            'Authorization': f'Bearer {token}',
            'Content-Type':  'text/plain',
        },
        data=query,
        timeout=Config.REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Ranking ───────────────────────────────────────────────────────────────────
def _rank(results, name):
    q    = _norm_key(name)
    base = _norm_key(re.sub(r'\s*[:\-–].+$', '', name).strip())

    def _score(g):
        n = _norm_key(g.get('name', ''))
        if n == q:                               return 4
        if n == base:                            return 3
        if n.startswith(q) or q.startswith(n):  return 2
        if n.startswith(base) or base.startswith(n): return 1
        return 0

    return sorted(results, key=_score, reverse=True)


# ── Normalize IGDB result → frontend shape ────────────────────────────────────
def _normalize(g):
    cover_image_id = g['cover']['image_id'] if g.get('cover') and g['cover'].get('image_id') else None

    shots          = g.get('screenshots') or []
    screenshot_ids = [s['image_id'] for s in shots if s.get('image_id')]
    bg_image_id    = screenshot_ids[0] if screenshot_ids else None

    metacritic = None
    if g.get('aggregated_rating') and g.get('aggregated_rating_count', 0) >= 3:
        metacritic = round(g['aggregated_rating'])

    rating = round(g['rating'] / 20, 1) if g.get('rating') else None

    released = None
    if g.get('first_release_date'):
        released = str(datetime.datetime.fromtimestamp(
            g['first_release_date'], datetime.timezone.utc).year)

    genres    = [x['name'] for x in (g.get('genres') or [])][:3]
    platforms = list(dict.fromkeys(filter(None,
        (_platform(p['name']) for p in (g.get('platforms') or []))
    )))[:4]

    esrb = None
    for ar in (g.get('age_ratings') or []):
        if ar.get('category') == 1:
            esrb = _ESRB.get(ar.get('rating'))
            break

    raw_desc    = (g.get('summary') or '').strip()
    description = raw_desc[:500] if raw_desc else None

    developer = publisher = None
    for ic in (g.get('involved_companies') or []):
        if not ic.get('company'):
            continue
        name = ic['company'].get('name')
        if ic.get('developer') and not developer:
            developer = name
        if ic.get('publisher') and not publisher:
            publisher = name

    modes = [m['name'] for m in (g.get('game_modes') or [])][:3]

    steam_url = None
    for w in (g.get('websites') or []):
        if w.get('category') == 13 and w.get('url'):
            steam_url = w['url']
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


# ── Shared fields string ──────────────────────────────────────────────────────
_FIELDS = (
    'fields name, slug, category, parent_game, version_parent, aggregated_rating, aggregated_rating_count, rating, '
    'first_release_date, summary, genres.name, platforms.name, game_type.id, '
    'cover.image_id, screenshots.image_id, age_ratings.category, age_ratings.rating, '
    'involved_companies.developer, involved_companies.publisher, involved_companies.company.name, '
    'game_modes.name, websites.category, websites.url; '
)

# ── Query helpers ─────────────────────────────────────────────────────────────
def _date_window(pub_ts):
    lo = pub_ts - 1 * 365 * 24 * 3600   # 2 years before episode
    hi = pub_ts + 180 * 24 * 3600       # 6 months after episode
    return lo, hi


def _name_cond(safe, safe_base=None):
    parts = [f'name ~ "{safe}"', f'name ~ *"{safe}"*']
    if safe_base:
        parts += [f'name ~ "{safe_base}"', f'name ~ *"{safe_base}"*']
    return '(' + ' | '.join(parts) + ')'


def _fetch_pass(fields, safe, safe_base, pub_ts=None):
    if pub_ts:
        lo, hi = _date_window(pub_ts)
        search_where = f'where first_release_date >= {lo} & first_release_date <= {hi}; '
        name_yc      = f' & first_release_date >= {lo} & first_release_date <= {hi}'
    else:
        search_where = name_yc = ''
    results = _igdb(f'{fields}search "{safe}"; {search_where}limit 10;')
    if not results:
        results = _igdb(f'{fields}where {_name_cond(safe, safe_base)}{name_yc}; limit 10;')
    return results


# ── Public lookup functions (used by rss catalog warming) ────────────────────
def fetch_by_id(igdb_id: int):
    """Direct lookup by IGDB id. Returns IgdbResult or None. Raises RequestException on failure."""
    results = _igdb(f'{_FIELDS}where id = {int(igdb_id)}; limit 1;')
    if not results:
        return None
    g = results[0]
    _cat = g.get('category') if g.get('category') is not None else (g.get('game_type') or {}).get('id', 0)
    return IgdbResult(id=g['id'], name=g['name'], slug=g.get('slug'),
                      parent_game_id=g.get('parent_game'),
                      version_parent_id=g.get('version_parent'),
                      category=_cat, data=_normalize(g))


def fetch_by_name(name: str, pub_ts: int = None):
    """Name search. Returns IgdbResult or None. Raises RequestException on failure."""
    safe      = name.replace('\\', '').replace('"', '')
    base_name = re.sub(r'\s*[:\-–].+$', '', name).strip()
    safe_base = base_name.replace('\\', '').replace('"', '') if base_name != name else None
    results   = _fetch_pass(_FIELDS, safe, safe_base, pub_ts)
    if not results and pub_ts:
        results = _fetch_pass(_FIELDS, safe, safe_base)
    if not results:
        return None
    if pub_ts:
        lo, hi    = _date_window(pub_ts)
        in_window = [g for g in results if lo <= (g.get('first_release_date') or 0) <= hi]
        if in_window:
            results = in_window
    g = _rank(results, name)[0]
    _cat = g.get('category') if g.get('category') is not None else (g.get('game_type') or {}).get('id', 0)
    return IgdbResult(id=g['id'], name=g['name'], slug=g.get('slug'),
                      parent_game_id=g.get('parent_game'),
                      version_parent_id=g.get('version_parent'),
                      category=_cat, data=_normalize(g))


