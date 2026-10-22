"""`cinq_minutes`, each test on the entry the resolution variant (`fiches.py`)
gives it — once decided (`python resolve.py --fiches`)."""
import fiches
from variants import cinq_minutes

NAME = 'fiches_v2'


def run(episode) -> dict:
    out = cinq_minutes.run(episode)
    tests = []
    for t in out['tests']:
        decided, fiche = fiches.lookup(t['game'], episode)
        tests.append({**t, 'igdb': fiche} if decided else t)
    return {**out, 'tests': tests}
