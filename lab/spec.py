"""The specification: for each game of each reference episode, what it should be.

Written by the curator, independent of any variant — the right answer is the
same whatever chain produced the output being judged:
- `level`: consacré (the episode is about the game), évoqué (the game comes up),
  absent (it doesn't belong to the episode);
- `igdb`: the IGDB entry the game is — {id, name, slug, released} — or 'absent'
  when IGDB has no entry for it; None until decided. Irrelevant when absent.
- `added`: the curator added the game by hand (no source proposed it).

Git-tracked, reviewed in a PR; once a variant is ported the app replays it as
its acceptance test.
"""
import datetime
import json
import os
import pathlib
import tempfile

PATH = pathlib.Path(__file__).parent / 'spec.json'
LEVELS = ('consacré', 'évoqué', 'absent')


def load() -> list[dict]:
    with PATH.open(encoding='utf-8') as f:
        return json.load(f)['games']


def for_episode(guid: str) -> dict[str, dict]:
    return {g['game']: g for g in load() if g['episode'] == guid}


def update(episode, game: str, **fields) -> dict:
    """Set some of a game's fields (level, igdb, added); creates its entry."""
    if 'level' in fields and fields['level'] is not None and fields['level'] not in LEVELS:
        raise ValueError(f'level must be one of {", ".join(LEVELS)}')
    igdb = fields.get('igdb')
    if igdb not in (None, 'absent') and not (isinstance(igdb, dict) and isinstance(igdb.get('id'), int)):
        raise ValueError("igdb must be {id, name, …}, 'absent' or null")
    games = load()
    entry = next((g for g in games if g['episode'] == episode.slug and g['game'] == game), None)
    if entry is None:
        entry = {'episode': episode.slug, 'episodeTitle': episode.title, 'podcast': episode.podcast_id,
                 'game': game, 'level': None, 'igdb': None, 'added': False}
        games.append(entry)
    entry.update({k: v for k, v in fields.items() if k in ('level', 'igdb', 'added')})
    entry['at'] = datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')
    _write(games)
    return entry


def remove(episode, game: str) -> None:
    _write([g for g in load() if not (g['episode'] == episode.slug and g['game'] == game)])


def _write(games: list[dict]) -> None:
    """Atomically, sorted for a reviewable diff, keeping the file's mode and owner
    (the dev container writes as root)."""
    games = sorted(games, key=lambda g: (g['podcast'], g['episodeTitle'], g['game']))
    st = PATH.stat()
    fd, tmp = tempfile.mkstemp(dir=PATH.parent, suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'games': games}, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.chmod(tmp, st.st_mode)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, PATH)
