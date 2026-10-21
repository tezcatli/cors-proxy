import datetime
import re
import threading
import time
import unicodedata
from html import unescape

from config import Config


def backoff(attempts: int) -> datetime.timedelta:
    """The delay before retry `attempts + 1` of something failing: the tick's
    interval, doubling, up to a day."""
    delay = datetime.timedelta(minutes=Config.RESOLVE_RETRY_MINUTES) * 2 ** (attempts - 1)
    return min(delay, datetime.timedelta(days=1))


class RateLimiter:
    """Blocking minimum-interval limiter shared by the outbound API clients
    (IGDB, Metacritic, HLTB): wait() sleeps as needed so calls are at least
    `1/rate` seconds apart. Thread-safe; in-process only (single-worker app)."""

    def __init__(self, rate: float):
        self._interval = 1.0 / rate
        self._last     = 0.0
        self._lock     = threading.Lock()

    def wait(self):
        with self._lock:
            wait = self._interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


def norm(s):
    s = unicodedata.normalize('NFD', s.lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def norm_key(s):
    return norm(s).replace(' ', '')

def make_slug(s):
    return norm(s).replace(' ', '-')


def plain_text(html: str | None) -> str:
    """An RSS description as plain text: tags dropped, entities decoded, spaces collapsed."""
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', html or ''))).strip()
