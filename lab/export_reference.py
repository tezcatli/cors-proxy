"""Export the judged episodes for the app's acceptance test
(backend/tests/test_reference.py): what the app's catalog build is given — the
title, the games it proposes, the episode's own chapters, its reading's sections
— and what they should give: the curator's judgments, and the frozen chain's
tests (frozen.json).

    docker compose -f docker-compose.dev.yml run --rm lab python export_reference.py
"""
import json
import pathlib

import freeze

OUT = pathlib.Path('/backend/tests/fixtures/reference.json')


def main() -> None:
    import server
    import measure
    import scope
    import spec
    from variants import current
    frozen = json.loads(freeze.PATH.read_text())['episodes']
    episodes = []
    for guid, chain in frozen.items():
        if spec.validated(guid) is None:
            continue
        ep = server._find(guid)
        reading = current._reading(ep) or []
        judged = spec.for_episode(guid)
        ok = scope.in_scope(ep, reading)
        episodes.append({
            'guid': guid, 'podcast': ep.podcast_id, 'title': ep.title, 'pub_ts': ep.pub_ts,
            'proposed': [{'name': m.name, 'timestamp': m.timestamp, 'seconds': m.timestamp_seconds}
                         for m in (ep.proposed if ep.proposed is not None else ep.games) if not m.read],
            'chapters': [] if ep.chapters_read else
                        [{'title': c.title, 'timestamp': c.timestamp, 'seconds': c.timestamp_seconds,
                          'game': c.game_name} for c in ep.chapters],
            'sections': [{k: s[k] for k in ('title', 'game', 'kind', 'start', 'end', 'ad')} for s in reading],
            'tests': sorted(n for n, g in judged.items() if g['test'] and (g.get('added') or ok(n))),
            'not_tests': sorted(n for n, g in judged.items() if g['test'] is False),
            'set': measure.sets().get(guid, 'référence'),
            'chain': [{'game': t['game'], 'start': t['start']} for t in chain],
        })
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'episodes': episodes}, ensure_ascii=False, indent=1) + '\n')
    print(f'{len(episodes)} episodes → {OUT}')


if __name__ == '__main__':
    main()
