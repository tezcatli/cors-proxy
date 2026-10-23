"""Draw episodes into reference.json, stratified: per show, its history split
in three by date, `--per-tier` drawn at random from each — transcribed ones,
not already in. Reproducible for a seed.

    docker compose -f docker-compose.dev.yml run --rm lab python draw.py --set contrôle --seed 2027

The 54 « référence » episodes are those the chain was tuned on; a « contrôle »
set, never seen while tuning, is what says whether the chain holds.
"""
import argparse
import datetime
import json
import pathlib
import random

HERE = pathlib.Path(__file__).parent
TIERS = ('début', 'milieu', 'récent')


def draw(episodes, have: set[str], seed: int, per_tier: int) -> list:
    """[(episode, tier label)]: per show, `per_tier` per third of its history."""
    rng = random.Random(seed)
    by_show: dict[str, list] = {}
    for e in episodes:
        if e.slug not in have:
            by_show.setdefault(e.podcast_id, []).append(e)
    out = []
    for show, eps in sorted(by_show.items()):
        eps.sort(key=lambda e: e.pub_ts or 0)
        for i, tier in enumerate(TIERS):
            part = eps[i * len(eps) // 3:(i + 1) * len(eps) // 3]
            years = [datetime.datetime.fromtimestamp(part[j].pub_ts, datetime.UTC).year for j in (0, -1)]
            out += [(e, f'{tier} ({years[0]}–{years[1]})') for e in rng.sample(part, min(per_tier, len(part)))]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--set', required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--per-tier', type=int, default=2)
    args = parser.parse_args()
    import snapshot
    snapshot.load()
    import feeds
    import transcribe
    path = HERE / 'reference.json'
    ref = json.loads(path.read_text())
    have = {e['guid'] for e in ref['episodes']}
    rows = transcribe.rows()
    done = [e for e in feeds.all_episodes() if (r := rows.get(e.slug)) and r.model]
    for e, tier in draw(done, have, args.seed, args.per_tier):
        ref['episodes'].append({'guid': e.slug, 'title': e.title, 'podcast': e.podcast_id,
                                'why': f'{args.set} : {tier}', 'set': args.set})
        print(e.podcast_id, tier, '|', e.title)
    for e in ref['episodes']:
        e.setdefault('set', 'référence')
    path.write_text(json.dumps(ref, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
