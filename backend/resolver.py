"""Answering the questions appearances ask (`questions.py`), and the background
work that does it.

Every question goes through the same steps, once:

  read     the LLM suggests other titles to search for (a French title's
           international one, an abbreviation expanded) — a reading of the name,
           never a fact about the game
  gather   the evidence: IGDB's candidates for the name as written, within the
           question's release window, and for the titles read
  judge    a curator (corrections.json: a pin, or the query to rank) > the LLM
           choosing among the candidates > IGDB's own ranking, provisional while
           the LLM is unavailable
  store    the answer under the question's key, with the reading and the evidence
           it was judged on; the game it lands on, once per game

The LLM reads, IGDB knows: judging names and release years needs no memory of the
game, so a game newer than the model resolves like any other. An answered
question stays answered — a new episode, a purge of its appearances' games or a
new prompt asks nothing again. One with no answer stays open: its evidence is
gathered again after the TTL, and the LLM asked again only if it changed.
"""
import dataclasses
import datetime
import logging
import threading
import time

import catalog_state as state
import feeds
import hltb
import ingest
import llm
import metacritic
import worker
from config import Config
from db import utcnow
from igdb import IgdbResult, fetch_by_id, fetch_by_name, fetch_time_to_beat, search_games
from models import IgdbEntry, IgdbGame, Resolution
from podcasts import PODCAST_BY_ID
from questions import Question, question_for
from utils import backoff, make_slug

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _Decision:
    result:     IgdbResult | None
    method:     str
    titles:     list[str] | None = None
    candidates: list[int] | None = None
    llm_failed: bool = False      # wanted, but down or unusable: provisional


def resolve(question: Question, enrich: bool = True, use_llm: bool = True) -> None:
    """Answer `question` and store the answer (memory + DB).

    `enrich=False` skips the slow, flaky scrapers (Metacritic, HowLongToBeat:
    ~1–10 s per game against ~0.3 s for IGDB) and caches a new game as
    `enriched=False`, which keeps it pending so the background sweep completes it.
    `use_llm=False` (the same quick pass) lets IGDB's ranking answer, as
    `method='search'`, which keeps the question pending too.

    A failure — IGDB erroring, or the LLM unavailable when it was wanted — is
    recorded with a growing `retry_at` (`utils.backoff`), so a question that fails every
    time costs a few calls a day rather than a round every sweep."""
    logger.info('Resolving %s', question.key)
    with state.lock:
        previous = state.resolutions.get(question.key)
    try:
        decision = _decide(question, previous, use_llm)
        if decision.result:
            _store_game(decision.result, enrich)
    except Exception as exc:
        logger.warning('IGDB resolution failed for %s: %s', question.key, exc)
        # Keep the previous answer, if any: a failed retry is no reason to stop
        # serving it.
        _store_failure(previous or Resolution(question.key, None, False, utcnow().isoformat()),
                       previous, str(exc))
        return

    result     = decision.result
    resolution = Resolution(
        question=question.key,
        igdb_id=result.id if result else None,
        is_child=result.is_child if result else False,
        decided_at=utcnow().isoformat(),
        method=decision.method,
        titles=decision.titles,
        candidates=decision.candidates,
    )
    if decision.llm_failed:
        # IGDB's ranking stands meanwhile, provisional, and the LLM is asked again
        # after the backoff.
        _store_failure(resolution, previous, 'LLM unavailable')
    else:
        state.store_resolution(resolution)


def _decide(question: Question, previous: Resolution | None, use_llm: bool) -> _Decision:
    if question.kind == 'pin':
        # A curator's answer, exactly: no redirect to a parent game (e.g. a remake
        # IGDB models as a "port" of an earlier version).
        return _Decision(fetch_by_id(question.pin, canonical=False), 'pin')
    if question.kind == 'search':
        # A curator's query: the LLM stays out of a search a human chose.
        return _Decision(fetch_by_name(question.query, question.window), 'pin')

    if not (use_llm and llm.enabled()):
        return _Decision(fetch_by_name(question.query, question.window), 'search')
    titles = _read(question, previous)
    if titles is None:
        return _Decision(fetch_by_name(question.query, question.window), 'search',
                         llm_failed=True)
    candidates, ranked = gather_evidence(question, titles)
    ids = sorted(candidates)
    if previous and previous.method == 'llm' and previous.igdb_id is None \
            and previous.candidates == ids:
        return _Decision(None, 'llm', titles, ids)    # same evidence: same verdict
    chosen = (llm.pick_candidate(question.name, _context(question),
                                 [candidates[i] for i in ids]) if ids else False)
    if chosen is None:
        return _Decision(ranked, 'search', titles, llm_failed=True)
    if chosen is False:
        return _Decision(None, 'llm', titles, ids)
    # Canonical, like the ranking: a DLC or port the model picked groups under
    # its parent game.
    result = ranked if ranked and ranked.id == chosen else fetch_by_id(chosen)
    return _Decision(result, 'llm', titles, ids)


