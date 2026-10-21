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
        # The split cache's first shape (deployed on its own) kept one decision per
        # appearance in `resolutions`, keyed by slug: exactly the transit table's
        # rows, which become answers at the first complete build.
        if 'slug' in {row[1] for row in conn.execute("PRAGMA table_info(resolutions)")}:
            conn.execute('ALTER TABLE resolutions RENAME TO appearance_resolutions')
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
    """Migrate the legacy one-row-per-appearance `igdb_cache`, then drop it.

    The games go straight to `igdb_games`, each keeping its best copy: an enriched
    one over the quick pass's, then the newest. The decisions can't become
    questions yet — a question needs the episode's show and date, so the feed —
    so they wait in `appearance_resolutions` until the first catalog build
    (`catalog_state.adopt_appearance_resolutions`)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(igdb_cache)")}
    # Columns added over the table's life; NULL on rows from before them.
    sig      = 'correction_sig' if 'correction_sig' in cols else "''"
    enriched = 'enriched'       if 'enriched'       in cols else '1'
    method   = 'method'         if 'method'         in cols else 'NULL'
    is_child = 'is_child'       if 'is_child'       in cols else '0'
    slug     = 'igdb_slug'      if 'igdb_slug'      in cols else 'NULL'
    conn.execute("""
        CREATE TABLE appearance_resolutions (
            slug           TEXT PRIMARY KEY,
            igdb_id        INTEGER,
            is_child       INTEGER NOT NULL,
            resolved_at    TEXT    NOT NULL,
            correction_sig TEXT    NOT NULL,
            method         TEXT
        )
    """)
    conn.execute(f"""
        INSERT INTO appearance_resolutions
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
