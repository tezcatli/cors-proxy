"""HowLongToBeat lookup for a game's main-story completion time.

Best-effort: HLTB has no official API (the `howlongtobeatpy` lib wraps an
unofficial, rotating endpoint), so every failure path returns None and the caller
falls back to IGDB. Rate-limited gently since it runs across the catalog on the
resolution sweep.
"""

import threading
import time
import logging

logger = logging.getLogger(__name__)

try:
    from howlongtobeatpy import HowLongToBeat
except Exception:                       # lib missing / import error
    HowLongToBeat = None

_MIN_INTERVAL = 1.2                      # seconds between calls (gentle)
_lock = threading.Lock()
_last = 0.0


def _throttle() -> None:
    global _last
    with _lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()


def fetch_time_to_beat(name: str, year=None) -> int | None:
    """Main-story hours for `name` from HowLongToBeat, or None. Never raises.

    Picks the best result by (same release year, then similarity); ignores weak
    matches (similarity < 0.4) to avoid wrong games.
    """
    if HowLongToBeat is None or not name:
        return None
    try:
        _throttle()
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
