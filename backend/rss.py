"""
Pure RSS feed parsing for the Silence on Joue podcast.
No I/O, no global state, no imports from other app modules.
"""

import re
from calendar import timegm
from email.utils import parsedate
from html import escape as _html_escape
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

from models import Chapter, Episode, GameMention
from utils import make_slug, norm as _norm


# ── XML namespace prefixes ────────────────────────────────────────────────────
_NS_CONTENT = 'http://purl.org/rss/1.0/modules/content/'
_NS_MEDIA   = 'http://search.yahoo.com/mrss/'
_NS_ITUNES  = 'http://www.itunes.com/dtds/podcast-1.0.dtd'

# ── Episode title filters (skip non-game episodes entirely) ──────────────────
_SKIP_TITLE = [
    re.compile(r'^quel(le)?\s',                                re.IGNORECASE),
    re.compile(r'bande.?annonce',                              re.IGNORECASE),
    re.compile(r'^\[reportage\]',                              re.IGNORECASE),
    re.compile(r'^\[hors-série\]\s*(la\s+faq|le\s+bilan)',    re.IGNORECASE),
]

# ── Chapter titles that are not game names ────────────────────────────────────
_NON_GAME_CHAPTER = [
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

# ── Legacy title patterns (pre-guillemet era) ─────────────────────────────────
_LEGACY_PREFIX = re.compile(
    r'^(?:'
    r'La\s+semaine\s+des\s+jeux\s+vid[eé]o\s*[!:,]'
    r'|Les\s+jeux\s+vid[eé]o\s+sur\s+Lib[eé]\s+Labo\s*:'
    r'|Silence[,\s]+on\s+joue\s*[!:,]?'
    r')\s*',
    re.IGNORECASE,
)

# Remainders after the legacy prefix that are not game lists
_LEGACY_NON_GAME_REMAINDER = re.compile(
    r'^(?:sp[eé]cial|grand\s+entretien|le\s+bilan|en\s+public|'
    r'avec\s+l[ea]\s|avec\s+les\s|un\s+peu\s+de|dix\s+ans|'
    r'le\s+final|le\s+meilleur\s+de|le\s+plein|'
    r'on\s+r[eé]pond|une\s+histoire|la\s+place)',
    re.IGNORECASE,
)


# ── HTML stripping ────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
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


# ── HTML sanitisation ─────────────────────────────────────────────────────────
# The episode description is rendered with v-html on the client, so the feed's
# HTML must be reduced to a safe whitelist before it ever reaches the browser.

_ALLOWED_TAGS       = {'p', 'br', 'ul', 'ol', 'li', 'strong', 'em', 'b', 'i', 'a'}
_VOID_TAGS          = {'br'}
_DROP_CONTENT_TAGS  = {'script', 'style'}
_SAFE_URL_RE        = re.compile(r'^(?:https?:|mailto:|/|#)', re.IGNORECASE)


class _Sanitizer(HTMLParser):
    """Keep only whitelisted tags; drop everything else (and script/style bodies)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out = []
        self._suppress = 0   # depth inside a drop-content tag

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_CONTENT_TAGS:
            self._suppress += 1
            return
        if self._suppress or tag not in _ALLOWED_TAGS:
            return
        if tag == 'a':
            href = next((v for k, v in attrs if k == 'href' and v), None)
            if href and _SAFE_URL_RE.match(href.strip()):
                safe = _html_escape(href.strip(), quote=True)
                self._out.append(f'<a href="{safe}" rel="noopener noreferrer" target="_blank">')
            else:
                self._out.append('<a>')
        else:
            self._out.append(f'<{tag}>')

    def handle_startendtag(self, tag, attrs):
        if self._suppress or tag not in _ALLOWED_TAGS:
            return
        if tag in _VOID_TAGS:
            self._out.append(f'<{tag}>')
        elif tag == 'a':
            self.handle_starttag(tag, attrs)
            self._out.append('</a>')
        else:
            self._out.append(f'<{tag}></{tag}>')

    def handle_endtag(self, tag):
        if tag in _DROP_CONTENT_TAGS:
            self._suppress = max(0, self._suppress - 1)
            return
        if self._suppress or tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        self._out.append(f'</{tag}>')

    def handle_data(self, data):
        if not self._suppress:
            self._out.append(_html_escape(data, quote=False))

    def result(self) -> str:
        return ''.join(self._out)


def sanitize_html(html: str) -> str:
    """Reduce feed HTML to a safe whitelisted subset for client-side rendering."""
    if not html:
        return html
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    return parser.result().strip()


# ── Timestamp parsing ─────────────────────────────────────────────────────────

def _parse_timestamp(ts: str) -> int:
    """Convert a human-readable timestamp string to seconds. Returns 0 on failure."""
    if not ts:
        return 0
    ts = ts.strip()
    m = re.match(r'^(\d+):(\d{2})(?::(\d{2}))?$', ts)
    if m:
        h, m2, s = m.group(1), m.group(2), m.group(3)
        return int(h) * 3600 + int(m2) * 60 + int(s) if s else int(h) * 60 + int(m2)
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

def _extract_chapters(text: str) -> list[Chapter]:
    chapters = []
    for line in re.split(r'[\n\r]+', text):
        m = re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$', line.strip())
        if m:
            ts_str = m.group(1)
            chapters.append(Chapter(
                timestamp=ts_str,
                timestamp_seconds=_parse_timestamp(ts_str),
                title=m.group(2).strip(),
            ))
    return chapters


def _strip_chapter_list(html: str, chapters: list[Chapter]) -> str:
    """Remove chapter-list paragraphs from an HTML description."""
    html = re.sub(r'<p>Chapitres.*?</p>', '', html, flags=re.IGNORECASE | re.DOTALL)
    for ch in chapters:
        ts = re.escape(ch.timestamp)
        html = re.sub(rf'<p>{ts}.*?</p>', '', html, flags=re.IGNORECASE | re.DOTALL)
    return html


def _is_non_game_chapter(title: str) -> bool:
    return any(p.search(title) for p in _NON_GAME_CHAPTER)


# ── Timestamp matching ────────────────────────────────────────────────────────

def find_chapter_for_game(game_name: str, chapters: list[Chapter]) -> Chapter | None:
    """Return the chapter most likely corresponding to game_name, or None."""
    norm_game = _norm(game_name)

    # Fast path: trust AI-annotated game_name if present
    for chapter in chapters:
        if chapter.game_name and _norm(chapter.game_name) == norm_game:
            return chapter

    best: Chapter | None = None
    best_score = 0.0

    for chapter in chapters:
        if _is_non_game_chapter(chapter.title):
            continue
        norm_chapter = _norm(chapter.title)
        if norm_chapter == norm_game:
            score = 3.0
        elif norm_chapter in norm_game or norm_game in norm_chapter:
            score = 2.0
        else:
            game_words    = {w for w in norm_game.split()    if len(w) > 2}
            chapter_words = {w for w in norm_chapter.split() if len(w) > 2}
            overlap = len(game_words & chapter_words)
            score = overlap / max(len(game_words), len(chapter_words)) if overlap and game_words and chapter_words else 0.0

        if score > best_score:
            best_score, best = score, chapter

    return best if best_score >= 0.5 else None


# ── Audio URL extraction ──────────────────────────────────────────────────────

def _get_audio_url(item: ET.Element) -> str | None:
    enc = item.find('enclosure')
    if enc is not None and enc.get('url'):
        return enc.get('url')
    media = item.find(f'{{{_NS_MEDIA}}}content')
    if media is not None and media.get('url'):
        return media.get('url')
    link = (item.findtext('link') or '').strip()
    return link if re.search(r'\.(mp3|m4a|ogg|aac)', link, re.IGNORECASE) else None


# ── Game name extraction ──────────────────────────────────────────────────────

def extract_legacy_names(title: str) -> list[str]:
    """Extract game names from the pre-guillemet 'Silence on joue !' title format."""
    m = _LEGACY_PREFIX.match(title)
    if not m:
        return []
    remainder = title[m.end():]
    if not remainder or _LEGACY_NON_GAME_REMAINDER.match(remainder):
        return []
    parts = re.split(r',\s*|\s+et\s+', remainder)
    names = []
    for part in parts:
        part = re.sub(r'[.!…]+$', '', part.strip()).strip()
        if len(part) >= 2:
            names.append(part)
    return names


def extract_game_names(title: str) -> list[str]:
    """Extract game names from an episode title.

    Prefers the modern «guillemet» format; falls back to the legacy prefix format.
    """
    if not title:
        return []
    guillemet_names = [m.group(1).strip() for m in re.finditer(r'«([^»]+)»', title)
                       if len(m.group(1).strip()) > 1]
    return guillemet_names if guillemet_names else extract_legacy_names(title)


# ── Feed parser ───────────────────────────────────────────────────────────────

def is_game_catalog_excluded(title: str) -> bool:
    """True for items that should not appear in the game catalog (trailers, etc.)."""
    return any(p.search(title) for p in _SKIP_TITLE)


def parse_feed(xml_bytes: bytes) -> list[Episode]:
    """Parse an RSS feed and return one Episode per RSS item."""
    root    = ET.fromstring(xml_bytes)
    channel = root.find('channel')
    if channel is None:
        channel = root
    episodes: list[Episode] = []

    for item in channel.findall('item'):
        title = (item.findtext('title') or '').strip() or 'Episode sans titre'

        game_names = extract_game_names(title)

        audio_url = _get_audio_url(item)

        # Canonical episode identity: the RSS guid is a stable, unique per-item id
        # (more stable than the title, which gets edited). Fall back to the audio
        # URL, then the title slug, so a guid-less item still gets a usable key.
        guid       = (item.findtext('guid') or '').strip()
        episode_id = guid or make_slug(audio_url or '') or make_slug(title)

        raw_pub  = (item.findtext('pubDate') or '').strip()
        parsed_d = parsedate(raw_pub) if raw_pub else None
        pub_ts   = timegm(parsed_d) if parsed_d else None

        raw_desc = (item.findtext(f'{{{_NS_CONTENT}}}encoded') or
                    item.findtext('description') or '')
        chapters   = _extract_chapters(_strip_html(raw_desc))
        clean_desc = _strip_chapter_list(raw_desc, chapters) if chapters else raw_desc
        clean_desc = sanitize_html(clean_desc)

        img_el    = item.find(f'{{{_NS_ITUNES}}}image')
        image_url = img_el.get('href') if img_el is not None else None
        if not image_url:
            thumb     = item.find(f'{{{_NS_MEDIA}}}thumbnail')
            image_url = thumb.get('url') if thumb is not None else None

        mentions: list[GameMention] = []
        for raw_name in game_names:
            raw_name = re.sub(r'^[,\s]+', '', raw_name).strip()
            if len(raw_name) < 2:
                continue
            matched = find_chapter_for_game(raw_name, chapters)
            mentions.append(GameMention(
                name=raw_name,
                timestamp=matched.timestamp if matched else None,
                timestamp_seconds=matched.timestamp_seconds if matched else 0,
            ))

        episodes.append(Episode(
            title=title,
            slug=episode_id,
            audio_url=audio_url,
            pub_ts=pub_ts,
            image_url=image_url,
            description=clean_desc or None,
            chapters=chapters,
            games=mentions,
        ))

    # Assign human-readable URL slugs from the title, de-duplicated so no two
    # episodes collide. The guid (`slug`) stays the stable internal identity;
    # `url_slug` is purely cosmetic for routing. Feed order is stable, so the
    # numeric suffixes on any rare collision are stable across reloads too.
    seen: dict[str, int] = {}
    for ep in episodes:
        base = make_slug(ep.title) or make_slug(ep.slug) or 'episode'
        n = seen.get(base, 0)
        seen[base] = n + 1
        ep.url_slug = base if n == 0 else f'{base}-{n + 1}'

    return episodes
