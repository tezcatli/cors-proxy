"""HowLongToBeat lookup for a game's main-story completion time.

Best-effort: HLTB has no official API (the `howlongtobeatpy` lib wraps an
unofficial, rotating endpoint), so every failure path returns None and the caller
falls back to IGDB. Rate-limited gently since it runs across the catalog on the
resolution sweep.
"""

import logging

from utils import RateLimiter

logger = logging.getLogger(__name__)

try:
    from howlongtobeatpy import HowLongToBeat
except Exception:                       # lib missing / import error
    HowLongToBeat = None

_rate_limiter = RateLimiter(1 / 1.2)    # gentle — runs across the whole catalog


def fetch_time_to_beat(name: str, year=None) -> int | None:
    """Main-story hours for `name` from HowLongToBeat, or None. Never raises.

    Picks the best result by (same release year, then similarity); ignores weak
    matches (similarity < 0.4) to avoid wrong games.
    """
    if HowLongToBeat is None or not name:
        return None
    try:
        _rate_limiter.wait()
        results = HowLongToBeat().search(name)
    except Exception as exc:
        logger.warning('HLTB lookup failed for %r: %s', name, exc)
        return None
    if not results:
        return None

    def rank(e):
        yr = getattr(e, 'release_world', None)
        same_year = 1 if (year and yr and str(yr) == str(year)) else 0
        return (same_year, getattr(e, 'similarity', 0) or 0)

    best = max(results, key=rank)
    if (getattr(best, 'similarity', 0) or 0) < 0.4:
        return None
    hours = getattr(best, 'main_story', 0) or 0
    return round(hours) if hours and hours > 0 else None
