import json
import re
import threading
import datetime
from calendar import timegm
from email.utils import parsedate
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests as http
from flask import Blueprint, abort, jsonify, request

from auth import require_auth
from config import Config
from corrections import find_by_norm_key
from db import get_db, utcnow
from igdb import TTL_SECONDS as IGDB_TTL_SECONDS, fetch_by_id, fetch_by_name
from utils import norm, norm_key
import logging

logger = logging.getLogger(__name__)

games_bp = Blueprint('games', __name__, url_prefix='/games')
games_bp.before_request(require_auth)

RSS_URL = 'https://feeds.acast.com/public/shows/silence-on-joue'

# ── HTML stripping ────────────────────────────────────────────────────────────
def _strip_html(html):
    if not html:
        return ''
    html = re.sub(r'</p>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<[^>]*>', '', html)
    html = (html.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                .replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' '))
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r'\n[ \t]+', '\n', html)
    return html.strip()


# ── Timestamp parsing ─────────────────────────────────────────────────────────
def _parse_timestamp(ts):
    if not ts:
        return 0
    ts = ts.strip()
    m = re.match(r'^(\d+):(\d{2})(?::(\d{2}))?$', ts)
    if m:
        a, b, c = m.group(1), m.group(2), m.group(3)
        return int(a) * 3600 + int(b) * 60 + int(c) if c else int(a) * 60 + int(b)
    m = re.match(r'^(\d+)\s*h(?:eure?s?)?(\d+)$', ts, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    m = re.match(
        r'(?:(\d+)\s*h(?:eure?s?)?)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?\s*(?:(\d+)\s*s(?:ec(?:ondes?)?)?)?',
        ts, re.IGNORECASE,
    )
    if m:
        total = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
        if total > 0:
            return total
    return 0


# ── Chapter extraction ────────────────────────────────────────────────────────
def _extract_chapters(text):
    chapters = []
    for line in re.split(r'[\n\r]+', text):
        m = re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$', line.strip())
        if m:
            ts_str = m.group(1)
            chapters.append({
                'timestampSeconds': _parse_timestamp(ts_str),
                'timestamp':        ts_str,
                'title':            m.group(2).strip(),
            })
    return chapters


# ── Non-game chapter detection ────────────────────────────────────────────────
_NON_GAME = [
    re.compile(r'^intro$',                         re.IGNORECASE),
    re.compile(r'^les?\s+news?',                   re.IGNORECASE),
    re.compile(r'^com\s+des?\s+coms?',             re.IGNORECASE),
    re.compile(r'^la?\s+minute\s+culturelle',      re.IGNORECASE),
    re.compile(r'^et\s+quand\s+vous\s+ne\s+jouez', re.IGNORECASE),
    re.compile(r'^bande.?annonce',                 re.IGNORECASE),
    re.compile(r'^jeux?\s+de\s+soci',             re.IGNORECASE),
    re.compile(r'^la?\s+chronique',                re.IGNORECASE),
    re.compile(r'^outro$',                         re.IGNORECASE),
    re.compile(r'^g[eé]n[eé]rique',               re.IGNORECASE),
    re.compile(r'^\s*$'),
]


def _is_non_game_chapter(title):
    return any(p.search(title) for p in _NON_GAME)


# ── Legacy title format (pre-guillemet era) ───────────────────────────────────
_SOJ_PREFIX_RE = re.compile(
    r'^(?:'
    r'La\s+semaine\s+des\s+jeux\s+vid[eé]o\s*[!:,]'
    r'|Les\s+jeux\s+vid[eé]o\s+sur\s+Lib[eé]\s+Labo\s*:'
    r'|Silence[,\s]+on\s+joue\s*[!:,]?'
    r')\s*',
    re.IGNORECASE,
)

_NON_GAME_REMAINDER_RE = re.compile(
    r'^(?:sp[eé]cial|grand\s+entretien|le\s+bilan|en\s+public|'
    r'avec\s+l[ea]\s|avec\s+les\s|un\s+peu\s+de|dix\s+ans|'
    r'le\s+final|le\s+meilleur\s+de|le\s+plein|'
    r'on\s+r[eé]pond|une\s+histoire|la\s+place)',
    re.IGNORECASE,
)


def _extract_legacy_names(title):
    m = _SOJ_PREFIX_RE.match(title)
    if not m:
        return []
    remainder = title[m.end():]
    if not remainder or _NON_GAME_REMAINDER_RE.match(remainder):
        return []
    parts = re.split(r',\s*|\s+et\s+', remainder)
    names = []
    for p in parts:
        p = re.sub(r'[.!…]+$', '', p.strip()).strip()
        if len(p) >= 2:
            names.append(p)
    return names


# ── Game name extraction ──────────────────────────────────────────────────────
def _extract_game_names(title):
    if not title:
        return []
    names = [m.group(1).strip() for m in re.finditer(r'«([^»]+)»', title)
             if len(m.group(1).strip()) > 1]
    return names if names else _extract_legacy_names(title)


# ── Timestamp matching ────────────────────────────────────────────────────────
def _find_timestamp(game_name, chapters):
    norm_game = norm(game_name)
    best, best_score = None, 0
    for ch in chapters:
        if _is_non_game_chapter(ch['title']):
            continue
        norm_ch = norm(ch['title'])
        if norm_ch == norm_game:
            score = 3
        elif norm_ch in norm_game or norm_game in norm_ch:
            score = 2
        else:
            gw = {w for w in norm_game.split() if len(w) > 2}
            cw = {w for w in norm_ch.split()   if len(w) > 2}
            overlap = len(gw & cw)
            score   = overlap / max(len(gw), len(cw)) if overlap and gw and cw else 0
        if score > best_score:
            best_score, best = score, ch
    if best_score >= 0.5 and best:
        return {'timestamp': best['timestamp'], 'timestampSeconds': best['timestampSeconds']}
    return None


# ── XML helpers ───────────────────────────────────────────────────────────────
_NS_CONTENT = 'http://purl.org/rss/1.0/modules/content/'
_NS_MEDIA   = 'http://search.yahoo.com/mrss/'

_SKIP_RE = [
    re.compile(r'^quel(le)?\s',                                re.IGNORECASE),
    re.compile(r'bande.?annonce',                              re.IGNORECASE),
    re.compile(r'^\[reportage\]',                              re.IGNORECASE),
    re.compile(r'^\[hors-série\]\s*(la\s+faq|le\s+bilan)',    re.IGNORECASE),
]


def _get_audio_url(item):
    enc = item.find('enclosure')
    if enc is not None and enc.get('url'):
        return enc.get('url')
    media = item.find(f'{{{_NS_MEDIA}}}content')
    if media is not None and media.get('url'):
        return media.get('url')
    link = (item.findtext('link') or '').strip()
    return link if re.search(r'\.(mp3|m4a|ogg|aac)', link, re.IGNORECASE) else None


# ── Feed parsing (pure XML → dicts, no DB) ────────────────────────────────────
def _parse_feed(xml_bytes):
    root    = ET.fromstring(xml_bytes)
    channel = root.find('channel')
    if channel is None:
        channel = root
    episodes = []

    for item in channel.findall('item'):
        title = (item.findtext('title') or '').strip() or 'Episode sans titre'
        if any(p.search(title) for p in _SKIP_RE):
            continue

        game_names = _extract_game_names(title)
        if not game_names:
            continue

        audio_url = _get_audio_url(item)
        raw_pub   = (item.findtext('pubDate') or '').strip()
        parsed_d  = parsedate(raw_pub) if raw_pub else None
        pub_ts    = timegm(parsed_d) if parsed_d else None
        raw_desc  = (item.findtext(f'{{{_NS_CONTENT}}}encoded') or
                     item.findtext('description') or '')
        chapters  = _extract_chapters(_strip_html(raw_desc))

        games = []
        for raw_name in game_names:
            logger.info("Extracted game name %r from title %r", raw_name, title)
            raw_name = re.sub(r'^[,\s]+', '', raw_name).strip()
            if len(raw_name) < 2:
                continue
            ts = _find_timestamp(raw_name, chapters)
            games.append({
                'name':      raw_name,
                'timestamp': ts['timestamp']        if ts else None,
                'tsSeconds': ts['timestampSeconds'] if ts else 0,
            })
        if games:
            episodes.append({
                'title':    title,
                'audioUrl': audio_url,
                'pubTs':    pub_ts,
                'games':    games,
            })

    return episodes


# ── Catalog upsert ────────────────────────────────────────────────────────────
def _sync_catalog(parsed_episodes):
    now = utcnow().isoformat()
    with get_db() as conn:
        for ep in parsed_episodes:
            conn.execute(
                'INSERT OR IGNORE INTO episodes (title, audio_url, pub_ts) VALUES (?, ?, ?)',
                (ep['title'], ep.get('audioUrl'), ep.get('pubTs'))
            )
            ep_id = conn.execute(
                'SELECT id FROM episodes WHERE title = ?', (ep['title'],)
            ).fetchone()['id']
            for g in ep['games']:
                key = norm_key(g['name'])
                row = conn.execute(
                    'SELECT id FROM games WHERE norm_key = ?', (key,)
                ).fetchone()
                if row:
                    game_id = row['id']
                    conn.execute('UPDATE games SET rss_at = ? WHERE id = ?', (now, game_id))
                else:
                    game_id = conn.execute(
                        'INSERT INTO games (norm_key, display_name, rss_at) VALUES (?, ?, ?)',
                        (key, g['name'], now)
                    ).lastrowid
                conn.execute(
                    '''INSERT OR IGNORE INTO episode_games (episode_id, game_id, timestamp, ts_seconds)
                       VALUES (?, ?, ?, ?)''',
                    (ep_id, game_id, g.get('timestamp'), g.get('tsSeconds', 0))
                )


# ── Staleness check ───────────────────────────────────────────────────────────
def _rss_is_stale():
    with get_db() as conn:
        row = conn.execute('SELECT MAX(rss_at) AS last FROM games').fetchone()
    if not row or not row['last']:
        return True
    age = (utcnow() - datetime.datetime.fromisoformat(row['last'])).total_seconds()
    return age >= Config.RSS_TTL_MINUTES * 60


# ── IGDB warming ──────────────────────────────────────────────────────────────
def _get_game_year_from_db(game_id):
    with get_db() as conn:
        row = conn.execute(
            '''SELECT MIN(e.pub_ts) AS min_ts
               FROM episode_games eg
               JOIN episodes e ON e.id = eg.episode_id
               WHERE eg.game_id = ?''',
            (game_id,)
        ).fetchone()
    if row and row['min_ts']:
        return datetime.datetime.fromtimestamp(row['min_ts'], datetime.timezone.utc).year
    return None


def _apply_igdb_result(game_id, result):
    now = utcnow().isoformat()
    with get_db() as conn:
        if result is None:
            conn.execute('UPDATE games SET igdb_at = ? WHERE id = ?', (now, game_id))
            return
        existing = conn.execute(
            'SELECT id FROM games WHERE igdb_id = ? AND id != ?',
            (result.id, game_id)
        ).fetchone()
        if existing:
            winner_id = existing['id']
            conn.execute(
                'UPDATE OR IGNORE episode_games SET game_id = ? WHERE game_id = ?',
                (winner_id, game_id)
            )
            conn.execute('DELETE FROM episode_games WHERE game_id = ?', (game_id,))
            conn.execute('DELETE FROM games WHERE id = ?', (game_id,))
        else:
            conn.execute(
                '''UPDATE games
                   SET igdb_id = ?, display_name = ?, igdb_data = ?, igdb_at = ?
                   WHERE id = ?''',
                (result.id, result.name, json.dumps(result.data), now, game_id)
            )


def _warm_one(game_row):
    logger.info("Warming IGDB data for game_id=%d name=%r", game_row['id'], game_row['display_name'])
    game_id = game_row['id']
    correction = find_by_norm_key(game_row['norm_key'])
    try:
        if game_row['igdb_id']:
            result = fetch_by_id(game_row['igdb_id'])
        elif correction and correction.get('igdb_id'):
            result = fetch_by_id(correction['igdb_id'])
        else:
            search_name = (correction or {}).get('search_name') or game_row['display_name']
            year        = _get_game_year_from_db(game_id)
            result      = fetch_by_name(search_name, year)
    except Exception:
        return
    _apply_igdb_result(game_id, result)


_warming_lock   = threading.Lock()
_warming_active = False


def _do_warm():
    global _warming_active
    try:
        stale_threshold = (
            utcnow() - datetime.timedelta(seconds=IGDB_TTL_SECONDS)
        ).isoformat()
        with get_db() as conn:
            games = conn.execute(
                'SELECT id, norm_key, display_name, igdb_id FROM games WHERE igdb_data IS NULL OR igdb_at < ?',
                (stale_threshold,)
            ).fetchall()
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(_warm_one, games))
    finally:
        with _warming_lock:
            _warming_active = False


