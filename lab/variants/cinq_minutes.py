"""Only what is in scope (`scope.py`): the games the title names, and those the
episode spends at least five minutes on. On top of `sans_bande_annonce`."""
import scope
from variants import current, sans_bande_annonce

NAME = 'cinq_minutes'


def run(episode) -> dict:
    out = sans_bande_annonce.run(episode)
    ok = scope.in_scope(episode, current._reading(episode))
    return {**out, 'tests': [t for t in out['tests'] if ok(t['game'])]}
