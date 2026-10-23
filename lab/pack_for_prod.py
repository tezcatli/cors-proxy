"""Pack, for prod, what the lab produced and the ported chain needs — so prod
never transcribes, reads or resolves the history again (`tools/push_lab_data.py`
loads it, `push-lab-data.sh` ships it):

- transcripts: every one of the snapshot (dev transcribed the history);
- readings: the lab's readings by the current transcript prompt;
- answers: one per question the ported catalog asks (`catalog_state.asked`,
  curators' pins and searches left alone): the lab's chosen resolution (fiches
  v1) when it decided it, else the answer the snapshot has — each brought onto
  its catalog page by the app's rule (`igdb._resolve_canonical`: a remaster
  joins its game, a remake stands apart), with that game's data (unenriched:
  prod's sweep scrapes Metacritic and HowLongToBeat as usual).

    docker compose -f docker-compose.dev.yml run --rm lab python pack_for_prod.py  → data/prod-pack.json.gz
"""
import gzip
import json
import logging
import pathlib
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

HERE = pathlib.Path(__file__).parent
OUT = HERE / 'data' / 'prod-pack.json.gz'


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    logging.getLogger('feeds').setLevel(logging.ERROR)
    import server  # noqa: F401  (the snapshot, the ported catalog)
    import catalog_state as state
    import db
    import fiches
    import igdb
    import llm

    with db.get_db() as conn:
        transcripts = [list(r) for r in conn.execute(
            'SELECT guid, model, segments, duration, cost FROM snapshot.transcripts WHERE segments IS NOT NULL')]
        readings = [list(r) for r in conn.execute(
            'SELECT key, task, version, input, answer, model, created_at FROM main.lab_llm_cache '
            "WHERE task = 'transcript' AND version = ?", (llm._TRANSCRIPT_V,))]
    logging.info('%d transcripts, %d readings', len(transcripts), len(readings))

    chosen: dict[str, tuple[int | None, str | None]] = {}
    for key, q in state.asked().items():
        if q.kind != 'name':
            continue
        decided, fiche = fiches.lookup(q.name, SimpleNamespace(podcast_id=q.podcast_id, pub_ts=q.dated), 1)
        if decided:
            chosen[key] = (fiche and fiche['id'], 'llm')
        elif (r := state.resolutions.get(key)) is not None and r.igdb_id:
            chosen[key] = (r.igdb_id, r.method)
    logging.info('%d answers (%d from the lab\'s resolution)', len(chosen),
                 sum(1 for i, m in chosen.values() if m == 'llm'))

    ids = sorted({i for i, _ in chosen.values() if i})
    with ThreadPoolExecutor(8) as pool:   # IGDB's 4 req/s, shared
        results = dict(zip(ids, pool.map(lambda i: igdb.fetch_by_id(i), ids)))
    now = db.utcnow().isoformat()
    answers, games = [], {}
    for key, (i, method) in chosen.items():
        res = results.get(i) if i else None
        if i and res is None:
            logging.warning('IGDB has no %s any more (%s): left to prod', i, key)
            continue
        answers.append([key, res.id if res else None, int(res.is_child) if res else 0, now, method])
        if res:
            games[res.id] = [res.id, res.slug, res.name, json.dumps(res.data, ensure_ascii=False), now, 0]
    logging.info('%d answers on %d games', len(answers), len(games))

    with gzip.open(OUT, 'wt', encoding='utf-8') as f:
        json.dump({'transcripts': transcripts, 'readings': readings, 'answers': answers,
                   'games': list(games.values())}, f, ensure_ascii=False)
    logging.info('→ %s (%.0f MB)', OUT, OUT.stat().st_size / 1e6)


if __name__ == '__main__':
    main()
