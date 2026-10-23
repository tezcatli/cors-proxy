"""The app as it stands, read from its catalog — what a listener gets: the
episode's appearances, the catalog's exclusions included (trailers, the
palmarès formats), each test at its start and on its IGDB entry. Once a chain
is ported, `python freeze.py --check` proves the app gives back what it froze."""
import catalog_state as state
import critiques
from podcasts import PODCAST_BY_ID
from rss import is_game_catalog_excluded
from utils import make_slug
from variants.current import _test_fiche, chapters, _reading

NAME = 'app'


def run(episode) -> dict:
    reading = _reading(episode)
    with state.lock:
        shown = state.episode_index.get(episode.slug)
        games = [(m, state.game_index.get(make_slug(m.name))) for m in shown.games] if shown else []
    excluded = shown is None or is_game_catalog_excluded(shown.title) or critiques.palmares(
        PODCAST_BY_ID[shown.podcast_id], shown.title)
    tests = [] if excluded else [
        {'game': m.name, 'start': m.timestamp_seconds, 'end': None, 'minutes': None,
         'verdict': (m.critique or {}).get('verdict'), 'igdb': _test_fiche(m, game, shown)[0]}
        for m, game in games]
    return {'chapters': chapters(shown or episode, reading[-1]['end'] if reading else None), 'tests': tests}
