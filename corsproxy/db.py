import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'users.db')


def utcnow():
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT    NOT NULL,
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                used_at    DATETIME
            );

            CREATE TABLE IF NOT EXISTS igdb_cache (
                slug      TEXT PRIMARY KEY,
                igdb_id   INTEGER,
                igdb_slug TEXT,
                name      TEXT,
                igdb_data TEXT,
                is_child  INTEGER DEFAULT 0,
                cached_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS igdb_cache_igdb_slug
                ON igdb_cache(igdb_slug) WHERE igdb_slug IS NOT NULL;
        """)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(igdb_cache)")}
        if 'igdb_slug' not in cols and cols:
            conn.execute("ALTER TABLE igdb_cache ADD COLUMN igdb_slug TEXT")
        if 'is_child' not in cols and cols:
            conn.execute("ALTER TABLE igdb_cache ADD COLUMN is_child INTEGER DEFAULT 0")
