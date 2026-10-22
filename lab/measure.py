"""A chain's score against the specification, on the validated episodes — the
only ones that say what's missing.

    docker compose -f docker-compose.dev.yml run --rm lab python measure.py [VARIANT] [--compare OTHER]

Each test the chain proposes or the curator expects is one case:
- `juste`: a test, proposed, on the right IGDB entry;
- `mauvaise fiche`: a test, proposed, on another entry (or on one when IGDB has none);
- `faux`: proposed, but not a test;
- `manquant`: a test the chain doesn't propose;
- `à juger`: proposed, never judged (the episode is back to « à revoir »);
- `fiche indécise`: a test, proposed, whose entry nobody chose yet;
- `hors champ`: judged a test, but out of scope (`scope.py`: under five minutes
  and not in the title) — neither expected nor wrong. Never one the curator
  added: the reading that missed it can't say how long it is.

Stop criterion: no `faux`, no `mauvaise fiche`, and at least 90 % of the
expected tests proposed.
"""
import argparse

import judge
import scope
import spec

FOUND = ('juste', 'mauvaise fiche', 'fiche indécise')
THRESHOLD = 0.9


def _fiche_outcome(chosen, proposed) -> str:
    if chosen is None:
        return 'fiche indécise'
    if chosen == 'absent':
        return 'juste' if proposed is None else 'mauvaise fiche'
    return 'juste' if proposed and proposed['id'] == chosen['id'] else 'mauvaise fiche'


def outcomes(rows: list[dict], in_scope=lambda game: True) -> list[dict]:
    """judge.rows of one validated episode → its cases: {game, outcome, start,
    proposed, chosen}. A game judged « pas un test » that isn't proposed is no
    case: the chain is right to leave it out."""
    cases = []
    for r in rows:
        sp, shown = r['spec'] or {}, r['shown']
        # A test the curator added is the reading's miss: its minutes can't be the
        # reading's, so it is in scope.
        if sp.get('test') is True and not sp.get('added') and not in_scope(r['game']):
            outcome = 'hors champ'
        elif shown and sp.get('test') is True:
            outcome = _fiche_outcome(sp.get('igdb'), shown['igdb'])
        elif shown and sp.get('test') is False:
            outcome = 'faux'
        elif shown:
            outcome = 'à juger'
        elif sp.get('test') is True:
            outcome = 'manquant'
        else:
            continue
        cases.append({'game': r['game'], 'outcome': outcome, 'start': judge.start(r),
                      'proposed': shown and shown['igdb'], 'chosen': sp.get('igdb')})
    return cases


def summary(cases: list[dict]) -> dict:
    """Counts per outcome, the share of expected tests found, and the verdict."""
    counts = {k: sum(c['outcome'] == k for c in cases)
              for k in ('juste', 'mauvaise fiche', 'fiche indécise', 'faux', 'manquant', 'à juger', 'hors champ')}
    expected = sum(counts[k] for k in (*FOUND, 'manquant'))
    found = sum(counts[k] for k in FOUND) / expected if expected else None
    return {**counts, 'expected': expected, 'found': found,
            'met': bool(expected) and counts['faux'] == 0 and counts['mauvaise fiche'] == 0
                   and found >= THRESHOLD}


def score(run, find) -> list[dict]:
    """[{guid, title, cases}] for every validated episode, `run` being a
    variant's run(episode) and `find` guid → episode."""
    out = []
    for guid in spec._read()['episodes']:
        ep = find(guid)
        if ep is None:
            continue
        rows = judge.rows(run(ep)['tests'], spec.for_episode(guid))
        from variants import current   # the episode's reading: what scope measures minutes on
        out.append({'guid': guid, 'title': ep.title,
                    'cases': outcomes(rows, scope.in_scope(ep, current._reading(ep)))})
    return out


def _print(name: str, episodes: list[dict]) -> None:
    s = summary([c for e in episodes for c in e['cases']])
    found = f"{s['found']:.0%}" if s['found'] is not None else '—'
    print(f"{name}: {len(episodes)} épisodes validés · {s['expected']} tests attendus · trouvés {found} · "
          f"faux {s['faux']} · mauvaise fiche {s['mauvaise fiche']} · manquants {s['manquant']} · "
          f"à juger {s['à juger']} · fiche indécise {s['fiche indécise']} · hors champ {s['hors champ']} → "
          f"{'critère atteint' if s['met'] else 'critère non atteint'}")
    for e in episodes:
        for c in e['cases']:
            if c['outcome'] not in ('juste', 'hors champ'):
                print(f"  {c['outcome']:15} {e['title'][:50]:50} {c['game']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('variant', nargs='?', default='current')
    parser.add_argument('--compare')
    args = parser.parse_args()
    import server   # loads the snapshot
    from variants import VARIANTS
    runs = {n: score(VARIANTS[n].run, server._find) for n in filter(None, (args.variant, args.compare))}
    for n, eps in runs.items():
        _print(n, eps)
    if args.compare:
        a, b = (runs[args.variant], runs[args.compare])
        print(f'\nCe qui change de {args.variant} à {args.compare} :')
        for ea, eb in zip(a, b):
            before = {c['game']: c['outcome'] for c in ea['cases']}
            after = {c['game']: c['outcome'] for c in eb['cases']}
            for game in [*before, *(g for g in after if g not in before)]:
                if before.get(game) != after.get(game):
                    print(f"  {ea['title'][:50]:50} {game}: {before.get(game, '—')} → {after.get(game, '—')}")


if __name__ == '__main__':
    main()