def _start_warming():
    global _warming_active
    with _warming_lock:
        if _warming_active:
            return
        _warming_active = True
    threading.Thread(target=_do_warm, daemon=True).start()


# ── Response builders ─────────────────────────────────────────────────────────
def _catalog_response():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT g.display_name, g.igdb_data,
                      COUNT(eg.episode_id) AS episode_count,
                      MAX(e.pub_ts)        AS latest_pub_ts
               FROM games g
               JOIN episode_games eg ON eg.game_id = g.id
               JOIN episodes e       ON e.id = eg.episode_id
               GROUP BY g.id
               ORDER BY lower(g.display_name)'''
        ).fetchall()
    result = []
    for r in rows:
        igdb_full = json.loads(r['igdb_data']) if r['igdb_data'] else None
        igdb_slim = {'metacritic': igdb_full.get('metacritic')} if igdb_full else None
        result.append({
            'name':         r['display_name'],
            'igdb':         igdb_slim,
            'episodeCount': r['episode_count'],
            'latestPubTs':  r['latest_pub_ts'] or 0,
        })
    return result


def _game_row_and_episodes(name):
    """Look up one game by display_name (case-insensitive). Returns (game_row, episodes) or aborts 404."""
    with get_db() as conn:
        game_row = conn.execute(
            'SELECT id, display_name, igdb_data FROM games WHERE lower(display_name) = lower(?)',
            (name,)
        ).fetchone()
        if not game_row:
            game_row = conn.execute(
                'SELECT id, display_name, igdb_data FROM games WHERE norm_key = ?',
                (norm_key(name),)
            ).fetchone()
        if not game_row:
            abort(404, 'Game not found')
        ep_rows = conn.execute(
            '''SELECT e.title, e.audio_url, e.pub_ts, eg.timestamp, eg.ts_seconds
               FROM episode_games eg
               JOIN episodes e ON e.id = eg.episode_id
               WHERE eg.game_id = ?
               ORDER BY eg.rowid''',
            (game_row['id'],)
        ).fetchall()
    episodes = [
        {
            'title':            r['title'],
            'audioUrl':         r['audio_url'],
            'pubTs':            r['pub_ts'],
            'timestamp':        r['timestamp'],
            'timestampSeconds': r['ts_seconds'],
        }
        for r in ep_rows
    ]
    return game_row, episodes


# ── Endpoints ─────────────────────────────────────────────────────────────────
@games_bp.route('', strict_slashes=False)
def catalog():
    if _rss_is_stale():
        try:
            r = http.get(RSS_URL, timeout=Config.REQUEST_TIMEOUT,
                         headers={'User-Agent': 'SilenceOnJoue/1.0'})
            r.raise_for_status()
            parsed = _parse_feed(r.content)
            _sync_catalog(parsed)
            _start_warming()
        except http.exceptions.RequestException as exc:
            with get_db() as conn:
                count = conn.execute('SELECT COUNT(*) FROM games').fetchone()[0]
            if count == 0:
                abort(502, f'RSS feed unavailable: {exc}')
    return jsonify(_catalog_response())


@games_bp.route('/igdb')
def games_igdb():
    names = request.args.getlist('name')
    if not names:
        return jsonify({})
    with get_db() as conn:
        placeholders = ','.join('?' * len(names))
        rows = conn.execute(
            f'SELECT display_name, igdb_data FROM games WHERE display_name IN ({placeholders})',
            names
        ).fetchall()
    return jsonify({
        row['display_name']: json.loads(row['igdb_data'])
        for row in rows
        if row['igdb_data']
    })


@games_bp.route('/refresh', methods=['POST'])
def refresh():
    try:
        r = http.get(RSS_URL, timeout=Config.REQUEST_TIMEOUT,
                     headers={'User-Agent': 'SilenceOnJoue/1.0'})
        r.raise_for_status()
        parsed = _parse_feed(r.content)
        _sync_catalog(parsed)
        _start_warming()
    except http.exceptions.RequestException as exc:
        abort(502, f'RSS feed unavailable: {exc}')
    return jsonify(_catalog_response())


@games_bp.route('/<string:slug>')
def game_detail(slug):
    game_row, episodes = _game_row_and_episodes(slug)
    return jsonify({
        'name':     game_row['display_name'],
        'igdb':     json.loads(game_row['igdb_data']) if game_row['igdb_data'] else None,
        'episodes': episodes,
    })


@games_bp.route('/<string:slug>/igdb-refresh', methods=['POST'])
def game_igdb_refresh(slug):
    with get_db() as conn:
        row = conn.execute(
            'SELECT id, norm_key, display_name, igdb_id FROM games WHERE lower(display_name) = lower(?)',
            (slug,)
        ).fetchone()
        if not row:
            row = conn.execute(
                'SELECT id, norm_key, display_name, igdb_id FROM games WHERE norm_key = ?',
                (norm_key(slug),)
            ).fetchone()
    if not row:
        abort(404, 'Game not found')
    with get_db() as conn:
        conn.execute(
            'UPDATE games SET igdb_data = NULL, igdb_at = NULL WHERE id = ?',
            (row['id'],)
        )
    _warm_one(row)
    game_row, episodes = _game_row_and_episodes(slug)
    return jsonify({
        'name':     game_row['display_name'],
        'igdb':     json.loads(game_row['igdb_data']) if game_row['igdb_data'] else None,
        'episodes': episodes,
    })
