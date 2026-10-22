"""Answer the IGDB questions of the reference episodes' games that have no
answer — the games the lab's own readings found, which prod never asked — or
an open one (no candidate fitted: IGDB adds games, the app asks those again
too), with the app's resolver (IGDB, then the LLM), into the lab's cache
(`data/lab.db`, see snapshot.py). A question answered with a game is left as
prod answered it.

    docker compose -f docker-compose.dev.yml run --rm lab python resolve.py
    docker compose -f docker-compose.dev.yml run --rm lab python resolve.py --fiches

`--fiches` instead decides, with the resolution variant (`fiches.py`), the
entry of every test `cinq_minutes` proposes in the reference episodes.

Needs OPENROUTER_API_KEY (and the IGDB credentials of backend_secrets.env).
Restart the lab's server afterwards: it loads the answers at start.
"""
import json
import logging
import pathlib
import sys

import snapshot

HERE = pathlib.Path(__file__).parent


def _fiches(guids) -> None:
    import fiches
    import server   # the episodes as the pages see them
    from variants import cinq_minutes
    for guid in guids:
        ep = server._find(guid)
        for t in cinq_minutes.run(ep)['tests']:
            if not fiches.lookup(t['game'], ep)[0]:
                f = fiches.decide(t['game'], ep)
                logging.info('%s → %s', t['game'], f and f'{f["name"]} ({f["released"]})')


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if '--fiches' in sys.argv:
        import llm
        if not llm.enabled():
            raise SystemExit('OPENROUTER_API_KEY is not set')
        _fiches([e['guid'] for e in json.loads((HERE / 'reference.json').read_text())['episodes']])
        return
    snapshot.load()
    import catalog_state as state
    import llm
    import resolver
    from questions import question_for
    from utils import make_slug
    if not llm.enabled():
        raise SystemExit('OPENROUTER_API_KEY is not set')

    guids = [e['guid'] for e in json.loads((HERE / 'reference.json').read_text())['episodes']]
    todo = {}
    for guid in guids:
        with state.lock:
            ep = state.episode_index.get(guid)
            games = [state.game_index.get(make_slug(m.name)) for m in ep.games] if ep else []
        for game in filter(None, games):
            q = question_for(game, ep)
            with state.lock:
                r = state.resolutions.get(q.key)
            if r is None or r.igdb_id is None:
                todo.setdefault(q.key, (q, game.name))
    logging.info('%d questions to answer', len(todo))
    for q, name in todo.values():
        resolver.resolve(q, enrich=False)
        with state.lock:
            r = state.resolutions.get(q.key)
            g = r and r.igdb_id and state.games.get(r.igdb_id)
        logging.info('%s → %s', name, g.name if g else 'none fits')


if __name__ == '__main__':
    main()
