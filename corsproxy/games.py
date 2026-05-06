import json
import re
import threading
import datetime
from calendar import timegm
from email.utils import parsedate
import xml.etree.ElementTree as ET

import requests as http
from flask import Blueprint, abort, jsonify, request

from auth import require_auth
from config import Config
from corrections import find_by_podcast
from db import get_db, utcnow
from igdb import fetch_by_id, fetch_by_name
from utils import norm, make_slug
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
_NS_ITUNES  = 'http://www.itunes.com/dtds/podcast-1.0.dtd'

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

        img_el    = item.find(f'{{{_NS_ITUNES}}}image')
        image_url = img_el.get('href') if img_el is not None else None
        if not image_url:
            thumb = item.find(f'{{{_NS_MEDIA}}}thumbnail')
            image_url = thumb.get('url') if thumb is not None else None

        games = []
        for raw_name in game_names:
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
                'title':       title,
                'audioUrl':    audio_url,
                'pubTs':       pub_ts,
                'imageUrl':    image_url,
                'description': raw_desc or None,
                'chapters':    chapters,
                'games':       games,
            })

    return episodes


# ── In-memory RSS state ───────────────────────────────────────────────────────
_rss_lock   = threading.Lock()
_rss_parsed = []
_rss_at     = None


def _rss_is_stale():
    return (
        _rss_at is None
        or (utcnow() - _rss_at).total_seconds() >= Config.RSS_TTL_HOURS * 3600
    )


def _fetch_rss():
    global _rss_parsed, _rss_at
    r = http.get(RSS_URL, timeout=Config.REQUEST_TIMEOUT,
                 headers={'User-Agent': 'SilenceOnJoue/1.0'})
    r.raise_for_status()
    with _rss_lock:
        _rss_parsed = _parse_feed(r.content)
        _rss_at = utcnow()

def _games_from_rss():
    with _rss_lock:
        episodes = list(_rss_parsed)
    games = {}
    for ep in episodes:
        date_str = (datetime.datetime.fromtimestamp(ep['pubTs'], datetime.timezone.utc)
                    .strftime('%Y%m%d') if ep.get('pubTs') else 'nopubts')
        for g in ep['games']:
            ps = make_slug(g['name']) + '-' + date_str
            if ps not in games:
                games[ps] = {'name': g['name'], 'slug': ps,
                             'episodes': [], 'latestPubTs': 0, 'episodeCount': 0}
            games[ps]['episodes'].append({
                'title':            ep['title'],
                'audioUrl':         ep.get('audioUrl'),
                'pubTs':            ep.get('pubTs'),
                'timestamp':        g.get('timestamp'),
                'timestampSeconds': g.get('tsSeconds', 0),
                'imageUrl':         ep.get('imageUrl'),
                'description':      ep.get('description'),
                'chapters':         ep.get('chapters', []),
            })
            if ep.get('pubTs', 0) > games[ps]['latestPubTs']:
                games[ps]['latestPubTs'] = ep['pubTs']
            games[ps]['episodeCount'] += 1
    return games


# ── IGDB resolution ───────────────────────────────────────────────────────────
def _resolve_one(slug, name, episode_pub_ts):
    logger.info("Resolving IGDB data for slug=%r name=%r", slug, name)
    correction = find_by_podcast(name, episode_pub_ts)
    try:
        if correction and correction.get('igdb_id'):
            result = fetch_by_id(correction['igdb_id'])
        else:
            search_name = (correction or {}).get('search_name') or name
            hint_date   = (correction or {}).get('hint_date')
            pub_ts = (int(datetime.datetime.fromisoformat(hint_date)
                          .replace(tzinfo=datetime.timezone.utc).timestamp())
                      if hint_date else episode_pub_ts)
            result = fetch_by_name(search_name, pub_ts)
    except Exception as exc:
        logger.warning("IGDB resolution failed for slug=%r name=%r: %s", slug, name, exc)
        return
    igdb_slug = (result.slug or make_slug(result.name)) if result else None
    now       = utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO igdb_cache '
            '(slug, igdb_id, igdb_slug, name, igdb_data, is_child, cached_at) VALUES (?,?,?,?,?,?,?)',
            (slug,
             result.id             if result else None,
             igdb_slug,
             result.name           if result else None,
             json.dumps(result.data) if result else None,
             int(result.is_child)  if result else 0,
             now)
        )


_resolve_lock   = threading.Lock()
_resolve_thread = None
_resolve_stop   = None


