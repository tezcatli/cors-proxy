"""Answer the IGDB questions of the reference episodes' games that have no
answer — the games the lab's own readings found, which prod never asked — or
an open one (no candidate fitted: IGDB adds games, the app asks those again
too), with the app's resolver (IGDB, then the LLM), into the lab's cache
(`data/lab.db`, see snapshot.py). A question answered with a game is left as
prod answered it.

    docker compose -f docker-compose.dev.yml run --rm lab python resolve.py [--all] [--jobs N]
    docker compose -f docker-compose.dev.yml run --rm lab python resolve.py --fiches [--all] [--jobs N]

`--fiches` instead decides, with the resolution variant (`fiches.py`), the
entry of every test `cinq_minutes` proposes. `--all`: every transcribed
episode (`targets.py`), not just the reference ones. N at a time (4).

Needs OPENROUTER_API_KEY (and the IGDB credentials of backend_secrets.env).
Restart the lab's server afterwards: it loads the answers at start.
"""
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor

import snapshot
import targets


def _pool(jobs: int, fn, items) -> None:
    """`fn` over `items`, `jobs` at a time — IGDB's 4 req/s are shared by all
    threads (igdb's rate limiter), the LLM calls run side by side."""
    def safe(item):
        try:
            fn(item)
        except Exception as exc:   # one question failing isn't the run's
            logging.warning('Failed %r: %s', item, exc)
    with ThreadPoolExecutor(jobs) as pool:
        list(pool.map(safe, items))


def _fiches(guids, jobs: int, version: int) -> None:
    import fiches
    import server   # the episodes as the pages see them
    from variants import cinq_minutes
    todo = {}
    for guid in guids:
        ep = server._find(guid)
        if ep is None:
            continue
        for t in cinq_minutes.run(ep)['tests']:
            if not fiches.lookup(t['game'], ep, version)[0]:
                todo.setdefault(fiches._key(t['game'], ep, version), (t['game'], ep))
    logging.info('%d entries to decide', len(todo))

    def decide(item):
        name, ep = item
        f = fiches.decide(name, ep, version)
        logging.info('%s → %s', name, f and f'{f["name"]} ({f["released"]})')
    _pool(jobs, decide, list(todo.values()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--fiches', action='store_true', help="the tests' entries, by the resolution variant")
    parser.add_argument('--all', action='store_true', help='every transcribed episode, not just the reference ones')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--version', type=int, help='the resolution version (fiches.VERSIONS; default fiches.DEFAULT)')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    import llm
    if not llm.enabled():
        raise SystemExit('OPENROUTER_API_KEY is not set')
    if args.fiches:
        import server  # noqa: F401  (loads the snapshot)
        import fiches
        _fiches(targets.guids(args.all), args.jobs, args.version or fiches.DEFAULT)
        return
    snapshot.load()
    import catalog_state as state
    import resolver
    from questions import question_for
    from utils import make_slug

    todo = {}
    for guid in targets.guids(args.all):
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

    def answer(item):
        q, name = item
        resolver.resolve(q, enrich=False)
        with state.lock:
            r = state.resolutions.get(q.key)
            g = r and r.igdb_id and state.games.get(r.igdb_id)
        logging.info('%s → %s', name, g.name if g else 'none fits')
    _pool(args.jobs, answer, list(todo.values()))


if __name__ == '__main__':
    main()