def _read(question: Question, previous: Resolution | None) -> list[str] | None:
    """The titles to search besides the name: read once per question; None when
    the LLM is unavailable."""
    if previous and previous.titles is not None:
        return previous.titles
    podcast = PODCAST_BY_ID.get(question.podcast_id)
    if podcast and podcast.games_by_llm:
        return []                 # the LLM named these games: nothing left to read
    return llm.suggest_titles(question.name, _context(question))


def _context(question: Question) -> dict:
    podcast = PODCAST_BY_ID.get(question.podcast_id)
    return {
        'podcast':      podcast.name if podcast else '',
        'show_covers':  ('retrospectives of older games' if podcast and not podcast.use_date_hint
                         else 'new releases'),
        # The first episode that named it — for a show covering new releases, the
        # game came out shortly before (or, for a preview, after).
        'episode_date': (datetime.datetime.fromtimestamp(question.aired, datetime.timezone.utc)
                         .date().isoformat() if question.aired else None),
    }


def gather_evidence(question: Question, titles: list[str]) -> tuple[dict[int, dict], IgdbResult | None]:
    """IGDB's candidates for the name and the titles read, by id, and its own
    ranked match for the name within the question's release window — which is
    always a candidate too: IGDB's free-text search finds nothing for some games
    (« The Séance of Blake Manor ») and only DLCs and seasons for others
    (« Honkai: Star Rail », « Fall Guys »)."""
    candidates: dict[int, dict] = {}
    for query in dict.fromkeys([question.query, *titles]):
        for c in search_games(query):
            candidates.setdefault(c['id'], {'id': c['id'], 'name': c['name'],
                                            'otherNames': c['alternativeNames'],
                                            'released': c['releaseDate']})
    ranked = fetch_by_name(question.query, question.window)
    if ranked is not None:
        candidates.setdefault(ranked.id, {
            'id': ranked.id, 'name': ranked.name, 'otherNames': [],
            'released': (ranked.data or {}).get('releaseDate')})
    return candidates, ranked


def _store_failure(resolution: Resolution, previous: Resolution | None, error: str) -> None:
    attempts = (previous.attempts if previous else 0) + 1
    logger.info('Resolution of %r failed %d time(s) in a row; next try in %s',
                resolution.question, attempts, backoff(attempts))
    state.store_resolution(dataclasses.replace(
        resolution, attempts=attempts, last_error=error[:500],
        retry_at=(utcnow() + backoff(attempts)).isoformat()))


def _store_game(result, enrich: bool) -> None:
    """Cache `result`'s game, unless the cached copy is good enough: fetched within
    the TTL and enriched — or any copy at all on the quick pass, which leaves an
    expired one to the sweep rather than replace it with unscraped data."""
    with state.lock:
        cached = state.games.get(result.id)
    if cached and (not enrich or (cached.enriched and is_fresh(cached.fetched_at))):
        return
    _write_game(result, enrich)


def _write_game(result, enrich: bool) -> None:
    data = dict(result.data)
    if enrich:
        # Real Metacritic score (overrides the IGDB aggregate already in the blob),
        # and durée de vie — HowLongToBeat primary, IGDB time-to-beat fallback. Both
        # best-effort: any failure leaves the IGDB value / hides the stat.
        mc = metacritic.fetch_metascore(result.name)
        if mc is not None:
            data['metacritic'] = mc
        data['timeToBeatHours'] = (
            hltb.fetch_time_to_beat(result.name, data.get('released'))
            or fetch_time_to_beat(result.id)
        )
    state.store_game(IgdbGame(
        igdb_id=result.id,
        igdb_slug=result.slug or make_slug(result.name),
        name=result.name,
        data=data,
        fetched_at=utcnow().isoformat(),
        enriched=enrich,
    ))


