"""Prove the ported resolver: for every frozen test, the app's own resolver —
asked afresh, nothing stored — lands on the catalog page the chosen chain gave
it (`frozen.json`). Needs OPENROUTER_API_KEY; costs a few cents.

    docker compose -f docker-compose.dev.yml run --rm lab python check_resolution.py
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import freeze


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    import server
    import catalog_state as state
    import groups
    import llm
    import resolver
    from questions import question_for
    from utils import make_slug
    if not llm.enabled():
        raise SystemExit('OPENROUTER_API_KEY is not set')
    frozen = json.loads(freeze.PATH.read_text())['episodes']
    todo = []
    for guid, tests in frozen.items():
        ep = server._find(guid)
        for t in tests:
            if t['page'] is None:
                continue
            with state.lock:
                game = state.game_index.get(make_slug(t['game']))
            if game is None:
                print('no game in the catalog:', t['game'])
                continue
            todo.append((ep, t, question_for(game, ep)))

    def decide(item):
        ep, t, q = item
        d = resolver._decide(q, None, use_llm=True)
        return ep, t, d.result.id if d.result else None
    with ThreadPoolExecutor(8) as pool:
        done = list(pool.map(decide, todo))
    groups.fill({i for _, _, i in done if i})
    groups._cache.clear()
    same = 0
    for ep, t, got in done:
        if groups.page(got) == t['page']:
            same += 1
        else:
            print(f"≠ {ep.title[:50]} | {t['game']}: frozen page {t['page']}, app {got} → page {groups.page(got)}")
    print(f'{same} / {len(done)} tests on the same catalog page')


if __name__ == '__main__':
    main()
