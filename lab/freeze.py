"""Freeze what the chosen chain gives the judged episodes, before porting it:
once ported, `current` — the app as it stands — changes, and every variant
built on it with it; the port is proven by the app giving back exactly this.

    docker compose -f docker-compose.dev.yml run --rm lab python freeze.py      → frozen.json
    docker compose -f docker-compose.dev.yml run --rm lab python freeze.py --check

Per episode: its tests, each with its start and its catalog page (`groups.py`).
"""
import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).parent
PATH = HERE / 'frozen.json'


def outputs(run, find, guids) -> dict:
    import groups
    out = {}
    for guid in guids:
        ep = find(guid)
        if ep is None:
            continue
        out[guid] = sorted(({'game': t['game'], 'start': t['start'],
                             'page': groups.page(t['igdb']['id']) if t.get('igdb') else None}
                            for t in run(ep)['tests']), key=lambda t: t['game'])
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='compare the app as it stands to the frozen outputs')
    parser.add_argument('--variant', default=None)
    parser.add_argument('--tests-only', action='store_true', help='compare the tests, not their pages')
    args = parser.parse_args()
    import server
    import targets
    from variants import VARIANTS
    name = args.variant or ('app' if args.check else server.DEFAULT)
    now = outputs(VARIANTS[name].run, server._find, targets.guids())
    if not args.check:
        PATH.write_text(json.dumps({'variant': name, 'episodes': now}, ensure_ascii=False, indent=1) + '\n')
        print(f'{sum(len(v) for v in now.values())} tests of {len(now)} episodes frozen from {name}')
        return
    frozen = json.loads(PATH.read_text())['episodes']
    if args.tests_only:
        strip = lambda ts: [{'game': t['game'], 'start': t['start']} for t in ts]
        frozen = {g: strip(ts) for g, ts in frozen.items()}
        now = {g: strip(ts) for g, ts in now.items()}
    diff = 0
    for guid, tests in frozen.items():
        if now.get(guid) != tests:
            diff += 1
            ep = server._find(guid)
            show = lambda ts: [tuple(t.values()) for t in ts]
            print(f'≠ {ep.title[:60]}\n   frozen {show(tests)}\n   now    {show(now.get(guid, []))}')
    print(f'{len(frozen) - diff} / {len(frozen)} episodes identical')


if __name__ == '__main__':
    main()
