"""The app's chain as it stands, from the snapshot: what a listener gets for an
episode — the chapters its player shows, and the tests its catalog references
(each game with its IGDB entry). The reference every other variant is measured
against first."""
import functools

import catalog_state as state
import igdb
import llm
import transcribe
from corrections import find_by_podcast
from feeds import CRITIQUE_KINDS
from judge import same
from utils import make_slug

NAME = 'current'


def _reading(episode) -> list[dict] | None:
    row = transcribe.rows().get(episode.slug)
    if not (row and row.model):
        return None
    return llm.read_transcript(transcribe.reading_input(episode, row.model))


def chapters(episode, last_end: float | None) -> list[dict]:
    """The player's chapters, each with its end: the next one's start; the last
    ends with the reading, when there is one."""
    cs = episode.chapters
    return [{'start': c.timestamp_seconds, 'title': c.title,
             'end': cs[i + 1].timestamp_seconds if i + 1 < len(cs) else last_end}
            for i, c in enumerate(cs)]


def _fiche(entry) -> dict | None:
    if not (entry and entry.igdb_slug):
        return None
    data = entry.data or {}
    return {'id': entry.igdb_id, 'name': entry.name, 'slug': entry.igdb_slug,
            'released': data.get('released'), 'coverImageId': data.get('coverImageId')}


@functools.cache
def _pinned(igdb_id: int) -> dict | None:
    """A fiche pinned in corrections.json that the snapshot hasn't resolved — the
    app resolves it at its next start; the lab asks IGDB (once)."""
    r = igdb.fetch_by_id(igdb_id, canonical=False)
    return r and {'id': r.id, 'name': r.name, 'slug': r.slug, 'released': r.data.get('released'),
                  'coverImageId': r.data.get('coverImageId')}


def _test_fiche(mention, game, episode) -> tuple[dict | None, bool]:
    """(the test's IGDB entry, whether corrections.json decides it)."""
    pin = find_by_podcast(mention.name, episode.pub_ts, episode.podcast_id)
    fiche = _fiche(state.entry(game, episode) if game else None)   # takes the lock itself
    if pin and pin.get('igdb_id') and not (fiche and fiche['id'] == pin['igdb_id']):
        fiche = _pinned(pin['igdb_id'])
    return fiche, bool(pin and pin.get('igdb_id'))


def run(episode) -> dict:
    """{chapters, tests}: an episode the catalog leaves out references no test."""
    reading = _reading(episode)
    with state.lock:
        shown = state.episode_index.get(episode.slug)
        games = [(m, state.game_index.get(make_slug(m.name))) for m in shown.games] if shown else []
    spans = chapters(shown or episode, reading[-1]['end'] if reading else None)
    tests = []
    for m, game in games:
        fiche, corrected = _test_fiche(m, game, shown)
        extent = _extent(m.name, reading)
        tests.append({'game': m.name, 'start': extent['start'] if extent else _start(m, reading, spans),
                      'end': extent and extent['end'], 'minutes': extent and extent['minutes'],
                      'verdict': (m.critique or {}).get('verdict'), 'igdb': fiche, 'corrected': corrected})
    return {'chapters': spans, 'tests': tests}


def _extent(name: str, reading) -> dict | None:
    """The stretch of the episode a test covers, from the reading. It starts
    where the critique does — its longest critique section, not a teaser
    before the intro (« Violence and Trading Cards ») nor a set-up — and goes on
    over the sections on the game after it, which only a section on *another*
    game ends (an ad or a plug in the middle is cut out of the talk, not the
    end of it). {start, end, minutes on the game}."""
    runs, run = [], None
    for s in reading or []:
        if s['game'] and same(s['game'], name):
            if run is None:
                run = []
                runs.append(run)
            run.append(s)
        elif s['game']:
            run = None
    critiques = [(s, r) for r in runs for s in r if s['kind'] in CRITIQUE_KINDS]
    if not critiques and not runs:
        return None
    main, run = max(critiques, key=lambda sr: sr[0]['end'] - sr[0]['start']) if critiques else (runs[0][0], runs[0])
    rest = run[run.index(main):]
    return {'start': main['start'], 'end': rest[-1]['end'],
            'minutes': round(sum(s['end'] - s['start'] for s in rest) / 60)}


def _start(mention, reading, spans) -> float | None:
    """Where to listen to a test: its chapter as the app matched it, else — only
    to listen, the app's matching left as it is — the reading's section on it,
    or a chapter of a close name (« Tinikin » for Tinykin)."""
    if mention.timestamp or mention.read:
        return mention.timestamp_seconds
    hit = next((s for s in reading or [] if s['game'] and same(s['game'], mention.name)), None) \
        or next((c for c in spans if same(c['title'], mention.name)), None)
    return hit['start'] if hit else None

