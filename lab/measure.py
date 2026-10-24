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
- `limite connue`: a wrong entry the curator recorded as one no chain can find
  (`limit` in the spec: the episode doesn't say it) — counted apart;
- `hors champ`: judged a test, but out of scope (`scope.py`: under five minutes
  and not in the title) — neither expected nor wrong. Never one the curator
  added: the reading that missed it can't say how long it is.

- `début faux`: a test proposed whose start is more than a minute off the one
  the curator set (`start` in the spec) — counted beside the outcome, only
  where a start was set.

Stop criterion: no `faux`, no `mauvaise fiche`, no `début faux`, and at least
90 % of the expected tests proposed — judged on the « contrôle » set: the « référence »
episodes are those the chain was tuned on, its score there is optimistic.
"""
import argparse
import json
import pathlib

import groups
import judge
import scope
import spec

# The latest control set first: the verdict is its own — each earlier one
# was used to choose the chain, the reference set to tune it. « nouvelles
# émissions » is the shows added after the chain was frozen (ORIGAMI, ZQSD,
# The Game Informer Show; The Back Page's episodes left out with the show):
# their own verdict on the tests, never tuned on.
SETS = ('nouvelles émissions', 'contrôle 2', 'contrôle', 'référence')
FOUND = ('juste', 'mauvaise fiche', 'fiche indécise', 'limite connue')
THRESHOLD = 0.9
START_SECONDS = 60


def _fiche_outcome(chosen, proposed) -> str:
    """On the catalog's game page (`groups.py`), not the exact entry: a remaster
    proposed for the game judged is right — one page to the catalog."""
    if chosen is None:
        return 'fiche indécise'
    if chosen == 'absent':
        return 'juste' if proposed is None else 'mauvaise fiche'
    return 'juste' if proposed and groups.page(proposed['id']) == groups.page(chosen['id']) else 'mauvaise fiche'


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
            if outcome == 'mauvaise fiche' and sp.get('limit'):
                outcome = 'limite connue'
        elif shown and sp.get('test') is False:
            outcome = 'faux'
        elif shown:
            outcome = 'à juger'
        elif sp.get('test') is True:
            outcome = 'manquant'
        else:
            continue
        # Its start, where the curator set one on a test proposed: wrong a minute off.
        start = (None if not (shown and sp.get('test') is True and not sp.get('added') and sp.get('start') is not None)
                 else 'faux' if abs(shown['start'] - sp['start']) > START_SECONDS else 'juste')
        cases.append({'game': r['game'], 'outcome': outcome, 'start': judge.start(r), 'début': start,
                      'proposed': shown and shown['igdb'], 'chosen': sp.get('igdb')})
    return cases


def summary(cases: list[dict]) -> dict:
    """Counts per outcome, the share of expected tests found, and the verdict."""
    counts = {k: sum(c['outcome'] == k for c in cases)
              for k in ('juste', 'mauvaise fiche', 'fiche indécise', 'faux', 'manquant', 'à juger', 'hors champ',
                        'limite connue')}
    counts['début faux'] = sum(c.get('début') == 'faux' for c in cases)
    counts['débuts jugés'] = sum(c.get('début') is not None for c in cases)
    expected = sum(counts[k] for k in (*FOUND, 'manquant'))
    found = sum(counts[k] for k in FOUND) / expected if expected else None
    return {**counts, 'expected': expected, 'found': found,
            'met': bool(expected) and counts['faux'] == 0 and counts['mauvaise fiche'] == 0
                   and counts['début faux'] == 0 and found >= THRESHOLD}


def sets() -> dict[str, str]:
    """guid → the set its episode belongs to (reference.json)."""
    ref = json.loads((pathlib.Path(__file__).parent / 'reference.json').read_text())['episodes']
    return {e['guid']: e.get('set', 'référence') for e in ref}


def by_set(episodes: list[dict]) -> dict[str, dict]:
    """{set: summary of its episodes' cases}, in `SETS` order."""
    return {name: {**summary([c for e in episodes if e['set'] == name for c in e['cases']]),
                   'episodes': sum(e['set'] == name for e in episodes)} for name in SETS}


def score(run, find) -> list[dict]:
    """[{guid, title, set, cases}] for every validated episode, `run` being a
    variant's run(episode) and `find` guid → episode."""
    of = sets()
    out = []
    for guid in spec._read()['episodes']:
        ep = find(guid)
        if ep is None:
            continue
        rows = judge.rows(run(ep)['tests'], spec.for_episode(guid))
        from variants import current   # the episode's reading: what scope measures minutes on
        out.append({'guid': guid, 'title': ep.title, 'set': of.get(guid, 'référence'),
                    'cases': outcomes(rows, scope.in_scope(ep, current._reading(ep)))})
    return out


def _print(name: str, episodes: list[dict]) -> None:
    for set_name, s in by_set(episodes).items():
        _print_set(f'{name} [{set_name}]', s)
    for e in episodes:
        for c in e['cases']:
            if c['outcome'] not in ('juste', 'hors champ'):
                print(f"  {c['outcome']:15} {e['set'][:4]} {e['title'][:46]:46} {c['game']}")
            if c.get('début') == 'faux':
                print(f"  {'début faux':15} {e['set'][:4]} {e['title'][:46]:46} {c['game']}")


def _print_set(name: str, s: dict) -> None:
    found = f"{s['found']:.0%}" if s['found'] is not None else '—'
    print(f"{name}: {s['episodes']} épisodes validés · {s['expected']} tests attendus · trouvés {found} · "
          f"faux {s['faux']} · mauvaise fiche {s['mauvaise fiche']} · manquants {s['manquant']} · "
          f"à juger {s['à juger']} · fiche indécise {s['fiche indécise']} · hors champ {s['hors champ']} · "
          f"limite connue {s['limite connue']} · début faux {s['début faux']}/{s['débuts jugés']} → "
          f"{'critère atteint' if s['met'] else 'critère non atteint'}")


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
