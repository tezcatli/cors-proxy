"""Copy the data prod produces into the dev DB — and nothing else.

Prod produces, dev consumes: transcripts, LLM answers and IGDB resolutions are
made by prod's pipeline, while what dev decides travels by git (corrections.json,
prompts). So the copy goes one way, and only the tables in PRODUCED leave prod:
users, invitations and reset tokens never do. It is an allowlist, so a table
added later stays home until it is listed here.

  python - export           in the prod container: the produced tables, as a
                            gzipped SQLite file on stdout
  prod_data.py import <snapshot> <dev db>
                            replace the dev DB's produced tables with the
                            snapshot's, schema included

The tables are copied as prod has them, so the dev backend migrates them at its
next start exactly as a deploy would (`db.init_db`).
"""
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile

PRODUCED = (
    'transcripts', 'llm_cache', 'resolutions', 'igdb_games',
)
PROD_DB = '/backend/data/users.db'


def _schema(conn, schema='main'):
    """The CREATE statements of the produced tables and their indexes, tables first."""
    ph = ','.join('?' * len(PRODUCED))
    return conn.execute(
        f"SELECT type, name, sql FROM {schema}.sqlite_master "
        f"WHERE tbl_name IN ({ph}) AND sql IS NOT NULL ORDER BY type = 'index'",
        PRODUCED).fetchall()


def _copy(conn, src='src') -> dict[str, int]:
    """Create the produced tables of the attached `src` in main and fill them."""
    counts = {}
    for kind, name, sql in _schema(conn, src):
        conn.execute(sql)
        if kind == 'table':
            conn.execute(f'INSERT INTO main."{name}" SELECT * FROM {src}."{name}"')
            counts[name] = conn.execute(f'SELECT COUNT(*) FROM main."{name}"').fetchone()[0]
    return counts


def export() -> None:
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        conn = sqlite3.connect(path, isolation_level=None)
        conn.execute('ATTACH ? AS src', (PROD_DB,))
        conn.execute('BEGIN')          # one read snapshot across every table
        counts = _copy(conn)
        conn.execute('COMMIT')
        conn.execute('DETACH src')
        conn.close()
        print(', '.join(f'{n} {c}' for n, c in counts.items()), file=sys.stderr)
        with open(path, 'rb') as f, gzip.GzipFile(fileobj=sys.stdout.buffer, mode='wb') as out:
            shutil.copyfileobj(f, out)
    finally:
        os.remove(path)


def import_(snapshot: str, db: str) -> None:
    conn = sqlite3.connect(db, isolation_level=None)
    conn.execute('ATTACH ? AS src', (snapshot,))
    conn.execute('BEGIN')
    for kind, name, _ in _schema(conn):
        if kind == 'table':
            conn.execute(f'DROP TABLE "{name}"')
    counts = _copy(conn)
    conn.execute('COMMIT')
    conn.close()
    for name, count in counts.items():
        print(f'  {name:24} {count:>7} rows')


if __name__ == '__main__':
    if sys.argv[1:] == ['export']:
        export()
    elif len(sys.argv) == 4 and sys.argv[1] == 'import':
        import_(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
