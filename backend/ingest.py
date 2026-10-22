"""The ingestion: transcribing every episode and reading its transcript, newest
first, one episode at a time, in one background thread.

Slow on purpose. The backlog (~2 300 h of audio) is a one-off that takes a day or
two, after which there is a handful of episodes a week; it shares a small server
with other apps. It runs off the worker because an episode takes a minute or more
(download, upload, transcription, reading), and the worker's jobs must stay short
for the requests waiting on them. What it produces goes to the `transcripts`
table and `llm_cache` — memos, safe to fill from any thread; the catalog only
changes when the worker rebuilds it (`on_read`).
"""
import logging
import threading
import time

import feeds
import llm
import transcribe
from config import Config
from db import utcnow
from models import Episode
from podcasts import PODCAST_BY_ID
from utils import backoff

logger = logging.getLogger(__name__)

_wake = threading.Event()
_thread: threading.Thread | None = None

# DeepInfra failing — out of credit, a key refused, an outage — pauses the whole
# ingestion rather than fail each episode in turn: each attempt downloads the
# whole audio first (up to 180 MB), so a dry account would pull the backlog's
# ~100 GB for nothing, every day. In memory: a restart resumes at once.
_failures     = 0      # DeepInfra failures in a row
_paused_until = 0.0    # time.monotonic()


def _status(episode: Episode, row: transcribe.Row | None) -> str:
    """Where an episode stands: 'transcribe' (no transcript yet), 'read' (the
    current prompt hasn't read it) or 'done'."""
    if not (row and row.model):
        return 'transcribe'
    read = llm.has_current_reading(transcribe.reading_input(episode, row.model))
    return 'done' if read else 'read'


def pending() -> list[Episode]:
    """What is left to do, newest first: the episodes not transcribed yet, and the
    transcribed ones the current prompt hasn't read — less those waiting out a
    failure, and what can't be done (no audio, a key missing)."""
    rows = transcribe.rows()
    now  = utcnow().isoformat()
    todo = []
    for ep in feeds.all_episodes():
        row = rows.get(ep.slug)
        if row and row.retry_at and row.retry_at > now:
            continue
        status = _status(ep, row)
        if (status == 'read' and llm.enabled()
                or status == 'transcribe' and transcribe.enabled() and ep.audio_url):
            todo.append(ep)
    return todo


def stats() -> dict[str, dict]:
    """Per show: its episodes, how many are transcribed, read by the current
    prompt, and failing (waiting out a delay)."""
    rows = transcribe.rows()
    out: dict[str, dict] = {}
    for ep in feeds.all_episodes():
        tally = out.setdefault(ep.podcast_id, {'episodes': 0, 'transcribed': 0, 'read': 0,
                                               'ingestErrors': 0})
        row = rows.get(ep.slug)
        status = _status(ep, row)
        tally['episodes']     += 1
        tally['transcribed']  += status != 'transcribe'
        tally['read']         += status == 'done'
        tally['ingestErrors'] += bool(row and row.retry_at)
    return out


def ingest(episode: Episode) -> bool:
    """Transcribe `episode` if it isn't, then read it. True once it is read; a
    failure of the episode is recorded, and it waits out a growing delay. A
    failure of DeepInfra (`transcribe.Unavailable`) is raised: it isn't the
    episode's."""
    try:
        transcript = transcribe.load(episode.slug)
        if transcript is None:
            transcript = transcribe.transcribe(
                episode.audio_url, PODCAST_BY_ID[episode.podcast_id].language)
            transcribe.store(episode.slug, transcript)
            logger.info('Transcribed %r: %.1f h, $%.4f', episode.title,
                        transcript.duration / 3600, transcript.cost or 0)
        if not llm.enabled():
            return False
        if llm.read_transcript(transcribe.reading_input(episode, transcript.model),
                               transcript.segments) is None:
            raise RuntimeError('LLM unavailable')
        transcribe.clear_failure(episode.slug)
        logger.info('Read %r', episode.title)
        return True
    except transcribe.Unavailable:
        raise
    except Exception as exc:
        transcribe.store_failure(episode.slug, f'{type(exc).__name__}: {exc}')
        return False


def wake() -> None:
    """There may be new work: the feeds were polled, or a failure is due again."""
    _wake.set()


def start(on_read) -> None:
    """Run the ingestion; `on_read()` after each episode read, to rebuild the
    catalog with it. Nothing to run without a transcription or LLM key, nor
    in dev (`Config.INGEST`)."""
    global _thread
    if _thread or not Config.INGEST or not (transcribe.enabled() or llm.enabled()):
        return
    _thread = threading.Thread(target=_loop, args=(on_read,), daemon=True, name='ingest')
    _thread.start()


