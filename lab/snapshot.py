"""Prod's data, as pulled into dev (./pull-prod-data.sh), opened read-only.

The lab reads the snapshot and never writes it, so a lab bug can't touch the dev
database. What the lab asks the LLM itself — readings of reference episodes prod
hasn't read, a variant's other prompt — goes to its own cache, `data/lab.db`:
every connection the app's modules open is that file, with the snapshot attached
read-only, and `llm_cache` a view over both whose writes land in the lab's. The
app's modules are used as libraries and never modified: to them it is one
database.
"""
import contextlib
import functools
import logging
import pathlib
import sqlite3

import db

_connect = sqlite3.connect
LAB_DB = pathlib.Path(__file__).parent / 'data' / 'lab.db'

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS lab_llm_cache (key TEXT PRIMARY KEY, task TEXT, version INTEGER, "
    "input TEXT, answer TEXT, model TEXT, created_at TEXT)",
)
# Per connection: the view and its write trigger are temporary, so the
# snapshot's own llm_cache is what « snapshot » means inside them.
_VIEW = (
    "CREATE TEMP VIEW llm_cache AS SELECT key, task, version, input, answer, model, created_at "
    "FROM main.lab_llm_cache UNION ALL SELECT key, task, version, input, answer, model, created_at "
    "FROM snapshot.llm_cache",
    "CREATE TEMP TRIGGER llm_cache_write INSTEAD OF INSERT ON llm_cache BEGIN "
    "INSERT OR REPLACE INTO main.lab_llm_cache VALUES (NEW.key, NEW.task, NEW.version, NEW.input, "
    "NEW.answer, NEW.model, NEW.created_at); END",
)


@contextlib.contextmanager
def _lab():
    LAB_DB.parent.mkdir(exist_ok=True)
    conn = _connect(f'file:{LAB_DB}', uri=True)  # so the snapshot attaches by URI, read-only
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('ATTACH DATABASE ? AS snapshot', (f'file:{db.DB_PATH}?mode=ro',))
        for sql in (*_SCHEMA, *_VIEW):
            conn.execute(sql)
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