def refresh_game(igdb_id: int) -> None:
    """Re-fetch a game by id — expired, never scraped, or missing — and re-scrape
    it. The questions answered with it stay answered: asking them again could land
    on a same-name game IGDB added since and silently undo a right answer. When
    IGDB no longer has the id, those questions are asked again."""
    try:
        result = fetch_by_id(igdb_id, canonical=False)
        if result is None:
            logger.info('IGDB no longer has game %d; asking its questions again', igdb_id)
            state.drop_game(igdb_id)
            return
        _write_game(result, enrich=True)
    except Exception as exc:
        logger.warning('IGDB refresh failed igdb_id=%d: %s', igdb_id, exc)


def resolve_members(members) -> None:
    """Answer the questions these appearances ask that have no answer — each once,
    however many appearances ask it, and as of its first airing."""
    asked = state.asked()
    for key in {question_for(g, a.episode).key for g, a in members}:
        if key in asked:
            _resolve_if_pending(asked[key])


# ── What is pending ───────────────────────────────────────────────────────────

def is_fresh(stamp: str) -> bool:
    """Whether `stamp` is within the IGDB TTL. Compares parsed datetimes, not ISO
    strings, so a whole-second timestamp (no fractional part) can't mis-sort
    against a fractional cutoff."""
    cutoff = utcnow() - datetime.timedelta(hours=Config.IGDB_TTL_HOURS)
    return datetime.datetime.fromisoformat(stamp) > cutoff


def resolution_pending(resolution: Resolution | None) -> bool:
    """Whether a question needs answering (again): never answered; failed, and its
    backoff has passed; answered by IGDB's ranking alone while the LLM is on
    (provisional); or open — no candidate fitted — past the TTL, since IGDB adds
    games. An answer is never re-asked for its age: `game_pending` renews its
    game's data by id."""
    if resolution is None:
        return True
    if resolution.retry_at:
        return datetime.datetime.fromisoformat(resolution.retry_at) <= utcnow()
    if llm.enabled() and resolution.method == 'search':
        return True
    return resolution.igdb_id is None and not is_fresh(resolution.decided_at)


def game_pending(game: IgdbGame | None) -> bool:
    """Whether a game an answer points at needs (re)fetching: missing, never
    scraped (`POST /refresh`'s quick pass), or past the TTL."""
    return game is None or not game.enriched or not is_fresh(game.fetched_at)


def appearance_pending(game, appearance, cache: dict[str, IgdbEntry]) -> bool:
    """Whether the sweep still has work for this appearance's question or game.
    `cache` is a `catalog_state.entries()` snapshot."""
    entry = cache.get(appearance.podcast_slug)
    if entry is None or resolution_pending(entry.resolution):
        return True
    return entry.igdb_id is not None and game_pending(entry.game)


def count_pending() -> int:
    """Count appearances the resolver still considers pending. Only the background
    tick and the admin console ask, so it isn't memoised."""
    with state.lock:
        games = list(state.game_index.values())
    cache = state.entries()
    return sum(1 for game in games for a in game.appearances
               if appearance_pending(game, a, cache))


# ── The sweep ─────────────────────────────────────────────────────────────────
# Planned as one job per question and per game on the worker, so a request's
# job never waits behind a whole sweep. Each job checks again when it runs: the
# plan may be minutes old by then.

def schedule_resolve() -> None:
    """Plan a sweep over whatever is pending. Cheap, and a no-op while one is
    already planned: every job it queues is keyed."""
    worker.submit(_plan_sweep, key='sweep')


def _plan_sweep() -> None:
    # The questions first: an answer caches its game too.
    asked = state.asked()
    with state.lock:
        answers = dict(state.resolutions)
    planned = 0
    for key, question in asked.items():
        if resolution_pending(answers.get(key)):
            worker.submit(_resolve_if_pending, question, key=f'resolve:{key}')
            planned += 1
    # Then each game's data, once per game however many questions it answers.
    stale = {e.igdb_id for e in state.entries().values()
             if e.igdb_id is not None and game_pending(e.game)}
    for igdb_id in stale:
        worker.submit(_refresh_if_pending, igdb_id, key=f'game:{igdb_id}')
    if planned or stale:
        logger.info('Sweep: %d question(s) to answer, %d game(s) to refresh',
                    planned, len(stale))


def _resolve_if_pending(question: Question) -> None:
    if resolution_pending(state.resolutions.get(question.key)):
        resolve(question)