def _do_resolve(stop: threading.Event):
    try:
        games = _games_from_rss()
        if not games:
            return
        with get_db() as conn:
            skip = {r['slug'] for r in conn.execute(
                'SELECT slug FROM igdb_cache'
                ' WHERE (igdb_slug IS NOT NULL OR igdb_data IS NULL)'
                f" AND cached_at > datetime('now', '-{Config.IGDB_TTL_HOURS} hours')",
            ).fetchall()}
        pending = [(ps, info) for ps, info in games.items() if ps not in skip]
        for ps, info in pending:
            if stop.is_set():
                break
            pub_ts = info['episodes'][0].get('pubTs') if info['episodes'] else None
            _resolve_one(ps, info['name'], pub_ts)
    finally:
        global _resolve_stop
        with _resolve_lock:
            if _resolve_stop is stop:
                _resolve_stop = None


def _start_resolve(force=False):
    global _resolve_thread, _resolve_stop
    with _resolve_lock:
        if not force and _resolve_thread and _resolve_thread.is_alive():
            return
        if _resolve_stop:
            _resolve_stop.set()
        stop = threading.Event()
        _resolve_stop   = stop
        _resolve_thread = threading.Thread(target=_do_resolve, args=(stop,), daemon=True)
        _resolve_thread.start()


# ── Startup ───────────────────────────────────────────────────────────────────
def _do_startup():
    if _rss_is_stale():
        try:
            _fetch_rss()
        except Exception as e:
            logger.warning("Startup RSS fetch failed: %s", e)
    _start_resolve()


def startup_warmup():
    threading.Thread(target=_do_startup, daemon=True).start()


# ── Response builders ─────────────────────────────────────────────────────────
def _catalog_response():
    rss_games = _games_from_rss()
    if not rss_games:
        return []
    ph = ','.join('?' * len(rss_games))
    with get_db() as conn:
        rows = conn.execute(
            f'SELECT slug, igdb_id, igdb_slug, name, igdb_data, is_child FROM igdb_cache WHERE slug IN ({ph})',
            list(rss_games.keys())
        ).fetchall()
    cache = {r['slug']: r for r in rows}

    merged_igdb  = {}
    merged_unres = {}

    for ps, g in rss_games.items():
        row = cache.get(ps)
        ep  = g['episodes'][0] if g['episodes'] else {}
        pts = ep.get('pubTs', 0) or 0

        if row and row['igdb_slug']:
            iid = row['igdb_id']
            if iid not in merged_igdb:
                igdb_full = json.loads(row['igdb_data'])
                is_child  = bool(row['is_child'])
                if not is_child:
                    corr    = find_by_podcast(g['name'], ep.get('pubTs'))
                    display = (corr or {}).get('display_name') or row['name']
                else:
                    display = row['name']
                merged_igdb[iid] = {
                    'slug':         row['igdb_slug'],
                    'name':         display,
                    '_from_child':  is_child,
                    'igdb':         {'metacritic': igdb_full.get('metacritic')},
                    'episodeCount': 0,
                    'latestPubTs':  0,
                }
            elif merged_igdb[iid].get('_from_child') and not bool(row['is_child']):
                corr    = find_by_podcast(g['name'], ep.get('pubTs'))
                display = (corr or {}).get('display_name') or row['name']
                merged_igdb[iid]['name']        = display
                merged_igdb[iid]['_from_child'] = False
            merged_igdb[iid]['episodeCount'] += 1
            if pts > merged_igdb[iid]['latestPubTs']:
                merged_igdb[iid]['latestPubTs'] = pts
        else:
            base = make_slug(g['name'])
            if base not in merged_unres:
                merged_unres[base] = {
                    'slug':         base,
                    'name':         g['name'],
                    'igdb':         None,
                    'episodeCount': 0,
                    'latestPubTs':  0,
                }
            merged_unres[base]['episodeCount'] += 1
            if pts > merged_unres[base]['latestPubTs']:
                merged_unres[base]['latestPubTs'] = pts

    for entry in merged_igdb.values():
        entry.pop('_from_child', None)
    result = list(merged_igdb.values()) + list(merged_unres.values())
    return sorted(result, key=lambda g: g['name'].lower())


