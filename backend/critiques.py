"""Which tests an episode holds — what the catalog is a base of: a video game
the hosts played and judge in the episode.

Defined in the lab (`lab/`) against the curator's judgments — 143 tests over
three sets, the last never seen while defining: no false test, every test found
— and ported here as one step of the catalog build (`select`, called by
`feeds._apply_readings`); `tests/test_reference.py` replays those judgments.
The reading describes each section (`llm.KINDS`), the rules decide:

- a critique is a review or impressions — an entry in a best-of, an awards show
  or a ranking isn't one;
- a game the reading finds is a test when the hosts critique it and spend at
  least five minutes on it: shorter, a test can't be told from a mention (1–2
  minute demos were tests in one episode and not in another);
- a game the title names is one, unless the reading heard it without a critique
  (« Nine Lives », Kassovitz's game project in the news): silence is no veto;
- a show whose every episode is about one game (Fin du Game) holds the title's
  game, over the whole episode, and nothing else the reading comes across;
- a show's palmarès formats, known by their titles (`Podcast.palmares_titles`),
  hold no test even when the reading calls each entry a review.

A test starts where its critique does — its longest critique section, not a
teaser before the intro — and goes on over the sections on the game after it.
"""
import difflib
import functools
import re

from models import Episode, GameMention
from utils import norm, norm_key

CRITIQUE_KINDS = {'review', 'impressions'}
MIN_SECONDS = 5 * 60
# What a test's start is looked for in: its critique, or its entry in a ranking
# (a title's game reviewed inside a best-of).
_JUDGED = CRITIQUE_KINDS | {'ranking'}

_ROMAN = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7',
          'viii': '8', 'ix': '9', 'x': '10'}


def _numbers(name: str) -> list[str]:
    """A name's numbers, roman numerals read as digits: a sequel is another game."""
    return [_ROMAN.get(w, w) for w in norm(name).split() if w.isdigit() or w in _ROMAN]


@functools.lru_cache(maxsize=None)
def same(a: str, b: str) -> bool:
    """One game under two spellings: the same letters but for spaces and
    punctuation (« Astro Bot »), or close (« Tinikin ») with the same numbers —
    « Gears of War 2 » and « Gears of War » are two games."""
    ka, kb = norm_key(a), norm_key(b)
    if ka == kb:
        return True
    return _numbers(a) == _numbers(b) and difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.85


def palmares(podcast, title: str) -> bool:
    """Whether the episode is one of the show's palmarès formats."""
    return bool(podcast.palmares_titles and re.search(podcast.palmares_titles, norm(title)))


def _on(name: str, sections: list[dict]) -> list[dict]:
    return [s for s in sections if s['game'] and not s['ad'] and same(s['game'], name)]


def start(name: str, sections: list[dict]) -> float | None:
    """Where a test starts: its longest critique section — the run of sections on
    the game it lies in goes on after it, only another game ending it — or its
    first section without one; None when the reading has none on it."""
    runs, run = [], None
    for s in sections:
        if s['game'] and same(s['game'], name):
            if run is None:
                run = []
                runs.append(run)
            run.append(s)
        elif s['game']:
            run = None
    judged = [s for r in runs for s in r if s['kind'] in _JUDGED]
    if judged:
        return max(judged, key=lambda s: s['end'] - s['start'])['start']
    return runs[0][0]['start'] if runs else None


def select(podcast, episode: Episode, sections: list[dict]) -> list[GameMention]:
    """The episode's tests, from the games its title proposed and its reading
    found (`episode.games`, critiques attached), by the rules above."""
    titled = [] if podcast.games_by_llm else [m.name for m in episode.proposed or [] if not m.read]
    games = list(episode.games)
    if podcast.one_game and titled:
        # Named as the title names it (« Astrobot », whatever the reading wrote),
        # with the verdict the reading gave it.
        read = next((m for m in games if same(m.name, titled[0])), None)
        first = episode.chapters[0].timestamp_seconds if episode.chapters else 0
        game = GameMention(titled[0], _ts(first), first, critique=read.critique if read else None)
        return [] if _dropped(game.name, sections, titled=True) else [game]
    tests = [m for m in games if not _dropped(m.name, sections, any(same(m.name, n) for n in titled))]
    for m in tests:
        at = start(m.name, sections)
        if at is not None:
            m.timestamp, m.timestamp_seconds = _ts(at), int(at)
        elif m.timestamp is None:
            chapter = next((c for c in episode.chapters if same(c.title, m.name)), None)
            if chapter:
                m.timestamp, m.timestamp_seconds = chapter.timestamp, chapter.timestamp_seconds
    return tests


def _dropped(name: str, sections: list[dict], titled: bool) -> bool:
    """Not a test: only ever a palmarès' entry; for the title's game, heard by the
    reading but never critiqued; for a game the reading found, under five
    minutes."""
    on = _on(name, sections)
    kinds = {s['kind'] for s in on}
    if kinds == {'ranking'}:
        return True
    if titled:
        return bool(kinds) and not kinds & _JUDGED
    return max((s['end'] - s['start'] for s in on), default=0) < MIN_SECONDS


def _ts(seconds: float) -> str:
    s = int(seconds)
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'