def _refresh_if_pending(igdb_id: int) -> None:
    with state.lock:
        wanted = any(r.igdb_id == igdb_id for r in state.resolutions.values())
        game   = state.games.get(igdb_id)
    if wanted and game_pending(game):
        refresh_game(igdb_id)


def is_resolving() -> bool:
    return worker.busy()


# How long POST /refresh may spend on brand-new episodes and games before
# answering. Measured at ~0.3 s per game for IGDB alone, so a typical new
# episode (2–5 games) fits; whatever doesn't is left to the sweep.
REFRESH_BUDGET_S = 10


def quick_pass(budget_s: float) -> None:
    """POST /refresh's work after the fetch, as one worker job: someone pulled to
    refresh right after an episode came out and is watching, so the response
    should already carry the new games' names and covers. Reads new episodes of
    LLM-read shows, then answers new questions from IGDB alone — Metacritic + HLTB
    (seconds each, and often timing out) and the LLM's say are left to the sweep
    (`resolve(enrich=False, use_llm=False)`)."""
    deadline = time.monotonic() + budget_s
    feeds.read_new_episodes(deadline)
    with state.lock:
        answered = set(state.resolutions)
    for key, question in state.asked().items():
        if key in answered:
            continue
        if time.monotonic() >= deadline:
            logger.info('Refresh budget spent; leaving new questions to the sweep')
            break
        resolve(question, enrich=False, use_llm=False)
    schedule_resolve()


def schedule_llm_reads() -> None:
    """Queue every episode the LLM hasn't read, one job each; the first to answer
    queues a rebuild — behind the reads already waiting, so on a first launch
    (hundreds of episodes) the catalog is rebuilt once, not per episode."""
    for payload in feeds.unread_episodes():
        worker.submit(_read_episode, payload,
                      key=f"llm:{payload['show']}:{payload['date']}:{payload['title']}")


def _read_episode(payload: dict) -> None:
    if feeds.read_episode(payload):
        worker.submit(_rebuild_and_sweep, key='rebuild')


def _rebuild_and_sweep() -> None:
    feeds.rebuild()
    schedule_resolve()


# ── Background tick: poll the feeds, retry what's pending ─────────────────────

_periodic_stop: threading.Event | None = None


def _tick() -> None:
    # Poll every tick: the feeds answer 304 when nothing changed, so this costs a
    # few conditional GETs, and a new episode is picked up — and its games
    # resolved — within one interval, usually before anyone looks.
    try:
        feeds.refresh_feed()
    except Exception as exc:
        logger.warning('Periodic feed refresh failed: %s', exc)
    # New episodes of LLM-read shows (a few a week) get their games read.
    schedule_llm_reads()
    # Unresolved, re-corrected and due-for-retry appearances, unscraped and
    # expired games alike (resolving or fetching moves the stamp, so this
    # self-limits).
    schedule_resolve()
    # New episodes to transcribe, and failures whose delay has passed.
    ingest.wake()


def _periodic(stop: threading.Event) -> None:
    interval = Config.RESOLVE_RETRY_MINUTES * 60
    while not stop.wait(interval):
        worker.submit(_tick, key='tick')


def _start_periodic() -> None:
    global _periodic_stop
    if _periodic_stop:
        return
    _periodic_stop = threading.Event()
    threading.Thread(target=_periodic, args=(_periodic_stop,), daemon=True).start()


# ── Startup ───────────────────────────────────────────────────────────────────

def _startup() -> None:
    state.load_igdb_cache_from_db()
    try:
        feeds.refresh_feed()
    except Exception as exc:
        logger.warning('Startup RSS fetch failed: %s', exc)
    schedule_resolve()
    # On the first launch this reads every episode of the LLM-read shows — long,
    # but one job each, behind the sweep; their games then resolve in another.
    schedule_llm_reads()
    ingest.wake()


def startup_warmup() -> None:
    worker.start()
    # HIGH, and queued before any request can be: a cold-start GET /games waiting
    # on the feed must find the IGDB cache already loaded.
    worker.submit(_startup, key='startup', priority=worker.HIGH)
    _start_periodic()
    # Each episode read changes its games and chapters: rebuild, then resolve
    # what it asks. Keyed, so a rebuild still waiting absorbs the next read.
    ingest.start(on_read=lambda: worker.submit(_rebuild_and_sweep, key='rebuild'))
