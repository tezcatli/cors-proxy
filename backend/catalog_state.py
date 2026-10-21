"""The in-memory catalog every /games request reads, and the IGDB cache's DB mirror.

The IGDB cache is two stores, because they are two decisions with their own keys
and lifetimes: `resolutions` (the answer to each question an appearance asks — see
`questions.py` — settled once) and `games` (a game's data, shared by all the
appearances on it and renewed by id when it expires). Readers see them joined per
appearance: appearance → question → resolution → game (`entries`).

All of it is rebuilt from the RSS feeds and the DB at startup; HTTP requests read
only from memory — no per-request DB queries. Writers replace or mutate these
attributes under `lock`; other modules always go through the module
(`state.game_index`), never `from catalog_state import …`, which would freeze a
binding that `feeds.refresh_feed` later replaces.
"""
import collections
import datetime
import json
import logging
import threading

from db import get_db
from corrections import find_by_podcast
from models import Episode, IgdbEntry, IgdbGame, PodcastGame, Resolution
from questions import Question, question_for

logger = logging.getLogger(__name__)

lock = threading.Lock()

episodes:      list[Episode] = []           # source of truth; owns all Episode objects
episode_index: dict[str, Episode] = {}      # episode.slug AND url_slug → same Episode
game_index:    dict[str, PodcastGame] = {}  # name_slug → PodcastGame
cached_at:     datetime.datetime | None = None

# Loaded from DB at startup; written as questions are answered and games fetched.
resolutions: dict[str, Resolution] = {}     # question key → its answer
games:       dict[int, IgdbGame]   = {}     # igdb_id → that game's data

# Monotonic version of the data the read payloads derive from (episodes + IGDB
# stores). Bumped under `lock` on every feed re-parse that changed something /
# IGDB resolution, and used to key the cached responses in games.py so repeated
# reads (incl. 304 revalidations) skip re-serialising and re-hashing.
data_version: int = 0


def bump_version() -> None:
    """Invalidate the derived response caches without touching the IGDB cache."""
    global data_version
    with lock:
        data_version += 1


# ── Reading ───────────────────────────────────────────────────────────────────

def _entry(question: Question) -> IgdbEntry | None:
    r = resolutions.get(question.key)
    return IgdbEntry(r, games.get(r.igdb_id) if r.igdb_id else None) if r else None


def entries() -> dict[str, IgdbEntry]:
    """A consistent snapshot of what every answered appearance resolved to, by
    podcast_slug."""
    with lock:
        return {a.podcast_slug: e for game in game_index.values() for a in game.appearances
                if (e := _entry(question_for(game, a.episode)))}


def entry(game: PodcastGame, episode: Episode) -> IgdbEntry | None:
    with lock:
        return _entry(question_for(game, episode))


def asked() -> dict[str, Question]:
    """Every question the catalog asks, by key — each as of its first airing, the
    episode nearest to the game's release (see `questions.py`)."""
    first: dict[str, Question] = {}
    with lock:
        for game in game_index.values():
            for a in game.appearances:
                q = question_for(game, a.episode)
                held = first.get(q.key)
                if held is None or (q.aired or 0) < (held.aired or 0):
                    first[q.key] = q
    return first


# ── Writing ───────────────────────────────────────────────────────────────────

def store_resolution(resolution: Resolution) -> None:
    global data_version
    with lock:
        resolutions[resolution.question] = resolution
        data_version += 1
    with get_db() as conn:
        _insert_resolutions(conn, [resolution])


def _insert_resolutions(conn, rows: list[Resolution]) -> None:
    def as_json(value):
        return json.dumps(value, ensure_ascii=False) if value is not None else None
    conn.executemany(
        'INSERT OR REPLACE INTO resolutions (question, igdb_id, is_child, decided_at, method, '
        'titles, candidates, attempts, last_error, retry_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
        [(r.question, r.igdb_id, int(r.is_child), r.decided_at, r.method, as_json(r.titles),
          as_json(r.candidates), r.attempts, r.last_error, r.retry_at) for r in rows])


