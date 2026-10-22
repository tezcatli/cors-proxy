"""The app's chain as it stands: what it attaches to an episode, from the
snapshot's readings and resolutions. The reference every other variant is
measured against first."""
import catalog_state as state
import llm
import transcribe
from feeds import CRITIQUE_KINDS, _as_chapter
from podcasts import PODCAST_BY_ID
from rss import find_chapter_for_game
from utils import make_slug

NAME = 'current'

# What a row says when the reading has nothing on the game (not read yet, or a
# name the reading doesn't use): every field present, so a page never guesses.
_NO_EVIDENCE = {'kind': None, 'start': None, 'minutes': None, 'verdict': None, 'at': None}


def _sections(episode) -> list[dict] | None:
    row = transcribe.rows().get(episode.slug)
    if not (row and row.model):
        return None
    return llm.read_transcript(transcribe.reading_input(episode, row.model))


def _source(episode, mention, read: bool) -> str:
    if mention.read:
        return 'lecture'
    if PODCAST_BY_ID[episode.podcast_id].games_by_llm:
        return 'lecture' if read else 'description'
    return 'titre'


def run(episode) -> dict:
    """Every game the chain sees in `episode`: attached (on the game's page) or
    only read, with what decided it and the IGDB entry it lands on — and the
    reading's sections, to see what it rests on."""
    sections = _sections(episode)
    groups: dict[str, list[dict]] = {}
    for s in sections or []:
        if s['game'] and not s['ad']:
            groups.setdefault(make_slug(s['game']), []).append(s)
    keys = list(groups)
    chapters = [_as_chapter(groups[k][0], groups[k][0]['game']) for k in keys]

    def evidence(name: str) -> tuple[str | None, dict]:
        hit = find_chapter_for_game(name, chapters)
        if hit is None:
            return None, dict(_NO_EVIDENCE)
        key = keys[chapters.index(hit)]
        group = groups[key]
        best = max(group, key=lambda s: (s['kind'] in CRITIQUE_KINDS, s['end'] - s['start']))
        return key, {'kind': best['kind'], 'start': best['start'], 'at': 'section',
                     'minutes': round(sum(s['end'] - s['start'] for s in group) / 60, 1),
                     'verdict': (best['opinion'] or {}).get('verdict')}

    rows, seen = [], set()
    for mention in episode.games:
        key, ev = evidence(mention.name)
        seen.add(key)
        if ev['start'] is None and mention.timestamp:
            # Nothing read on it: its chapter is where to listen.
            ev = {**ev, 'start': mention.timestamp_seconds, 'at': 'chapitre'}
        game = state.game_index.get(make_slug(mention.name))
        entry = state.entry(game, episode) if game else None
        rows.append({'game': mention.name, 'level': 'consacré',
                     'source': _source(episode, mention, sections is not None),
                     'igdb': ({'slug': entry.igdb_slug, 'name': entry.name,
                               'released': (entry.data or {}).get('released')}
                              if entry and entry.igdb_slug else None), **ev})
    for key in keys:
        if key not in seen:
            _, ev = evidence(groups[key][0]['game'])
            rows.append({'game': groups[key][0]['game'], 'level': None, 'source': 'lecture',
                         'igdb': None, **ev})
    rows.sort(key=lambda r: (r['level'] is None, -(r.get('minutes') or 0)))
    return {'read': sections is not None, 'games': rows,
            'sections': [s for s in sections or [] if not s['ad']]}
