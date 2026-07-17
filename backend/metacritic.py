"""Scrape the real Metacritic critic score for a game.

Metacritic has no public API; this fetches the public game page and reads the
critic Metascore from its JSON-LD `ratingValue`. Best-effort + gently rate-limited
(a probe drew 0 Cloudflare blocks at ~1 req/1.4 s); any failure (404, block, parse
error) returns None and the caller falls back to IGDB's aggregate.
"""

import re
import logging
import unicodedata

import requests
from config import Config
from utils import RateLimiter

logger = logging.getLogger(__name__)

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
_BASE = 'https://www.metacritic.com/game/'
_session = requests.Session()
_rate_limiter = RateLimiter(1 / 1.4)    # gentle — keeps Cloudflare clear
_RATING_RE = re.compile(r'"ratingValue"\s*:\s*"?(\d{1,3})')
_BLOCK_MARKERS = ('challenge-platform', 'Just a moment', 'cf-mitigated')


def _slug_candidates(name: str) -> list[str]:
    """Metacritic-style slug(s): strip accents, delete apostrophes, '&'→'and',
    non-alnum→'-'; plus a base-title variant dropping the subtitle."""
    n = unicodedata.normalize('NFD', name)
    n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')
    n = n.lower().replace('&', ' and ')
    n = re.sub(r"['’\"]", '', n)
    def slug(s): return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', s)).strip('-')
    full = slug(n)
    base = slug(re.split(r'[:–-]| - ', n, maxsplit=1)[0])
    return [s for s in dict.fromkeys((full, base)) if s]


def fetch_metascore(name: str) -> int | None:
    """Real Metacritic critic score (0–100) for `name`, or None. Never raises."""
    if not Config.METACRITIC_SCRAPE or not name:
        return None
    for slug in _slug_candidates(name):
        try:
            _rate_limiter.wait()
            r = _session.get(
                f'{_BASE}{slug}/',
                headers={'User-Agent': _UA, 'Accept': 'text/html',
                         'Accept-Language': 'en-US,en'},
                timeout=Config.REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning('Metacritic fetch failed %r: %s', slug, exc)
            return None
        if r.status_code in (403, 429, 503) or any(m in r.text[:4000] for m in _BLOCK_MARKERS):
            logger.warning('Metacritic blocked (%s) for %r', r.status_code, slug)
            return None
        if r.status_code != 200:
            continue                    # 404 → try the next slug variant
        m = _RATING_RE.search(r.text)
        if m:
            return int(m.group(1))
    return None
