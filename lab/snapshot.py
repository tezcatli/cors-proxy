"""Prod's data, as pulled into dev (./pull-prod-data.sh), opened read-only.

The lab reads the snapshot and never writes it: every connection the app's
modules open is read-only, so a lab bug can't touch the dev database. The app's
modules are used as libraries — the feed parser, the catalog, the cached
readings — and never modified.
"""
import contextlib
import logging
import sqlite3

import db

_connect = sqlite3.connect


@contextlib.contextmanager
def _read_only():
    conn = _connect(f'file:{db.DB_PATH}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


db.get_db = _read_only


def load() -> None:
    """Build the app's catalog in memory from the snapshot and the live feeds —
    what the app shows now. The reconciliation that would prune the database is
    skipped: the snapshot is read-only."""
    import catalog_state as state
    import feeds
    logging.getLogger('feeds').setLevel(logging.ERROR)
    state.reconcile = lambda complete: None
    state.load_igdb_cache_from_db()
    feeds.refresh_feed()
