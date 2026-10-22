"""An awards ceremony (« Les Silences d'or »), a best-of, a ranking is no test:
a game whose only sections are its entries in one isn't proposed. On top of
`un_jeu`."""
from judge import same
from variants import current, un_jeu

NAME = 'sans_palmares'


def run(episode) -> dict:
    out = un_jeu.run(episode)
    reading = current._reading(episode) or []

    def kinds(name: str) -> set:
        return {s['kind'] for s in reading if s['game'] and not s['ad'] and same(s['game'], name)}

    return {**out, 'tests': [t for t in out['tests'] if kinds(t['game']) != {'ranking'}]}
