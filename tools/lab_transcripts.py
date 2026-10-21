"""One-off: hand prod the Silence on Joue transcripts the lab already made.

The lab (~/dev/llmplayground) transcribed 601 episodes (~715 h) with WhisperX on
a local GPU to chapter them — the source of chapters.json. Importing them spares
the ingestion paying to transcribe them again (~9 $, a day of backlog). The one
exception to "prod produces, dev consumes", since the backlog happens once;
delete this with chapters.json once the backlog is through.

  lab_transcripts.py pack <lab soj.db>   on the dev host: every lab transcript,
                                          gzipped JSON on stdout
  python - load <file>                   in the prod container: map each to its
                                          episode and store it, never over one
                                          prod already has

The lab keyed an episode by its feed guid, or by make_slug(guid) for the old
djpod URLs; all 601 map to the current feed.
"""
import gzip
import json
import sqlite3
import sys

MODEL = 'whisperx-large-v2 (lab)'


def pack(lab_db: str) -> None:
    conn = sqlite3.connect(f'file:{lab_db}?mode=ro', uri=True)
    episodes: dict[str, list] = {}
    for episode_id, start, end, text in conn.execute(
            'SELECT episode_id, start_s, end_s, text FROM segment ORDER BY episode_id, idx'):
        if text and text.strip():
            episodes.setdefault(episode_id, []).append([round(start, 2), round(end, 2), text.strip()])
    with gzip.GzipFile(fileobj=sys.stdout.buffer, mode='wb') as out:
        out.write(json.dumps(episodes, ensure_ascii=False).encode())
    print(f'{len(episodes)} episodes packed', file=sys.stderr)


def load(path: str) -> None:
    sys.path.insert(0, '/backend')
    import feeds
    from db import get_db, utcnow
    from podcasts import PODCAST_BY_ID
    from utils import make_slug

    with gzip.open(path) as f:
        lab = json.load(f)
    feeds._fetch_feed(PODCAST_BY_ID['silence-on-joue'])
    guid_of = {}
    for ep in feeds._feed_episodes['silence-on-joue']:
        guid_of[ep.slug] = guid_of[make_slug(ep.slug)] = ep.slug
    rows = [(guid_of[key], MODEL, json.dumps(segments, ensure_ascii=False), segments[-1][1], 0.0,
             utcnow().isoformat()) for key, segments in lab.items() if key in guid_of]
    with get_db() as conn:
        before = conn.execute('SELECT COUNT(*) FROM transcripts WHERE segments IS NOT NULL').fetchone()[0]
        conn.executemany(
            'INSERT INTO transcripts (guid, model, segments, duration, cost, created_at) '
            'VALUES (?,?,?,?,?,?) ON CONFLICT(guid) DO UPDATE SET model = excluded.model, '
            'segments = excluded.segments, duration = excluded.duration, cost = excluded.cost, '
            'created_at = excluded.created_at, attempts = 0, last_error = NULL, retry_at = NULL '
            'WHERE transcripts.segments IS NULL', rows)
        after = conn.execute('SELECT COUNT(*) FROM transcripts WHERE segments IS NOT NULL').fetchone()[0]
    print(f'{len(lab)} lab transcripts, {len(rows)} matched to the feed, '
          f'{after - before} stored ({len(rows) - (after - before)} already had one)')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'pack':
        pack(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == 'load':
        load(sys.argv[2])
    else:
        sys.exit(__doc__)
