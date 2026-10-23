"""The specification: what each reference episode really holds — its tests. A
test is a video game the hosts played and judge in the episode; the goal is a
base of them. It is the truth any chain is measured against, independent of
every chain (the app's included: the app follows).

Written by the curator on a chain's proposals:
- `test`: True, the episode tests this video game; False, it doesn't (news, a
  mention, a board game…);
- `igdb`: the IGDB entry the test is — {id, name, slug, released, coverImageId}
  — or 'absent' when IGDB has none; None while undecided;
- `added`: the curator added it as missing (no chain proposed it), and `start`,
  the chapter it was added in;
- `limit`: why the entry is one no chain can be expected to find — the
  episode doesn't say it (Dark Souls: Remastered, inferred from the show's
  theme). Measured apart, it doesn't hold the stop criterion back.

And per episode, `validated`: the curator has seen it whole — every proposed
test not judged otherwise is right, on the entry proposed, and nothing else is
missing. Only a validated episode is measured.

Git-tracked, reviewed in a PR; once a variant is ported the app replays it as
its acceptance test.
"""
import datetime
import json
import os
import pathlib
import tempfile

PATH = pathlib.Path(__file__).parent / 'spec.json'


def _read() -> dict:
    with PATH.open(encoding='utf-8') as f:
        doc = json.load(f)
    return {'episodes': doc.get('episodes', {}), 'games': doc['games']}


def load() -> list[dict]:
    return _read()['games']


def validated(guid: str) -> dict | None:
    return _read()['episodes'].get(guid)


def for_episode(guid: str) -> dict[str, dict]:
    return {g['game']: g for g in load() if g['episode'] == guid}


def update(episode, game: str, **fields) -> dict:
    """Set some of a game's fields (test, igdb, added, start); creates its entry."""
    if not (fields.get('test') is None or isinstance(fields['test'], bool)):
        raise ValueError('test must be true, false or null')
    igdb = fields.get('igdb')
    if igdb not in (None, 'absent') and not (isinstance(igdb, dict) and isinstance(igdb.get('id'), int)):
        raise ValueError("igdb must be {id, name, …}, 'absent' or null")
    doc = _read()
    entry = _entry(doc['games'], episode, game)
    entry.update({k: v for k, v in fields.items() if k in ('test', 'igdb', 'added', 'start')})
    _write(doc)
    return entry


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')


def _entry(games: list[dict], episode, game: str) -> dict:
    entry = next((g for g in games if g['episode'] == episode.slug and g['game'] == game), None)
    if entry is None:
        entry = {'episode': episode.slug, 'episodeTitle': episode.title, 'podcast': episode.podcast_id,
                 'game': game, 'test': None, 'igdb': None, 'added': False}
        games.append(entry)
    entry['at'] = _now()
    return entry


def validate(episode, proposed: dict[str, dict | None], variant: str) -> None:
    """The curator has seen the episode whole: each proposed test ({name: its
    proposed entry}) not judged yet is a test, and a test whose entry wasn't
    chosen is on the one proposed — a judgment already made stands — and the
    episode is validated, in one write."""
    doc = _read()
    for game, fiche in proposed.items():
        entry = next((g for g in doc['games'] if g['episode'] == episode.slug and g['game'] == game), None)
        if entry is None or entry['test'] is None:
            entry = _entry(doc['games'], episode, game)
            entry['test'] = True
        if entry['test'] and entry.get('igdb') is None and fiche:
            entry['igdb'] = fiche
    doc['episodes'][episode.slug] = {'title': episode.title, 'validated': _now(), 'variant': variant}
    _write(doc)


def rename(episode, game: str, new: str) -> dict:
    """A test added by hand, under another name (a typo, the chapter's title
    kept as is)."""
    doc = _read()
    mine = [g for g in doc['games'] if g['episode'] == episode.slug]
    entry = next((g for g in mine if g['game'] == game), None)
    if entry is None:
        raise ValueError(f'no {game!r} in this episode')
    if any(g['game'] == new for g in mine if g is not entry):
        raise ValueError(f'{new!r} is already judged in this episode')
    entry['game'], entry['at'] = new, _now()
    _write(doc)
    return entry


def remove(episode, game: str) -> None:
    doc = _read()
    doc['games'] = [g for g in doc['games'] if not (g['episode'] == episode.slug and g['game'] == game)]
    _write(doc)


def _write(doc: dict) -> None:
    """Atomically, sorted for a reviewable diff, keeping the file's mode and owner
    (the dev container writes as root)."""
    games = sorted(doc['games'], key=lambda g: (g['podcast'], g['episodeTitle'], g['game']))
    episodes = dict(sorted(doc['episodes'].items(), key=lambda kv: kv[1]['title']))
    st = PATH.stat()
    fd, tmp = tempfile.mkstemp(dir=PATH.parent, suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'episodes': episodes, 'games': games}, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.chmod(tmp, st.st_mode)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, PATH)