def _game_row_and_episodes(slug, rss_games=None):
    if rss_games is None:
        rss_games = _games_from_rss()
    with get_db() as conn:
        rows = conn.execute(
            'SELECT slug, name, igdb_data, is_child FROM igdb_cache WHERE igdb_slug = ?', (slug,)
        ).fetchall()
    if rows:
        episodes = []
        for r in rows:
            g = rss_games.get(r['slug'])
            if g:
                episodes.extend(g['episodes'])
        non_child = [r for r in rows if not r['is_child']]
        name_row  = non_child[0] if non_child else rows[0]
        name_g    = rss_games.get(name_row['slug'])
        name_pts  = name_g['episodes'][0].get('pubTs') if name_g and name_g['episodes'] else None
        corr      = find_by_podcast(name_g['name'], name_pts) if name_g else None
        display   = (corr or {}).get('display_name') or name_row['name']
        return {'display_name': display, 'slug': slug, 'igdb_data': rows[0]['igdb_data']}, episodes
    normalized = make_slug(slug)
    matches = [(ps, g) for ps, g in rss_games.items() if make_slug(g['name']) == normalized]
    if matches:
        all_episodes = [ep for _, g in matches for ep in g['episodes']]
        return {'display_name': matches[0][1]['name'], 'slug': normalized,
                'igdb_data': None}, all_episodes
    abort(404, 'Game not found')


# ── Response helpers ──────────────────────────────────────────────────────────
def _game_detail_response(game_row, episodes):
    return jsonify({
        'name':     game_row['display_name'],
        'slug':     game_row['slug'],
        'igdb':     json.loads(game_row['igdb_data']) if game_row['igdb_data'] else None,
        'episodes': episodes,
    })


# ── Endpoints ─────────────────────────────────────────────────────────────────
@games_bp.route('', strict_slashes=False)
def catalog():
    if _rss_is_stale():
        try:
            _fetch_rss()
        except http.exceptions.RequestException as exc:
            if not _rss_parsed:
                abort(502, f'RSS feed unavailable: {exc}')
    _start_resolve()
    return jsonify(_catalog_response())


@games_bp.route('/igdb')
def games_igdb():
    slugs = request.args.getlist('slug')
    if not slugs:
        return jsonify({})
    ph = ','.join('?' * len(slugs))
    with get_db() as conn:
        rows = conn.execute(
            f'SELECT igdb_slug, igdb_data FROM igdb_cache WHERE igdb_slug IN ({ph})',
            slugs
        ).fetchall()
    seen = {}
    for r in rows:
        if r['igdb_slug'] not in seen:
            seen[r['igdb_slug']] = json.loads(r['igdb_data'])
    return jsonify(seen)


@games_bp.route('/refresh', methods=['POST'])
def refresh():
    try:
        _fetch_rss()
        _start_resolve(force=True)
    except http.exceptions.RequestException as exc:
        abort(502, f'RSS feed unavailable: {exc}')
    return jsonify(_catalog_response())


@games_bp.route('/<string:slug>')
def game_detail(slug):
    game_row, episodes = _game_row_and_episodes(slug)
    return _game_detail_response(game_row, episodes)


@games_bp.route('/<string:slug>/igdb-refresh', methods=['POST'])
def game_igdb_refresh(slug):
    rss_games = _games_from_rss()
    with get_db() as conn:
        igdb_rows = conn.execute(
            'SELECT slug FROM igdb_cache WHERE igdb_slug = ?', (slug,)
        ).fetchall()
        if igdb_rows:
            podcast_slugs = [r['slug'] for r in igdb_rows]
            conn.execute('DELETE FROM igdb_cache WHERE igdb_slug = ?', (slug,))
        else:
            normalized    = make_slug(slug)
            podcast_slugs = [ps for ps, g in rss_games.items() if make_slug(g['name']) == normalized]
            if not podcast_slugs:
                abort(404, 'Game not found')
            ph = ','.join('?' * len(podcast_slugs))
            conn.execute(f'DELETE FROM igdb_cache WHERE slug IN ({ph})', podcast_slugs)
    for ps in podcast_slugs:
        g = rss_games.get(ps)
        if g:
            pub_ts = g['episodes'][0].get('pubTs') if g['episodes'] else None
            _resolve_one(ps, g['name'], pub_ts)
    with get_db() as conn:
        row = conn.execute(
            'SELECT igdb_slug FROM igdb_cache WHERE slug = ?', (podcast_slugs[0],)
        ).fetchone()
    new_slug = row['igdb_slug'] if row and row['igdb_slug'] else make_slug(slug)
    game_row, episodes = _game_row_and_episodes(new_slug, rss_games)
    return _game_detail_response(game_row, episodes)
