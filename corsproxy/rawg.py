import json
import datetime
import requests as http
import jwt as pyjwt
from flask import Blueprint, request, jsonify, abort
from db import get_db
from config import Config

rawg_bp = Blueprint('rawg', __name__, url_prefix='/rawg')

RAWG_BASE = 'https://api.rawg.io/api'
TTL_DAYS  = 30


@rawg_bp.before_request
def _require_auth():
    if Config.DEBUG:
        return
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        abort(401, 'Not authenticated')
    try:
        pyjwt.decode(auth[7:], Config.JWT_SECRET, algorithms=['HS256'])
    except pyjwt.PyJWTError:
        abort(401, 'Not authenticated')


def _cache_get(key):
    with get_db() as conn:
        row = conn.execute(
            'SELECT data, cached_at FROM rawg_cache WHERE key = ?', (key,)
        ).fetchone()
    if not row:
        return None
    age = datetime.datetime.utcnow() - datetime.datetime.fromisoformat(row['cached_at'])
    if age.days >= TTL_DAYS:
        return None
    return json.loads(row['data'])


def _cache_set(key, data):
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO rawg_cache (key, data, cached_at) VALUES (?, ?, ?)',
            (key, json.dumps(data), datetime.datetime.utcnow().isoformat()),
        )


@rawg_bp.route('/<path:path>')
def proxy(path):
    if not Config.RAWG_KEY:
        abort(503, 'RAWG API key not configured')
    qs = '&'.join(f'{k}={v}' for k, v in sorted(request.args.items()))
    cache_key = f'{path}?{qs}' if qs else path
    cached = _cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)
    try:
        r = http.get(
            f'{RAWG_BASE}/{path}',
            params={**request.args, 'key': Config.RAWG_KEY},
            timeout=Config.REQUEST_TIMEOUT,
        )
        r.raise_for_status()
    except http.exceptions.RequestException as exc:
        abort(502, f'RAWG API indisponible : {exc}')
    data = r.json()
    _cache_set(cache_key, data)
    return jsonify(data)
