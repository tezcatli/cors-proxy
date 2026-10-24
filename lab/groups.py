"""The catalog's game page an IGDB entry belongs to — the curator's rule: a
game, its DLCs and expansions, its editions and ports, and its remasters are one
page; only a remake is a page of its own (IGDB category 8). Tests are measured
on that page, not on the exact entry: Dark Souls and Dark Souls: Remastered are
one game to the catalog.

Cached in the lab's database (`lab_groups`), filled by `python groups.py`
(IGDB, 4 req/s) for every entry judged or proposed; the measure reads the cache.

    docker compose -f docker-compose.dev.yml run --rm lab python groups.py
"""
import logging

import db

REMAKE = 8
_cache: dict[int, int] = {}


def _table(conn) -> None:
    conn.execute('CREATE TABLE IF NOT EXISTS main.lab_groups (igdb_id INTEGER PRIMARY KEY, group_id INTEGER)')


def parent(game: dict) -> int | None:
    """The entry a game is one page with, by the rule — None for a page of its own."""
    category = game.get('category') if game.get('category') is not None else (game.get('game_type') or {}).get('id', 0)
    vp = game.get('version_parent')
    if isinstance(vp, dict) and vp.get('id'):
        return vp['id']
    pg = game.get('parent_game')
    if category != REMAKE and isinstance(pg, dict) and pg.get('id'):
        return pg['id']
    return None


def page(igdb_id: int | None) -> int | None:
    """The page of an entry, from the cache (the entry itself when not cached)."""
    if igdb_id is None:
        return None
    if not _cache:
        with db.get_db() as conn:
            _table(conn)
            _cache.update({r['igdb_id']: r['group_id'] for r in conn.execute('SELECT * FROM main.lab_groups')})
    return _cache.get(igdb_id, igdb_id)


def _resolve(igdb_id: int) -> int:
    """Up the parents, by the rule, from IGDB (a few levels at most)."""
    import igdb
    seen = [igdb_id]
    while len(seen) < 5:
        rows = igdb._post(f'{igdb._FIELDS}where id = {int(seen[-1])}; limit 1;')
        up = parent(rows[0]) if rows else None
        if up is None or up in seen:
            break
        seen.append(up)
    return seen[-1]


def fill(ids) -> None:
    with db.get_db() as conn:
        _table(conn)
        known = {r['igdb_id'] for r in conn.execute('SELECT igdb_id FROM main.lab_groups')}
    todo = sorted({i for i in ids if i and i not in known})
    logging.info('%d entries to place', len(todo))
    for i in todo:
        g = _resolve(i)
        with db.get_db() as conn:
            conn.execute('INSERT OR REPLACE INTO main.lab_groups VALUES (?, ?)', (i, g))
        if g != i:
            logging.info('%s → %s', i, g)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    import server
    import spec
    from variants import fiche_versions
    ids = {g['igdb']['id'] for g in spec.load() if isinstance(g.get('igdb'), dict)}
    for guid in spec._read()['episodes']:
        ep = server._find(guid)
        if ep is None:   # a show set aside: its judgments stay, its feed is gone
            continue
        for variant in fiche_versions.ALL:
            ids |= {t['igdb']['id'] for t in variant.run(ep)['tests'] if t.get('igdb')}
    fill(ids)


if __name__ == '__main__':
    main()
