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
- a game the title names is one when the reading finds it — a special's title
  isn't a game, « Le 500e épisode en public » — unless the reading heard it
  only without a critique (« Nine Lives », Kassovitz's game project in the
  news);
- a show whose every episode is about one game (Fin du Game) holds the title's
  game, over the whole episode, and nothing else the reading comes across;
- a show's palmarès formats, known by their titles (`Podcast.palmares_titles`),
  hold no test even when the reading calls each entry a review.

A test starts where its critique does — its longest critique section, or the
critique sections before it that only ads part from it (an ad break cuts a
review in two, not into two tests), never a teaser before the intro — and goes
on over the sections on the game after it (`span`): its duration, shown on the
game's page. A one-game show's test runs to the end of the reading.

Two names are one game when they are spelled alike (`same`) or, both having an
IGDB answer, when the answers are one catalog page — a title names « Wolfenstein »
or « Zelda », the reading « Wolfenstein: The Old Blood »; « Broken Sword 5 » and
« Broken Age » share a word, not a game. Only when one has no answer (two games
in one name, an answer still to come) do the words decide, numbers apart. A game
is never two pages. The names whose answers matter (`identify`: the title's and
the reading's critiques) are asked by the catalog like its own
(`catalog_state.asked`); a name only in the news is one game with another by
its spelling alone.
"""
import difflib
import functools
import re
from collections.abc import Callable

from models import Chapter, Episode, GameMention
from rss import find_chapter_for_game
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


def identify(podcast, episode: Episode, sections: list[dict]) -> list[str]:
    """The names whose IGDB answers tell the episode's games apart: the ones its
    title proposed and the ones its reading critiques or ranks."""
    if podcast.one_game:
        return []
    proposed = [m.name for m in episode.proposed or [] if not m.read]
    judged = [s['game'] for s in sections if s['game'] and not s['ad'] and s['kind'] in _JUDGED]
    return list(dict.fromkeys(proposed + judged))


def select(podcast, episode: Episode, sections: list[dict],
           page: Callable[[str], int | None] = lambda name: None) -> list[GameMention]:
    """The episode's tests, from the games its title proposed (`episode.proposed`)
    and its reading (`sections`), by the rules above; `page(name)` is the catalog
    page a name's answer is on, None while it has none."""
    on = [s for s in sections if s['game'] and not s['ad']]
    proposed = [m for m in episode.proposed or [] if not m.read]
    titled = [] if podcast.games_by_llm else [m.name for m in proposed]
    if podcast.one_game and titled:
        # Named as the title names it (« Astrobot », whatever the reading wrote),
        # with the verdict the reading gave it.
        first = episode.chapters[0].timestamp_seconds if episode.chapters else 0
        game = GameMention(titled[0], _ts(first), first, critique=_critique(_on(titled[0], on)))
        if sections:
            game.duration_seconds = max(int(max(s['end'] for s in sections)) - first, 0) or None
        return [] if _dropped(game.name, sections) else [game]
    tests = []
    for g in _games([m.name for m in proposed], on, identify(podcast, episode, sections), page):
        if not _is_test(g, titled=g['proposed'] in titled):
            continue
        mention = next((m for m in proposed if m.name == g['proposed']), None) \
            or GameMention(g['name'], None, 0, read=True)
        at, end = span(g['sections'], sections)
        mention.timestamp, mention.timestamp_seconds = _ts(at), int(at)
        mention.duration_seconds = int(end - at)
        mention.critique = _critique(g['sections'])
        tests.append(mention)
    return tests


def _games(proposed: list[str], sections: list[dict], identified: list[str], page) -> list[dict]:
    """[{names, proposed (the title's name, or None), name (the test's), sections}],
    one per game."""
    names = list(dict.fromkeys([*proposed, *(s['game'] for s in sections)]))
    pages = {n: page(n) if n in identified else None for n in names}
    root = {n: n for n in names}
    held = {n: {pages[n]} - {None} for n in names}   # a game is one page

    def find(n):
        while root[n] != n:
            n = root[n]
        return n

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ra, rb = find(a), find(b)
            if ra != rb and len(held[ra] | held[rb]) <= 1 and _one(a, b, pages, identified):
                root[rb] = ra
                held[ra] |= held[rb]
    games: dict[str, dict] = {}
    for n in names:
        g = games.setdefault(find(n), {'names': [], 'proposed': None, 'sections': []})
        g['names'].append(n)
        if n in proposed and g['proposed'] is None:
            g['proposed'] = n
    for s in sections:
        games[find(s['game'])]['sections'].append(s)
    for g in games.values():
        # The title's name, else one with an answer: words can't tell « Assassin's
        # Creed » from « Assassin's Creed: Brotherhood », an answer they chose
        # would be a wrong one.
        g['name'] = g['proposed'] or next((n for n in g['names'] if pages[n]), g['names'][0])
    return list(games.values())


def _one(a: str, b: str, pages: dict, identified: list[str]) -> bool:
    if same(a, b):
        return True
    if pages[a] and pages[b]:
        return pages[a] == pages[b]
    # A name only in the news is its spelling: its minutes are no critique's.
    if a not in identified or b not in identified:
        return False
    return _numbers(a) == _numbers(b) and find_chapter_for_game(a, [Chapter('', 0, b, b)]) is not None


def _is_test(g: dict, titled: bool) -> bool:
    """A proposed game needs a section of it; the title's is vetoed when heard only
    without a critique; any other is a test from five minutes of a critique."""
    kinds = {s['kind'] for s in g['sections']}
    if not kinds or kinds == {'ranking'}:
        return False
    if titled:
        return bool(kinds & _JUDGED)
    if not g['proposed'] and not kinds & CRITIQUE_KINDS:
        return False
    return max(s['end'] - s['start'] for s in g['sections']) >= MIN_SECONDS


def span(sections: list[dict], reading: list[dict]) -> tuple[float, float]:
    """Where a test on these `sections` of the `reading` starts and ends. It
    starts at its longest critique section, or the first of the critique
    sections before it that only ads part from it; at its first section without
    a critique. It ends with the last section on the game that follows on from
    there, ads aside."""
    judged = [s for s in sections if s['kind'] in _JUDGED]
    main = max(judged, key=lambda s: s['end'] - s['start']) if judged else sections[0]
    at = next(i for i, r in enumerate(reading) if r is main)
    first, last = main, main
    if judged:
        ids = {id(s) for s in judged}
        for s in reversed(reading[:at]):
            if id(s) in ids:
                first = s
            elif not s['ad']:
                break
    ids = {id(s) for s in sections}
    for s in reading[at + 1:]:
        if id(s) in ids:
            last = s
        elif not s['ad']:
            break
    return first['start'], last['end']


def _critique(sections: list[dict]) -> dict | None:
    """The hosts' opinion of the game: its longest critique's."""
    critiques = [s for s in sections if s['kind'] in CRITIQUE_KINDS]
    return max(critiques, key=lambda s: s['end'] - s['start'])['opinion'] if critiques else None


def _on(name: str, sections: list[dict]) -> list[dict]:
    return [s for s in sections if s['game'] and not s['ad'] and same(s['game'], name)]


def _dropped(name: str, sections: list[dict]) -> bool:
    """A one-game show's game is no test when only ever a palmarès' entry, or heard
    but never critiqued."""
    kinds = {s['kind'] for s in _on(name, sections)}
    return kinds == {'ranking'} or (bool(kinds) and not kinds & _JUDGED)


def _ts(seconds: float) -> str:
    s = int(seconds)
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'
