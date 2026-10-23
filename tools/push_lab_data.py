"""Load into prod what the lab produced (`lab/pack_for_prod.py`), so prod never
transcribes, reads or resolves the history again. Runs in the prod backend
container, fed on stdin by push-lab-data.sh:

    python - load /tmp/lab-pack.json.gz

Nothing prod made is lost: a transcript prod has is kept, a reading or a game
prod has is kept (its game data may be enriched); only the answers to the
catalog's questions are replaced — the lab's chosen resolution, measured against
the curator's judgments — never a curator's pin or search (other keys). Restart
the backend afterwards: it loads the cache at start.
"""
import gzip
import json
import sys


def load(path: str) -> None:
    sys.path.insert(0, '/backend')
    from db import get_db, utcnow

    with gzip.open(path, 'rt', encoding='utf-8') as f:
        pack = json.load(f)
    now = utcnow().isoformat()
    with get_db() as conn:
        count = lambda sql: conn.execute(sql).fetchone()[0]
        before = {'transcripts': count('SELECT COUNT(*) FROM transcripts WHERE segments IS NOT NULL'),
                  'readings': count("SELECT COUNT(*) FROM llm_cache WHERE task = 'transcript'"),
                  'games': count('SELECT COUNT(*) FROM igdb_games')}
        conn.executemany(
            'INSERT INTO transcripts (guid, model, segments, duration, cost, created_at) VALUES (?,?,?,?,?,?) '
            'ON CONFLICT(guid) DO UPDATE SET model = excluded.model, segments = excluded.segments, '
            'duration = excluded.duration, cost = excluded.cost, created_at = excluded.created_at, '
            'attempts = 0, last_error = NULL, retry_at = NULL WHERE transcripts.segments IS NULL',
            [(g, m, s, d, c, now) for g, m, s, d, c in pack['transcripts']])
        conn.executemany('INSERT OR IGNORE INTO llm_cache (key, task, version, input, answer, model, created_at) '
                         'VALUES (?,?,?,?,?,?,?)', pack['readings'])
        conn.executemany('INSERT OR IGNORE INTO igdb_games (igdb_id, igdb_slug, name, data, fetched_at, enriched) '
                         'VALUES (?,?,?,?,?,?)', pack['games'])
        answers = [a for a in pack['answers'] if a[0].startswith('name|')]
        conn.executemany('INSERT OR REPLACE INTO resolutions (question, igdb_id, is_child, decided_at, method) '
                         'VALUES (?,?,?,?,?)', answers)
        after = {'transcripts': count('SELECT COUNT(*) FROM transcripts WHERE segments IS NOT NULL'),
                 'readings': count("SELECT COUNT(*) FROM llm_cache WHERE task = 'transcript'"),
                 'games': count('SELECT COUNT(*) FROM igdb_games')}
    for k in before:
        print(f'{k}: {before[k]} → {after[k]} (+{after[k] - before[k]})')
    print(f'answers: {len(answers)} stored')


if __name__ == '__main__':
    if sys.argv[1:2] != ['load'] or len(sys.argv) != 3:
        raise SystemExit('usage: python - load <pack.json.gz>')
    load(sys.argv[2])
