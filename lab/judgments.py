"""The curator's judgments: what each game *should* be in each reference episode.

consacré — the episode is about the game; évoqué — the game comes up in it;
absent — it doesn't belong to the episode; mauvaise-fiche — the right game, the
wrong IGDB entry. A judgment states the expected outcome, not an opinion of the
output, so it stays a reference case whatever a variant produces. Git-tracked,
reviewed in a PR; the app replays them as acceptance tests once a variant is
ported.
"""
import datetime
import json
import os
import pathlib
import tempfile

PATH = pathlib.Path(__file__).parent / 'judgments.json'
VERDICTS = ('consacré', 'évoqué', 'absent', 'mauvaise-fiche')


def load() -> list[dict]:
    with PATH.open(encoding='utf-8') as f:
        return json.load(f)['judgments']


def for_episode(guid: str) -> dict[str, dict]:
    return {j['game']: j for j in load() if j['episode'] == guid}


def judge(episode, game: str, verdict: str | None, igdb_slug: str | None) -> None:
    """Record what `game` should be in `episode`; None withdraws the judgment."""
    if verdict is not None and verdict not in VERDICTS:
        raise ValueError(f'verdict must be one of {", ".join(VERDICTS)}')
    kept = [j for j in load() if not (j['episode'] == episode.slug and j['game'] == game)]
    if verdict is not None:
        kept.append({'episode': episode.slug, 'episodeTitle': episode.title,
                     'podcast': episode.podcast_id, 'game': game, 'verdict': verdict,
                     'igdbSlug': igdb_slug,
                     'at': datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')})
    _write(kept)


def _write(judgments: list[dict]) -> None:
    """Atomically, sorted for a reviewable diff, keeping the file's mode and owner
    (the dev container writes as root)."""
    judgments = sorted(judgments, key=lambda j: (j['podcast'], j['episodeTitle'], j['game']))
    st = PATH.stat()
    fd, tmp = tempfile.mkstemp(dir=PATH.parent, suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'judgments': judgments}, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.chmod(tmp, st.st_mode)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, PATH)
