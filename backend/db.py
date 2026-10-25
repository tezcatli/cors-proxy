"""SQLite at `data/users.db` (WAL), its schema and its migrations.

Tables: `users`, `invitations`, `reset_tokens` (auth — never leave prod, see
`tools/prod_data.py`); `resolutions` (one answer per question, keyed by
`questions.Question.key`) and `igdb_games` (one row per game, keyed by
`igdb_id`) — the IGDB cache is two tables because it holds two decisions with
different keys and lifetimes, with no foreign key between them since an answer
may briefly point at a game being re-fetched; `llm_cache` (see `llm.py`);
`transcripts` (see `transcribe.py`, never loaded into memory).

`init_db` creates what is missing, so a deploy or `pull-prod-data.sh` only needs
a restart; a change of shape adds its migration here, and drops it once every
database has run it.
"""
import sqlite3
import os
import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'users.db')


def utcnow():
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


@contextmanager
def get_db():
    """Yield a SQLite connection, committing on success and always closing.

    Mirrors the commit/rollback semantics of using a raw connection as a
    context manager, but additionally closes the connection so file
    descriptors are not leaked while waiting for GC finalisation.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT    NOT NULL,
                is_admin      INTEGER  DEFAULT 0,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS reset_tokens (
                token      TEXT    PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invitations (
                token      TEXT     PRIMARY KEY,
                email      TEXT     NOT NULL COLLATE NOCASE,
                is_admin   INTEGER  DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                used_at    DATETIME
            );

            -- The answer to each question (questions.Question.key): which IGDB
            -- game it is. igdb_id NULL = no candidate fits, the question is open.
            CREATE TABLE IF NOT EXISTS resolutions (
                question    TEXT PRIMARY KEY,
                igdb_id     INTEGER,
                is_child    INTEGER NOT NULL DEFAULT 0,
                decided_at  TEXT    NOT NULL,
                method      TEXT,
                titles      TEXT,
                candidates  TEXT,
                attempts    INTEGER NOT NULL DEFAULT 0,
                last_error  TEXT,
                retry_at    TEXT
            );
            -- One row per IGDB game, shared by all the appearances resolved to it.
            CREATE TABLE IF NOT EXISTS igdb_games (
                igdb_id    INTEGER PRIMARY KEY,
                igdb_slug  TEXT    NOT NULL,
                name       TEXT    NOT NULL,
                data       TEXT    NOT NULL,
                fetched_at TEXT    NOT NULL,
                enriched   INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS llm_cache (
                key        TEXT PRIMARY KEY,
                task       TEXT NOT NULL,
                version    INTEGER NOT NULL,
                input      TEXT NOT NULL,
                answer     TEXT NOT NULL,
                model      TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            -- llm.ask(any_version=True): an older prompt's answer for this input.
            CREATE INDEX IF NOT EXISTS llm_cache_task_input ON llm_cache (task, input);

            -- One row per episode (its guid) the ingestion has tried: the
            -- transcript once it succeeded (`segments`, JSON [[start, end, text]];
            -- NULL until then), what it cost, and the failure backoff of the
            -- step that failed last (transcribing or reading).
            CREATE TABLE IF NOT EXISTS transcripts (
                guid        TEXT PRIMARY KEY,
                model       TEXT,
                segments    TEXT,
                duration    REAL,
                cost        REAL,
                created_at  TEXT,
                attempts    INTEGER NOT NULL DEFAULT 0,
                last_error  TEXT,
                retry_at    TEXT
            );
        """)
