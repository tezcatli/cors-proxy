"""The shows whose every episode is about one game (or saga) — the one its
title names — know their test before anything is read: it is that game, over
the whole episode, and nothing else the reading comes across (Dragon Age II,
Inquisition in a Dragon Age: Origins episode). Every other show as `current`.
"""
from judge import same
from variants import current

NAME = 'un_jeu'

# Each episode is about the one game its title names; a property of the show,
# to become a `podcasts.Podcast` attribute when ported.
ONE_GAME = {'fin-du-game'}


def _title_game(episode) -> str | None:
    proposed = episode.proposed if getattr(episode, 'proposed', None) is not None else episode.games
    return next((m.name for m in proposed if not m.read), None)


def run(episode) -> dict:
    out = current.run(episode)
    name = _title_game(episode) if episode.podcast_id in ONE_GAME else None
    if name is None:
        return out
    # Its entry and the hosts' opinion as `current` has them; its extent, the
    # whole episode.
    found = next((t for t in out['tests'] if same(t['game'], name)), {})
    chapters = out['chapters']
    start = chapters[0]['start'] if chapters else 0
    end = chapters[-1]['end'] if chapters else None
    test = {'game': name, 'start': start, 'end': end, 'minutes': end and round((end - start) / 60),
            'verdict': found.get('verdict'), 'igdb': found.get('igdb')}
    return {**out, 'tests': [test]}