def _step(on_read) -> float | None:
    """One turn: ingest the next pending episode. Returns how long to wait before
    the next turn: 0 to go on, None until woken (nothing to do), the rest of a
    pause while DeepInfra fails."""
    global _failures, _paused_until
    pause = _paused_until - time.monotonic()
    if pause > 0:
        return pause
    try:
        todo = pending()
    except Exception:
        logger.exception('Ingestion: listing the pending episodes failed')
        return None
    if not todo:
        return None
    try:
        read = ingest(todo[0])
    except transcribe.Unavailable as exc:
        _failures += 1
        delay = backoff(_failures).total_seconds()
        _paused_until = time.monotonic() + delay
        logger.warning('Ingestion paused for %d min (%s); restart the backend to resume at once',
                       delay // 60, exc)
        return delay
    _failures = 0
    if read:
        on_read()
    return 0


def _loop(on_read) -> None:
    while True:
        _wake.clear()
        wait = _step(on_read)
        if wait != 0:
            _wake.wait(wait)     # the tick's wake ends it early: a pause is then re-checked


def untranscribed(oldest_first: bool = True) -> list[Episode]:
    """The episodes with audio and no transcript yet, oldest first by default."""
    rows = transcribe.rows()
    todo = [ep for ep in feeds.all_episodes()
            if ep.audio_url and not (rows.get(ep.slug) and rows[ep.slug].model)]
    return todo[::-1] if oldest_first else todo


def transcribe_all(episodes: list[Episode], jobs: int) -> tuple[int, float]:
    """Transcribe `episodes`, `jobs` at a time — the backlog, from dev, while prod
    only serves. Transcribing only: the readings are the lab's to make. An episode
    already transcribed is skipped, so a rerun pays nothing twice. DeepInfra failing
    stops the run (it would fail every episode in turn); a failing episode is
    recorded and the others go on. Returns how many were transcribed, and the cost."""
    import concurrent.futures
    stop = threading.Event()
    done, cost = 0, 0.0

    def one(episode: Episode):
        if stop.is_set() or transcribe.load(episode.slug) is not None:
            return None
        try:
            t = transcribe.transcribe(episode.audio_url, PODCAST_BY_ID[episode.podcast_id].language)
        except transcribe.Unavailable as exc:
            stop.set()
            logger.error('DeepInfra failing, stopping (at %s): %s', episode.title[:60], exc)
            return None
        except Exception as exc:
            transcribe.store_failure(episode.slug, f'{type(exc).__name__}: {exc}')
            logger.warning('%s: %s', episode.title[:60], exc)
            return None
        transcribe.store(episode.slug, t)
        return t

    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        for i, (episode, t) in enumerate(zip(episodes, pool.map(one, episodes)), 1):
            if t is not None:
                done += 1
                cost += t.cost or 0
                logger.info('%d/%d  %s · %.1f h · $%.4f  (total $%.2f)', i, len(episodes),
                            episode.title[:60], t.duration / 3600, t.cost or 0, cost)
    return done, cost


def main(argv: list[str]) -> None:
    """In dev:
      python ingest.py <guid or url_slug>...         ingest (transcribe + read) these episodes
      python ingest.py --transcribe-all [--jobs N]   transcribe every episode not yet transcribed,
                                                     oldest first, N at a time (default 8)"""
    import db
    from rss import assign_url_slugs
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    db.init_db()
    for podcast in feeds.PODCASTS:
        feeds._fetch_feed(podcast)
    if argv and argv[0] == '--transcribe-all':
        jobs = int(argv[argv.index('--jobs') + 1]) if '--jobs' in argv else 8
        todo = untranscribed()
        logger.info('%d episode(s) to transcribe, %d at a time', len(todo), jobs)
        done, cost = transcribe_all(todo, jobs)
        logger.info('Transcribed %d episode(s), $%.2f', done, cost)
        return
    episodes = feeds.all_episodes()
    assign_url_slugs(episodes)
    by_name = {key: ep for ep in episodes for key in (ep.slug, ep.url_slug)}
    for name in argv:
        episode = by_name.get(name)
        if episode is None:
            logger.error('No episode %r', name)
        elif not ingest(episode):
            logger.error('%r not read: %s', name, transcribe.rows()[episode.slug].last_error
                         or 'no LLM key, transcribed only')
    logger.info('Restart the backend to rebuild the catalog with them.')


if __name__ == '__main__':
    import sys
    main(sys.argv[1:])
