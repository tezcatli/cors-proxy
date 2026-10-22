"""Prod's data, as pulled into dev (./pull-prod-data.sh), opened read-only.

The lab reads the snapshot and never writes it, so a lab bug can't touch the dev
database. What the lab produces itself — readings of reference episodes prod
hasn't read, a variant's other prompt, the IGDB answers for the games those
readings find — goes to its own cache, `data/lab.db`: every connection the
app's modules open is that file, with the snapshot attached read-only, and each
produced table (`LAB_TABLES`) a view over both, the lab's row winning, whose
writes land in the lab's. The app's modules are used as libraries and never
modified: to them it is one database.
"""
import contextlib
import functools
import logging
import pathlib
import sqlite3

import db

_connect = sqlite3.connect
LAB_DB = pathlib.Path(__file__).parent / 'data' / 'lab.db'

# The tables the lab writes, by primary key.
LAB_TABLES = {'llm_cache': 'key', 'resolutions': 'question', 'igdb_games': 'igdb_id'}


def _overlay(conn, table: str, pk: str) -> None:
    """`table` as a temporary view over the lab's copy and the snapshot's — per
    connection, so « snapshot » inside it is this connection's attachment — and
    a trigger sending its writes to the lab's copy."""
    cols = [(r[1], r[2]) for r in conn.execute(f'PRAGMA snapshot.table_info({table})')]
    names = ', '.join(c for c, _ in cols)
    conn.execute(f'CREATE TABLE IF NOT EXISTS main.lab_{table} ('
                 + ', '.join(f'{c} {t}{" PRIMARY KEY" if c == pk else ""}' for c, t in cols) + ')')
    conn.execute(f'CREATE TEMP VIEW {table} AS SELECT {names} FROM main.lab_{table} UNION ALL '
                 f'SELECT {names} FROM snapshot.{table} WHERE {pk} NOT IN (SELECT {pk} FROM main.lab_{table})')
    conn.execute(f'CREATE TEMP TRIGGER {table}_write INSTEAD OF INSERT ON {table} BEGIN '
                 f'INSERT OR REPLACE INTO main.lab_{table} ({names}) VALUES '
                 f'({", ".join("NEW." + c for c, _ in cols)}); END')


@contextlib.contextmanager
def _lab():
    LAB_DB.parent.mkdir(exist_ok=True)
    conn = _connect(f'file:{LAB_DB}', uri=True)  # so the snapshot attaches by URI, read-only
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('ATTACH DATABASE ? AS snapshot', (f'file:{db.DB_PATH}?mode=ro',))
        for table, pk in LAB_TABLES.items():
            _overlay(conn, table, pk)
        yield conn
        conn.commit()
    finally:
        conn.close()


db.get_db = _lab


def load() -> None:
    """Build the app's catalog in memory from the snapshot and the live feeds —
    what the app shows now. The reconciliation that would prune the database is
    skipped: the snapshot is read-only."""
    import catalog_state as state
    import feeds
    import transcribe
    logging.getLogger('feeds').setLevel(logging.ERROR)
    state.reconcile = lambda complete: None
    # The snapshot's transcripts don't change while the lab runs; listing them
    # scans every transcript (0.2 s), once per episode shown otherwise.
    transcribe.rows = functools.cache(transcribe.rows)
    state.load_igdb_cache_from_db()
    feeds.refresh_feed()
