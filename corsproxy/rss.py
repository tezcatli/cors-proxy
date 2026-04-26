import re
import xml.etree.ElementTree as ET

import requests as http
from flask import Blueprint, abort, jsonify, request

from auth import require_auth
from config import Config
from db import cache_get, cache_set, SENTINEL
from utils import norm, norm_key

rss_bp = Blueprint('rss', __name__, url_prefix='/rss')
rss_bp.before_request(require_auth)

RSS_URL    = 'https://feeds.acast.com/public/shows/silence-on-joue'
_CACHE_KEY = 'feed'

# ── Corrections (port of corrections.js) ─────────────────────────────────────
_CORRECTIONS = {norm_key(k): v for k, v in [
    ('artic eggs',                         'Arctic Eggs'),
    ('make way',                           'Make Way'),
    ("l'ordre des géants",                 'Indiana Jones and the Great Circle: The Order of Giants'),
    ('indiana jones et le cercle ancien',  'Indiana Jones and the Great Circle'),
    ('1348: Ex-Voto',                      '1348: Ex Voto'),
    ('elden ring nightrein',               'elden ring nightreign'),
    ('Vendran las aves',                   'Vendrán las aves'),
    ('shogun shodown',                     'Shogun Showdown'),
    ('Eté',                                'Été'),
    ('beyond good and evil remastered',    'Beyond Good & Evil: 20th Anniversary Edition'),
    ('Top Spin 2K25',                      'Top Spin 2K 25'),
]}


def _correct(name):
    return _CORRECTIONS.get(norm_key(name), name)


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
    re.compile(r'^jeux?\s+de\s+soci',              re.IGNORECASE),
    re.compile(r'^la?\s+chronique',                re.IGNORECASE),
    re.compile(r'^outro$',                         re.IGNORECASE),
    re.compile(r'^g[eé]n[eé]rique',               re.IGNORECASE),
    re.compile(r'^\s*$'),
]


def _is_non_game_chapter(title):
    return any(p.search(title) for p in _NON_GAME)


# ── Game name extraction ──────────────────────────────────────────────────────
def _extract_game_names(title):
    if not title:
        return []
    return [m.group(1).strip() for m in re.finditer(r'«([^»]+)»', title)
            if len(m.group(1).strip()) > 1]


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


# ── Feed parsing ──────────────────────────────────────────────────────────────
def _parse_feed(xml_bytes):
    root    = ET.fromstring(xml_bytes)
    channel = root.find('channel')
    if channel is None:
        channel = root
    games_map = {}

    for item in channel.findall('item'):
        title = (item.findtext('title') or '').strip() or 'Episode sans titre'
        if any(p.search(title) for p in _SKIP_RE):
            continue

        game_names = _extract_game_names(title)
        if not game_names:
            continue

        audio_url = _get_audio_url(item)
        pub_date  = (item.findtext('pubDate') or '').strip() or None
        raw_desc  = (item.findtext(f'{{{_NS_CONTENT}}}encoded') or
                     item.findtext('description') or '')
        chapters  = _extract_chapters(_strip_html(raw_desc))

        for name in game_names:
            name = _correct(re.sub(r'^[,\s]+', '', name).strip())
            if len(name) < 2:
                continue
            key = norm_key(name)
            if key not in games_map:
                games_map[key] = {'name': name, 'episodes': []}
            ts = _find_timestamp(name, chapters)
            games_map[key]['episodes'].append({
                'title':            title,
                'audioUrl':         audio_url,
                'pubDate':          pub_date,
                'timestamp':        ts['timestamp']        if ts else None,
                'timestampSeconds': ts['timestampSeconds'] if ts else 0,
            })

    return sorted(games_map.values(), key=lambda g: g['name'].lower())


# ── Endpoint ──────────────────────────────────────────────────────────────────
@rss_bp.route('/games')
def games():
    cached = cache_get('games_cache', _CACHE_KEY, Config.RSS_TTL_MINUTES * 60)
    if cached is not SENTINEL:
        return jsonify(cached)
    try:
        r = http.get(RSS_URL, timeout=Config.REQUEST_TIMEOUT,
                     headers={'User-Agent': 'SilenceOnJoue/1.0'})
        r.raise_for_status()
    except http.exceptions.RequestException as exc:
        abort(502, f'RSS feed unavailable: {exc}')
    result = _parse_feed(r.content)
    cache_set('games_cache', _CACHE_KEY, result)
    return jsonify(result)
