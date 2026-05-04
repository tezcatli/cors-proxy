import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'users.db')


def utcnow():
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
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

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS games (
                id           INTEGER  PRIMARY KEY AUTOINCREMENT,
                igdb_id      INTEGER  UNIQUE,
                slug         TEXT     UNIQUE,
                display_name TEXT     NOT NULL,
                igdb_data    TEXT,
                igdb_at      TEXT
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                title     TEXT    NOT NULL UNIQUE,
                audio_url TEXT,
                pub_ts    INTEGER
            );
            CREATE TABLE IF NOT EXISTS episode_games (
                episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                game_id    INTEGER NOT NULL REFERENCES games(id)    ON DELETE CASCADE,
                timestamp  TEXT,
                ts_seconds INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (episode_id, game_id)
            );
        """)