def store_game(game: IgdbGame) -> None:
    global data_version
    with lock:
        games[game.igdb_id] = game
        data_version += 1
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO igdb_games '
            '(igdb_id, igdb_slug, name, data, fetched_at, enriched) VALUES (?,?,?,?,?,?)',
            (game.igdb_id, game.igdb_slug, game.name, json.dumps(game.data),
             game.fetched_at, int(game.enriched)))


def load_igdb_cache_from_db() -> None:
    global resolutions, games
    with get_db() as conn:
        res_rows  = conn.execute('SELECT * FROM resolutions').fetchall()
        game_rows = conn.execute('SELECT igdb_id, igdb_slug, name, data, fetched_at, enriched '
                                 'FROM igdb_games').fetchall()

    def from_json(value):
        return json.loads(value) if value is not None else None
    loaded_res = {row['question']: Resolution(
        question=row['question'],
        igdb_id=row['igdb_id'],
        is_child=bool(row['is_child']),
        decided_at=row['decided_at'],
        method=row['method'],
        titles=from_json(row['titles']),
        candidates=from_json(row['candidates']),
        attempts=row['attempts'],
        last_error=row['last_error'],
        retry_at=row['retry_at'],
    ) for row in res_rows}
    loaded_games = {row['igdb_id']: IgdbGame(
        igdb_id=row['igdb_id'],
        igdb_slug=row['igdb_slug'],
        name=row['name'],
        data=json.loads(row['data']),
        fetched_at=row['fetched_at'],
        enriched=bool(row['enriched']),
    ) for row in game_rows}
    with lock:
        resolutions = loaded_res
        games       = loaded_games


def reconcile(complete: bool) -> None:
    """Bring the IGDB stores in line with a freshly built catalog: adopt the
    legacy per-appearance decisions once every feed is in (`complete`), then prune."""
    if complete:
        adopt_appearance_resolutions()
    prune_igdb_cache()


def prune_igdb_cache() -> None:
    """Drop the answers no appearance asks for any more (an episode left the feed,
    a correction changed the question), then the games no answer points at, so
    both stay bounded. No-op when there are no appearances (e.g. an empty/odd
    parse) so a transient feed can't wipe the cache."""
    global data_version
    questions = set(asked())
    with lock:
        if not questions:
            return
        stale = [key for key in resolutions if key not in questions]
        for key in stale:
            del resolutions[key]
        wanted = {r.igdb_id for r in resolutions.values()}
        unused = [igdb_id for igdb_id in games if igdb_id not in wanted]
        for igdb_id in unused:
            del games[igdb_id]
        if stale or unused:
            data_version += 1
    _delete_rows('resolutions', 'question', stale)
    _delete_rows('igdb_games', 'igdb_id', unused)
    if stale or unused:
        logger.info('Pruned %d unasked question(s) and %d unused game(s)',
                    len(stale), len(unused))


def purge_cache(question_keys) -> None:
    """Forget these answers so the questions are asked again. Their games stay:
    whichever game the new answers land on, its data is still good."""
    global data_version
    keys = list(set(question_keys))
    if not keys:
        return
    with lock:
        for key in keys:
            resolutions.pop(key, None)
        data_version += 1
    _delete_rows('resolutions', 'question', keys)


_EXPIRED = '1970-01-01T00:00:00'


def expire_games(igdb_ids) -> None:
    """Mark these games stale, so the next resolution or sweep re-fetches and
    re-scrapes them. Their data keeps being served meanwhile — deleting them
    would drop every appearance on them out of its catalog group until then."""
    ids = [i for i in set(igdb_ids) if i is not None]
    with lock:
        for igdb_id in ids:
            if igdb_id in games:
                games[igdb_id].fetched_at = _EXPIRED
    if ids:
        with get_db() as conn:
            ph = ','.join('?' * len(ids))
            conn.execute(f'UPDATE igdb_games SET fetched_at = ? WHERE igdb_id IN ({ph})',
                         [_EXPIRED, *ids])


