"""The lab: what the pipeline makes of an episode, and the curator's judgment of it.

While the reading pipeline is being defined (which games an episode is about, at
which level, on which IGDB entry), the curator judges its real output, episode by
episode, in the dev app. Each judgment says what *should* be — consacré (the
episode is about the game), évoqué (the game comes up), absent (it doesn't belong
to the episode), or mauvaise-fiche (the right game, the wrong IGDB entry) — so it
stays a reference case whatever the pipeline produces next. The judgments live in
lab/judgments.json, git-tracked like corrections.json, and writable only where
that file is (dev): the lab is a dev-time activity.
"""
import json
import os
import pathlib
import tempfile

import catalog_state as state
import llm
import transcribe
from db import utcnow
from feeds import CRITIQUE_KINDS, _as_chapter
from models import Episode
from podcasts import PODCAST_BY_ID
from rss import find_chapter_for_game
from utils import make_slug

_PATH = pathlib.Path(__file__).parent / 'lab' / 'judgments.json'

VERDICTS = ('consacré', 'évoqué', 'absent', 'mauvaise-fiche')


def enabled() -> bool:
    return os.access(_PATH, os.W_OK)


def _load() -> list[dict]:
    with _PATH.open(encoding='utf-8') as f:
        return json.load(f)['judgments']


def _write(judgments: list[dict]) -> None:
    """Atomically, sorted for a reviewable diff, keeping the file's mode and owner
    (as corrections._write does: the dev container writes as root)."""
    judgments = sorted(judgments, key=lambda j: (j['podcast'], j['episodeTitle'], j['game']))
    st = _PATH.stat()
    fd, tmp = tempfile.mkstemp(dir=_PATH.parent, suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'judgments': judgments}, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.chmod(tmp, st.st_mode)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, _PATH)


def _sections(episode: Episode) -> list[dict] | None:
    row = transcribe.rows().get(episode.slug)
    if not (row and row.model):
        return None
    return llm.read_transcript(transcribe.reading_input(episode, row.model))


def _source(episode: Episode, mention, read: bool) -> str:
    if mention.read:
        return 'lecture'
    if PODCAST_BY_ID[episode.podcast_id].games_by_llm:
        return 'lecture' if read else 'description'
    return 'titre'


def episode_view(episode: Episode) -> dict:
    """Every game the pipeline sees in `episode` — the ones it attaches to the
    episode, and the ones its reading finds but doesn't attach — with what decided
    it (source, kind, minutes), the IGDB entry it lands on, and the judgment."""
    sections = _sections(episode)
    by_game: dict[str, list[dict]] = {}
    for s in sections or []:
        if s['game'] and not s['ad']:
            by_game.setdefault(make_slug(s['game']), []).append(s)
    judged = {j['game']: j for j in _load() if j['episode'] == episode.slug}

    def evidence(name: str) -> dict:
        groups = list(by_game.values())
        chapters = [_as_chapter(g[0], g[0]['game']) for g in groups]
        hit = find_chapter_for_game(name, chapters)
        if hit is None:
            return {}
        group = groups[chapters.index(hit)]
        best = max(group, key=lambda s: (s['kind'] in CRITIQUE_KINDS, s['end'] - s['start']))
        return {'kind': best['kind'], 'start': best['start'],
                'minutes': round(sum(s['end'] - s['start'] for s in group) / 60, 1),
                'verdict': (best['opinion'] or {}).get('verdict'), 'readName': best['game'],
                '_key': make_slug(best['game'])}

    rows, seen = [], set()
    for mention in episode.games:
        ev = evidence(mention.name)
        seen.add(ev.pop('_key', None))
        game = state.game_index.get(make_slug(mention.name))
        entry = state.entry(game, episode) if game else None
        rows.append({'game': mention.name, 'attached': True,
                     'source': _source(episode, mention, sections is not None),
                     'igdb': ({'slug': entry.igdb_slug, 'name': entry.name,
                               'released': (entry.data or {}).get('released')}
                              if entry and entry.igdb_slug else None),
                     **ev, 'judgment': judged.get(mention.name, {}).get('verdict')})
    for key, group in by_game.items():
        if key in seen:
            continue
        name = group[0]['game']
        ev = evidence(name)
        ev.pop('_key', None)
        rows.append({'game': name, 'attached': False, 'source': 'lecture', 'igdb': None,
                     **ev, 'judgment': judged.get(name, {}).get('verdict')})
    rows.sort(key=lambda r: (not r['attached'], -(r.get('minutes') or 0)))
    return {'episode': episode.slug, 'title': episode.title, 'podcast': episode.podcast_id,
            'read': sections is not None, 'games': rows}


def judge(episode: Episode, game: str, verdict: str | None, igdb_slug: str | None) -> None:
    """Record what `game` should be in `episode` (None withdraws the judgment)."""
    judgments = [j for j in _load() if not (j['episode'] == episode.slug and j['game'] == game)]
    if verdict is not None:
        judgments.append({'episode': episode.slug, 'episodeTitle': episode.title,
                          'podcast': episode.podcast_id, 'game': game, 'verdict': verdict,
                          'igdbSlug': igdb_slug, 'at': utcnow().isoformat(timespec='seconds')})
    _write(judgments)
