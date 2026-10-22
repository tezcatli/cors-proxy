"""What the curator judges an episode on: its structure, and every game any source
proposes for it — independent of any variant.

Sources: the title (as the app parses it), the description (the LLM's reading of
it, for the shows read that way), the chapters, the transcript's reading (every
section about a game, whatever its kind), and the games the curator added. The
same game named differently by two sources (« Tinikin », « Astro Bot ») is one
candidate.
"""
import difflib
import re

import catalog_state as state
import feeds
import llm
import transcribe
from podcasts import PODCAST_BY_ID
from rss import _is_non_game_chapter
from utils import make_slug, norm, norm_key

SOURCES = ('titre', 'description', 'chapitre', 'lecture', 'ajout')


def _reading(episode) -> list[dict] | None:
    row = transcribe.rows().get(episode.slug)
    if not (row and row.model):
        return None
    return llm.read_transcript(transcribe.reading_input(episode, row.model))


def _spans(chapters, last_end) -> list[dict]:
    out = []
    for i, c in enumerate(chapters):
        end = chapters[i + 1].timestamp_seconds if i + 1 < len(chapters) else last_end
        out.append({'start': c.timestamp_seconds, 'end': end, 'title': c.title,
                    'game': c.game_name, 'source': 'chapitre'})
    return out


def structure(episode, reading: list[dict] | None) -> list[dict]:
    """One timeline of the episode: the reading's sections when it is read (ads
    left out), its chapters otherwise. Each segment: start, end, title, game."""
    if reading:
        return [{'start': s['start'], 'end': s['end'], 'title': s['title'], 'game': s['game'],
                 'kind': s['kind'], 'source': 'lecture'} for s in reading if not s['ad']]
    return _spans(episode.chapters, None)


_ROMAN = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7',
          'viii': '8', 'ix': '9', 'x': '10'}


def _numbers(name: str) -> list[str]:
    """A name's numbers, roman numerals read as digits: a sequel is another game."""
    return [_ROMAN.get(w, w) for w in norm(name).split() if w.isdigit() or w in _ROMAN]


def _same(a: str, b: str) -> bool:
    """One game under two spellings: the same letters but for spaces and
    punctuation (« Astro Bot »), or close (« Tinikin ») with the same numbers —
    « Gears of War 2 » and « Gears of War » are two games."""
    ka, kb = norm_key(a), norm_key(b)
    if ka == kb:
        return True
    return _numbers(a) == _numbers(b) and difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.85


def group(proposals: list[tuple[str, str]]) -> list[dict]:
    """[(name, source)] → one candidate per game: {game, sources}, named after the
    first proposal (sources come in order of authority: title first)."""
    out: list[dict] = []
    for name, source in proposals:
        hit = next((c for c in out if any(_same(name, n) for n in c['names'])), None)
        if hit is None:
            out.append({'game': name, 'names': [name], 'sources': [source]})
        else:
            hit['names'].append(name)
            if source not in hit['sources']:
                hit['sources'].append(source)
    return out


# A show's recurring segments, which its chapters name but which are no game.
_SEGMENTS = re.compile(r'^(intro(duction)?|g[ée]n[ée]rique|conclusion|outro|actualit[ée]s?|les news|news|'
                       r'minute culturelle|courrier|le com des coms?|publicit[ée]|sponsor|'
                       r"et quand vous ne jouez pas|la chronique|bilan|questions?)\b", re.I)


def _game_chapters(chapters: list[dict]) -> list[dict]:
    """The chapters that may be a game. chapters.json marks its game chapters
    (`game`): when any chapter is marked, only those are; a description's
    chapters aren't marked, so its recurring segments are left out by name."""
    if any(c['game'] for c in chapters):
        return [c for c in chapters if c['game']]
    return [c for c in chapters if not _is_non_game_chapter(c['title'])
            and not _SEGMENTS.match(c['title'].strip())]


def _description_games(episode) -> list[str]:
    podcast = PODCAST_BY_ID[episode.podcast_id]
    payload = feeds._llm_episode(podcast, episode) if podcast.games_by_llm else None
    return (llm.reviewed_games(payload, cached_only=True, any_version=True) or []) if payload else []


def candidates(episode, added: list[str]) -> tuple[list[dict], list[dict], bool]:
    """(structure, candidates, read). Each candidate: game, sources, the segments
    it appears in, and the IGDB entry the app gives it now (None if not attached)."""
    reading = _reading(episode)
    chapters = _spans(episode.chapters, reading[-1]['end'] if reading else None)
    podcast = PODCAST_BY_ID[episode.podcast_id]
    # The title only proposes games for the shows whose titles the app parses; the
    # others' games come from the description or the reading, counted below.
    proposals = [] if podcast.games_by_llm else [
        (m.name, 'titre') for m in (episode.proposed if episode.proposed is not None
                                    else episode.games) if not m.read]
    proposals += [(n, 'description') for n in _description_games(episode)]
    if not episode.chapters_read:
        proposals += [(c['game'] or c['title'], 'chapitre') for c in _game_chapters(chapters)]
    proposals += [(s['game'], 'lecture') for s in reading or [] if s['game'] and not s['ad']]
    proposals += [(n, 'ajout') for n in added]
    out = group(proposals)

    segments = [*chapters, *([] if reading is None else structure(episode, reading))]
    for c in out:
        c['segments'] = sorted((s for s in segments
                                if any(_same(n, s['game'] or s['title']) for n in c['names'])),
                               key=lambda s: s['start'])
        game = next((state.game_index.get(make_slug(n)) for n in c['names']
                     if make_slug(n) in state.game_index), None)
        entry = state.entry(game, episode) if game else None
        c['appIgdb'] = ({'id': entry.igdb_id, 'name': entry.name, 'slug': entry.igdb_slug,
                         'released': (entry.data or {}).get('released'),
                         'coverImageId': (entry.data or {}).get('coverImageId')}
                        if entry and entry.igdb_slug else None)
        del c['names']
    return structure(episode, reading) or chapters, out, reading is not None