def drop_game(igdb_id: int) -> None:
    """IGDB no longer has this game: forget it, and every answer pointing at it,
    so those questions are asked again."""
    global data_version
    with lock:
        games.pop(igdb_id, None)
        keys = [k for k, r in resolutions.items() if r.igdb_id == igdb_id]
        for key in keys:
            del resolutions[key]
        data_version += 1
    _delete_rows('igdb_games', 'igdb_id', [igdb_id])
    _delete_rows('resolutions', 'question', keys)


def _delete_rows(table: str, column: str, keys: list) -> None:
    if not keys:
        return
    with get_db() as conn:
        ph = ','.join('?' * len(keys))
        conn.execute(f'DELETE FROM {table} WHERE {column} IN ({ph})', keys)


# ── The legacy per-appearance decisions ───────────────────────────────────────

def adopt_appearance_resolutions() -> None:
    """Turn the decisions migrated from the legacy cache (one per appearance, see
    `db._split_igdb_cache`) into answers to the questions their appearances ask
    now, so a deploy re-asks nothing already settled. Once, then the transit table
    is dropped.

    A row answers the question its appearance asks now when it was resolved under
    the correction now in force (`_legacy_sig`); one resolved under a correction
    since changed or removed answered another question. A question inherits only
    when its appearances agree: if they disagree, it has no answer yet, and the
    LLM judges it like any other — each such question is logged."""
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'appearance_resolutions'"
                            ).fetchone():
            return
        # A row failing when it was migrated (`retry_at`, the split cache's first
        # shape) decided nothing: its question is asked like a new one.
        rows = {r['slug']: r for r in conn.execute('SELECT * FROM appearance_resolutions')
                if not ('retry_at' in r.keys() and r['retry_at'])}
    by_question: dict[str, list] = collections.defaultdict(list)
    with lock:
        for game in game_index.values():
            for a in game.appearances:
                question = question_for(game, a.episode)
                row = rows.get(a.podcast_slug)
                correction = find_by_podcast(game.name, a.episode.pub_ts, a.episode.podcast_id)
                if (row is not None and row['correction_sig'] == _legacy_sig(correction)
                        and question.key not in resolutions):
                    by_question[question.key].append(row)

    adopted = []
    for key, agreeing in by_question.items():
        ids = {r['igdb_id'] for r in agreeing}
        if len(ids) > 1:
            logger.info('Question %s: its appearances disagreed (%s); left for the LLM', key,
                        ', '.join(map(str, sorted(ids, key=str))))
            continue
        newest = max(agreeing, key=lambda r: datetime.datetime.fromisoformat(r['resolved_at']))
        # One appearance the LLM judged settles the question; otherwise it keeps
        # the method it had ('pin', a legacy row's None, or a provisional 'search').
        method = 'llm' if any(r['method'] == 'llm' for r in agreeing) else newest['method']
        adopted.append(Resolution(question=key, igdb_id=newest['igdb_id'],
                                  is_child=bool(newest['is_child']),
                                  decided_at=newest['resolved_at'], method=method))
    global data_version
    with lock:
        for r in adopted:
            resolutions[r.question] = r
        data_version += 1
    with get_db() as conn:
        _insert_resolutions(conn, adopted)
        conn.execute('DROP TABLE appearance_resolutions')
    logger.info('Adopted %d answer(s) from %d legacy per-appearance row(s)',
                len(adopted), len(rows))


def _legacy_sig(correction: dict | None) -> str:
    """How the legacy cache recorded the correction an appearance was resolved
    under ('' = none, or one that only renames)."""
    sig = {k: correction[k] for k in ('igdb_id', 'search_name', 'hint_date')
           if correction and correction.get(k)}
    return json.dumps(sig, sort_keys=True) if sig else ''
