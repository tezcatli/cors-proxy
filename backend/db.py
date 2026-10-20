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

            -- Which IGDB game each appearance is (podcast_slug = make_slug(name) +
            -- '-' + episode guid). igdb_id NULL = IGDB had no match.
            CREATE TABLE IF NOT EXISTS resolutions (
                slug           TEXT PRIMARY KEY,
                igdb_id        INTEGER,
                is_child       INTEGER NOT NULL DEFAULT 0,
                resolved_at    TEXT    NOT NULL,
                correction_sig TEXT    NOT NULL DEFAULT '',
                method         TEXT
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
        """)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'igdb_cache'").fetchone():
            _split_igdb_cache(conn)
        user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if 'is_admin' not in user_cols and user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        # Carries the admin grant from the invitation to the account it creates.
        inv_cols = {row[1] for row in conn.execute("PRAGMA table_info(invitations)")}
        if 'is_admin' not in inv_cols and inv_cols:
            conn.execute("ALTER TABLE invitations ADD COLUMN is_admin INTEGER DEFAULT 0")


def _split_igdb_cache(conn) -> None:
    """Migrate the legacy one-row-per-appearance `igdb_cache` into `resolutions`
    and `igdb_games`, then drop it. Each game keeps its best copy: an enriched one
    over the quick pass's, then the newest. A row without its game's data keeps
    its resolution, and the sweep fetches the game by id."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(igdb_cache)")}
    # Columns added over the table's life; NULL on rows from before them.
    sig      = 'correction_sig' if 'correction_sig' in cols else "''"
    enriched = 'enriched'       if 'enriched'       in cols else '1'
    method   = 'method'         if 'method'         in cols else 'NULL'
    is_child = 'is_child'       if 'is_child'       in cols else '0'
    slug     = 'igdb_slug'      if 'igdb_slug'      in cols else 'NULL'
    conn.execute(f"""
        INSERT OR IGNORE INTO resolutions (slug, igdb_id, is_child, resolved_at, correction_sig, method)
        SELECT slug, igdb_id, COALESCE({is_child}, 0), cached_at, COALESCE({sig}, ''), {method}
        FROM igdb_cache
    """)
    conn.execute(f"""
        INSERT OR IGNORE INTO igdb_games (igdb_id, igdb_slug, name, data, fetched_at, enriched)
        SELECT igdb_id, igdb_slug, name, data, cached_at, enriched FROM (
            SELECT igdb_id, {slug} AS igdb_slug, name, igdb_data AS data, cached_at,
                   COALESCE({enriched}, 1) AS enriched,
                   ROW_NUMBER() OVER (PARTITION BY igdb_id
                                      ORDER BY COALESCE({enriched}, 1) DESC, cached_at DESC) AS pick
            FROM igdb_cache
            WHERE igdb_id IS NOT NULL AND {slug} IS NOT NULL
              AND name IS NOT NULL AND igdb_data IS NOT NULL
        ) WHERE pick = 1
    """)
    conn.execute("DROP TABLE igdb_cache")
