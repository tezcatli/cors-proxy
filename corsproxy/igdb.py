import re
import time
import threading
import datetime
import requests as http
from flask import Blueprint, request, jsonify, abort
from db import cache_get, cache_set, SENTINEL
from config import Config
from auth import _decode_jwt, require_auth
from utils import norm_key as _norm_key

igdb_bp = Blueprint('igdb', __name__, url_prefix='/igdb')
igdb_bp.before_request(require_auth)

TTL_DAYS   = 30
TTL_SECONDS = TTL_DAYS * 86400
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
    url = None
    if g.get('cover') and g['cover'].get('image_id'):
        url = f"https://images.igdb.com/igdb/image/upload/t_cover_big_2x/{g['cover']['image_id']}.jpg"

    bg_url = None
    shots = g.get('screenshots') or []
    if shots and shots[0].get('image_id'):
        bg_url = f"https://images.igdb.com/igdb/image/upload/t_720p/{shots[0]['image_id']}.jpg"

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

    developer = None
    for ic in (g.get('involved_companies') or []):
        if ic.get('developer') and ic.get('company'):
            developer = ic['company'].get('name')
            break

    return dict(url=url, bgUrl=bg_url, metacritic=metacritic, rating=rating, genres=genres,
                released=released, platforms=platforms, esrb=esrb,
                description=description, developer=developer)


# ── Query helpers ─────────────────────────────────────────────────────────────
def _year_window(year):
    lo = int(datetime.datetime(year - 1, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
    hi = int(datetime.datetime(year + 1, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc).timestamp())
    return lo, hi


def _name_cond(safe, safe_base=None):
    parts = [f'name ~ "{safe}"', f'name ~ *"{safe}"*']
    if safe_base:
        parts += [f'name ~ "{safe_base}"', f'name ~ *"{safe_base}"*']
    return '(' + ' | '.join(parts) + ')'


def _fetch_pass(fields, safe, safe_base, year=None):
    if year:
        lo, hi = _year_window(year)
        search_where = f'where first_release_date >= {lo} & first_release_date <= {hi}; '
        name_yc      = f' & first_release_date >= {lo} & first_release_date <= {hi}'
    else:
        search_where = name_yc = ''
    results = _igdb(f'{fields}search "{safe}"; {search_where}limit 10;')
    if not results:
        results = _igdb(f'{fields}where {_name_cond(safe, safe_base)}{name_yc}; limit 10;')
    return results


# ── Endpoint ──────────────────────────────────────────────────────────────────
@igdb_bp.route('/game')
def game():
    name = request.args.get('name', '').strip()
    if not name:
        abort(400, 'Missing required query parameter: name')
    if not Config.IGDB_CLIENT_ID or not Config.IGDB_CLIENT_SECRET:
        abort(503, 'IGDB credentials not configured')

    try:
        year = int(request.args['year']) if 'year' in request.args else None
    except ValueError:
        year = None

    norm  = _norm_key(name)
    key   = f'{norm}_{year}' if year else norm
    cached = cache_get('igdb_cache', key, TTL_SECONDS)
    if cached is not SENTINEL:
        return jsonify(cached)

    safe      = name.replace('\\', '').replace('"', '')
    base_name = re.sub(r'\s*[:\-–].+$', '', name).strip()
    safe_base = base_name.replace('\\', '').replace('"', '') if base_name != name else None

    fields = (
        'fields name, aggregated_rating, aggregated_rating_count, rating, '
        'first_release_date, summary, genres.name, platforms.name, '
        'cover.image_id, screenshots.image_id, age_ratings.category, age_ratings.rating, '
        'involved_companies.developer, involved_companies.company.name; '
    )

    try:
        results = _fetch_pass(fields, safe, safe_base, year)
        if not results and year:
            results = _fetch_pass(fields, safe, safe_base)

        if not results:
            cache_set('igdb_cache', key, None)
            return jsonify(None)

        data = _normalize(_rank(results, name)[0])
        cache_set('igdb_cache', key, data)
        return jsonify(data)

    except http.exceptions.RequestException as exc:
        abort(502, f'IGDB API indisponible : {exc}')
