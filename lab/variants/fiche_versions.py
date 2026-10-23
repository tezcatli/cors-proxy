"""`formats` with each resolution version side by side — `app` the app's own
answers, then fiches.VERSIONS — to choose the resolution by its score on every
judged test, not by one case."""
import fiches
from variants import cinq_minutes, formats


class WithFiches:
    def __init__(self, version: int | None):
        self.version = version
        self.NAME = f'formats_v{version}' if version else 'formats_app'

    def run(self, episode) -> dict:
        out = cinq_minutes.run(episode)
        if formats.palmares(episode):
            return {**out, 'tests': []}
        if self.version is None:
            return out
        tests = []
        for t in out['tests']:
            decided, fiche = fiches.lookup(t['game'], episode, self.version)
            tests.append({**t, 'igdb': fiche} if decided else {**t, 'igdb': None})
        return {**out, 'tests': tests}


ALL = [WithFiches(None), *(WithFiches(v) for v in fiches.VERSIONS)]
