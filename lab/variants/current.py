"""The app's chain as it stands: what it attaches to an episode, from the
snapshot's readings and resolutions. The reference every other variant is
measured against first."""
import difflib

import catalog_state as state
import llm
import transcribe
from feeds import CRITIQUE_KINDS, _as_chapter
from podcasts import PODCAST_BY_ID
from rss import find_chapter_for_game
from utils import make_slug, norm

NAME = 'current'

# What a row says when the reading has nothing on the game (not read yet, or a
# name the reading doesn't use): every field present, so a page never guesses.
_NO_EVIDENCE = {'kind': None, 'start': None, 'end': None, 'minutes': None, 'verdict': None, 'at': None}


def chapter_spans(episode, sections: list[dict] | None) -> list[dict]:
    """The episode's chapters with their end — the next one's start; the last
    ends with the reading, when there is one — and their length."""
    chapters = episode.chapters
    last = sections[-1]['end'] if sections else None
    spans = []
    for i, c in enumerate(chapters):
        end = chapters[i + 1].timestamp_seconds if i + 1 < len(chapters) else last
        spans.append({'title': c.title, 'start': c.timestamp_seconds, 'end': end,
                      'minutes': round((end - c.timestamp_seconds) / 60, 1) if end else None})
    return spans


def _near_chapter(name: str, spans: list[dict]) -> dict | None:
    """A chapter whose title is close to `name` — «Tinikin» for Tinykin — only
    to show where to listen; the chain's own matching is left as it is."""
    titles = [norm(s['title']) for s in spans]
    close = difflib.get_close_matches(norm(name), titles, n=1, cutoff=0.8)
    return spans[titles.index(close[0])] if close else None


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
        return key, {'kind': best['kind'], 'start': best['start'], 'end': best['end'], 'at': 'section',
                     'minutes': round(sum(s['end'] - s['start'] for s in group) / 60, 1),
                     'verdict': (best['opinion'] or {}).get('verdict')}

    spans = chapter_spans(episode, sections)
    rows, seen = [], set()
    for mention in episode.games:
        key, ev = evidence(mention.name)
        seen.add(key)
        if ev['start'] is None:
            # Nothing read on it: its chapter is where to listen.
            span = next((c for c in spans if c['start'] == mention.timestamp_seconds), None) \
                if mention.timestamp else None
            at = 'chapitre'
            if span is None:
                span, at = _near_chapter(mention.name, spans), 'chapitre approché'
            if span:
                ev = {**ev, 'start': span['start'], 'end': span['end'], 'minutes': span['minutes'], 'at': at}
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
    return {'read': sections is not None, 'games': rows, 'chapters': spans,
            'sections': [s for s in sections or [] if not s['ad']]}
