import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'users.db')


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
            CREATE TABLE IF NOT EXISTS rawg_cache (
                key        TEXT     PRIMARY KEY,
                data       TEXT     NOT NULL,
                cached_at  DATETIME NOT NULL
            );
        """)
