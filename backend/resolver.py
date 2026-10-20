"""Resolving podcast game names against IGDB, and the background work that does it."""
import datetime
import logging
import threading
import time

import catalog_state as state
import corrections
import feeds
import hltb
import llm
import metacritic
from config import Config
from corrections import find_by_podcast
from db import utcnow
from igdb import fetch_by_id, fetch_by_name, fetch_time_to_beat, search_games
from models import IgdbEntry, IgdbGame, Resolution
from podcasts import PODCAST_BY_ID
from utils import make_slug

logger = logging.getLogger(__name__)


def resolve_one(podcast_slug: str, name: str, pub_ts: int | None,
                podcast_id: str = '', enrich: bool = True, use_llm: bool = True) -> None:
    """Decide which IGDB game one appearance is, and cache that decision (memory + DB).

    Order: a corrections.json entry; else the LLM (`_resolve_with_llm`); else the
    name search. The game's data is cached once per game (`_store_game`), so an
    appearance landing on a game already fetched costs no second fetch or scrape.

    `enrich=False` skips the slow, flaky scrapers (Metacritic, HowLongToBeat:
    ~1–10 s per game against ~0.3 s for IGDB) and caches a new game as
    `enriched=False`, which keeps it pending so the background sweep completes it.
    `use_llm=False` (the same quick pass) goes straight to the name search; the
    resolution is then cached as `method='search'`, which keeps it pending too."""
    logger.info('Resolving IGDB for slug=%r name=%r', podcast_slug, name)
    # corrections.json outranks everything else.
    correction = find_by_podcast(name, pub_ts, podcast_id)
    pinned_id  = (correction or {}).get('igdb_id')
    method     = 'pin' if correction else None
    try:
        if pinned_id:
            # A pinned id is authoritative — don't let canonical resolution redirect
            # it (e.g. a remake IGDB models as a "port" of an earlier version).
            result = fetch_by_id(pinned_id, canonical=False)
        else:
            # A correction's search_name/hint_date means a curator chose the
            # search, so the LLM stays out of it.
            found = (_resolve_with_llm(name, podcast_id, pub_ts)
                     if use_llm and not correction else None)
            if found is not None:
                result, method = found or None, 'llm'
            else:
                result = fetch_by_name(*_search_args(name, pub_ts, podcast_id, correction))
                method = method or 'search'
        if result:
            _store_game(result, enrich)
    except Exception as exc:
        logger.warning('IGDB resolution failed slug=%r name=%r: %s', podcast_slug, name, exc)
        return

    state.store_resolution(Resolution(
        podcast_slug=podcast_slug,
        igdb_id=result.id if result else None,
        is_child=result.is_child if result else False,
        resolved_at=utcnow().isoformat(),
        # Fingerprint the correction actually used, so a later sweep can tell when a
        # shipped corrections.json rules differently on this appearance than it did here.
        correction_sig=corrections.fingerprint(correction),
        method=method,
    ))


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
    it. Its appearances keep their resolution: re-searching their names could land
    on a same-name game IGDB added since and silently undo a right resolution. When
    IGDB no longer has the id, those appearances are searched again."""
    try:
        result = fetch_by_id(igdb_id, canonical=False)
        if result is None:
            logger.info('IGDB no longer has game %d; re-resolving its appearances', igdb_id)
            state.drop_game(igdb_id)
            return
        _write_game(result, enrich=True)
    except Exception as exc:
        logger.warning('IGDB refresh failed igdb_id=%d: %s', igdb_id, exc)


def _search_args(name, pub_ts, podcast_id, correction) -> tuple[str, int | None]:
    """(name, date hint) for `fetch_by_name`."""
    search_name = (correction or {}).get('search_name') or name
    hint_date   = (correction or {}).get('hint_date')
    podcast     = PODCAST_BY_ID.get(podcast_id)
    if hint_date:
        # An explicit curated date always wins, whatever the podcast.
        return search_name, int(datetime.datetime.fromisoformat(hint_date)
                                .replace(tzinfo=datetime.timezone.utc).timestamp())
    if podcast and not podcast.use_date_hint:
        # Retrospective show: the episode date isn't evidence of the game's release
        # date, so search undated and let the ranker prefer the earliest same-name
        # entry.
        return search_name, None
    return search_name, pub_ts


def _resolve_with_llm(name: str, podcast_id: str, pub_ts: int | None):
    """The IGDB game the LLM says `name` means: an IgdbResult, False when it
    judges that no IGDB entry fits (cached as a miss), or None when the LLM is
    unavailable (the caller falls back to the name search).

    The model never supplies an id: it names the game (translating, expanding),
    we search IGDB for its candidates, and it picks among those.

    The context is the show and the year, not the episode: a name heard in
    several episodes of a year is then one question, not one per episode."""
    if not llm.enabled():
        return None
    podcast = PODCAST_BY_ID.get(podcast_id)
    context = {
        'podcast':       podcast.name if podcast else '',
        'show_covers':   ('retrospectives of older games' if podcast and not podcast.use_date_hint
                          else 'new releases'),
        'episode_year':  (datetime.datetime.fromtimestamp(pub_ts, datetime.timezone.utc).year
                          if pub_ts else None),
    }
    # A show whose games the LLM read already has official titles: asking the
    # model to name the game again would only cost a call.
    titles = [name] if podcast and podcast.games_by_llm else llm.official_titles(name, context)
    if titles is None:
        return None
    if not titles:
        return False
    candidates: dict[int, dict] = {}
    for query in dict.fromkeys([name, *titles]):
        for c in search_games(query):
            candidates.setdefault(c['id'], {'id': c['id'], 'name': c['name'],
                                            'year': c['released']})
    # IGDB's free-text search misses some games its name search finds: nothing
    # at all for « The Séance of Blake Manor », only DLCs and seasons for
    # « Honkai: Star Rail » or « Fall Guys ». Always offer that match too.
    fallback = fetch_by_name(*_search_args(name, pub_ts, podcast_id, None))
    if fallback is not None:
        candidates.setdefault(fallback.id, {
            'id': fallback.id, 'name': fallback.name,
            'year': ((fallback.data or {}).get('released') or '')[:4] or None})
    if not candidates:
        return False
    chosen = llm.pick_candidate(name, context, list(candidates.values()))
    if not chosen:
        return chosen
    if fallback is not None and chosen == fallback.id:
        return fallback                      # already canonical
    # Canonical, like the name search: a DLC or port the model picked groups
    # under its parent game.
    return fetch_by_id(chosen) or None


def resolve_members(members) -> None:
    for game, appearance in members:
        resolve_appearance(game, appearance)


def resolve_appearance(game, appearance, **kwargs) -> None:
    ep = appearance.episode
    resolve_one(appearance.podcast_slug, game.name, ep.pub_ts, ep.podcast_id, **kwargs)


# ── What is pending ───────────────────────────────────────────────────────────

def is_fresh(stamp: str) -> bool:
    """Whether `stamp` is within the IGDB TTL. Compares parsed datetimes, not ISO
    strings, so a whole-second timestamp (no fractional part) can't mis-sort
    against a fractional cutoff."""
    cutoff = utcnow() - datetime.timedelta(hours=Config.IGDB_TTL_HOURS)
    return datetime.datetime.fromisoformat(stamp) > cutoff


def resolution_pending(game, appearance, resolution: Resolution | None) -> bool:
    """Whether the resolver should decide (again) which game this appearance is.

    Pending when never resolved; when IGDB had no match and the TTL has passed
    (it may have added the game since); when it is a plain search result while the
    LLM is on (provisional: the LLM hasn't had its say); or when the correction in
    force now fingerprints differently than when it was resolved — that is how a
    corrections.json shipped to an already-deployed instance takes effect: an
    added, changed *or removed* correction re-resolves exactly the affected
    appearances. A match is never re-searched for its age: `game_pending` renews
    its data by id."""
    if resolution is None:
        return True
    if resolution.igdb_id is None and not is_fresh(resolution.resolved_at):
        return True
    if llm.enabled() and resolution.method == 'search':
        return True
    current = corrections.fingerprint(find_by_podcast(
        game.name, appearance.episode.pub_ts, appearance.episode.podcast_id))
    return resolution.correction_sig != current


def game_pending(game: IgdbGame | None) -> bool:
    """Whether a game an appearance is resolved to needs (re)fetching: missing,
    never scraped (`POST /refresh`'s quick pass), or past the TTL."""
    return game is None or not game.enriched or not is_fresh(game.fetched_at)


def appearance_pending(game, appearance, cache: dict[str, IgdbEntry]) -> bool:
    """Whether the sweep still has work for this appearance, either decision.
    `cache` is a `catalog_state.entries()` snapshot."""
    entry = cache.get(appearance.podcast_slug)
    if entry is None or resolution_pending(game, appearance, entry.resolution):
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

_resolve_lock   = threading.Lock()
_resolve_thread: threading.Thread | None = None
_resolve_stop:   threading.Event  | None = None


def _resolve_pending(stop: threading.Event) -> None:
    global _resolve_stop
    try:
        with state.lock:
            games = dict(state.game_index)
        if not games:
            return

        # Which game each appearance is, first: a resolution caches its game too.
        cache = state.entries()
        for game in games.values():
            for appearance in game.appearances:
                if stop.is_set():
                    return
                entry = cache.get(appearance.podcast_slug)
                if resolution_pending(game, appearance, entry.resolution if entry else None):
                    resolve_appearance(game, appearance)

        # Then each game's data, once per game however many episodes discuss it.
        stale = {e.igdb_id for e in state.entries().values()
                 if e.igdb_id is not None and game_pending(e.game)}
        for igdb_id in stale:
            if stop.is_set():
                return
            refresh_game(igdb_id)
    finally:
        with _resolve_lock:
            if _resolve_stop is stop:
                _resolve_stop = None


def schedule_resolve(force: bool = False) -> None:
    global _resolve_thread, _resolve_stop
    with _resolve_lock:
        if not force and _resolve_thread and _resolve_thread.is_alive():
            return
        if _resolve_stop:
            _resolve_stop.set()
        stop            = threading.Event()
        _resolve_stop   = stop
        _resolve_thread = threading.Thread(target=_resolve_pending, args=(stop,), daemon=True)
        _resolve_thread.start()


def is_resolving() -> bool:
    return bool(_resolve_thread and _resolve_thread.is_alive())


# How long POST /refresh may spend on brand-new games before answering. Measured
# at ~0.3 s per game for IGDB alone, so a typical new episode (2–5 games) fits;
# whatever doesn't is left to the background sweep.
REFRESH_BUDGET_S = 10


def resolve_new(budget_s: float) -> None:
    """IGDB-only pass over never-cached appearances, bounded by `budget_s`.

    A user pulls to refresh right after an episode comes out, so this is when
    someone is watching: the response should already carry the new games' names
    and covers. Metacritic + HLTB (seconds each, and often timing out) are left to
    the background sweep — see `resolve_one(enrich=False)`."""
    deadline = time.monotonic() + budget_s
    with state.lock:
        todo = [(g, a) for g in state.game_index.values() for a in g.appearances
                if a.podcast_slug not in state.resolutions]
    for game, appearance in todo:
        if time.monotonic() >= deadline:
            logger.info('Refresh budget spent; leaving new appearances to the sweep')
            break
        resolve_appearance(game, appearance, enrich=False, use_llm=False)


# ── Background tick: poll the feeds, retry what's pending ─────────────────────

_periodic_stop: threading.Event | None = None


def _periodic_resolve(stop: threading.Event) -> None:
    interval = Config.RESOLVE_RETRY_MINUTES * 60
    while not stop.wait(interval):
        try:
            # Poll every tick: the feeds answer 304 when nothing changed, so this
            # costs two conditional GETs, and a new episode is picked up — and its
            # games resolved — within one interval, usually before anyone looks.
            try:
                feeds.refresh_feed()
            except Exception as exc:
                logger.warning('Periodic feed refresh failed: %s', exc)
            # New episodes of LLM-read shows (a few a week) get their games here.
            feeds.ask_llm_for_new_episodes()
            # Unresolved and re-corrected appearances, unscraped and expired games
            # alike (resolving or fetching refreshes the stamp, so this self-limits).
            pending = count_pending()
            if pending:
                logger.info('Periodic re-resolve: %d pending appearance(s)', pending)
                schedule_resolve()
        except Exception:
            logger.exception('Periodic re-resolve tick failed')


def _start_periodic_resolve() -> None:
    global _periodic_stop
    if _periodic_stop:
        return
    _periodic_stop = threading.Event()
    threading.Thread(target=_periodic_resolve, args=(_periodic_stop,), daemon=True).start()


# ── Startup ───────────────────────────────────────────────────────────────────

def _startup() -> None:
    state.load_igdb_cache_from_db()
    try:
        feeds.refresh_feed()
    except Exception as exc:
        logger.warning('Startup RSS fetch failed: %s', exc)
    schedule_resolve()
    _start_periodic_resolve()
    # On the first launch this reads every episode of the LLM-read shows — long,
    # so after the sweep and the tick are up; their games then resolve in a sweep.
    if feeds.ask_llm_for_new_episodes():
        schedule_resolve()


def startup_warmup() -> None:
    threading.Thread(target=_startup, daemon=True).start()
