"""The title proposes, the reading may veto: a game the episode's title names
is no test when the reading heard it and found no critique of it — only news,
a mention (« Nine Lives », Kassovitz's game project in the news). A title game
the reading has no section on stays: silence is no veto. On top of `formats`
with the resolution chosen by the score (fiches v1)."""
import scope
from feeds import CRITIQUE_KINDS
from judge import same
from variants import current, fiche_versions

NAME = 'titre_critique'
VERSION = 1   # the resolution, chosen by its score
_BASE = next(v for v in fiche_versions.ALL if v.version == VERSION)


def run(episode) -> dict:
    out = _BASE.run(episode)
    reading = current._reading(episode) or []
    named = scope.title_games(episode)

    def vetoed(name: str) -> bool:
        if not any(same(name, n) for n in named):
            return False
        kinds = {s['kind'] for s in reading if s['game'] and not s['ad'] and same(s['game'], name)}
        return bool(kinds) and not kinds & CRITIQUE_KINDS

    return {**out, 'tests': [t for t in out['tests'] if not vetoed(t['game'])]}
