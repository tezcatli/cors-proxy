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
from models import IgdbEntry
from podcasts import PODCAST_BY_ID
from utils import make_slug

logger = logging.getLogger(__name__)


def resolve_one(podcast_slug: str, name: str, pub_ts: int | None,
                podcast_id: str = '', enrich: bool = True, use_llm: bool = True) -> None:
    """Resolve one appearance against IGDB and cache it (memory + DB).

    Order: a corrections.json entry; else, for an appearance already resolved
    under the same correction, a *renewal* (its cached igdb_id re-fetched, see
    `renew_id`); else the LLM (`_resolve_with_llm`); else the name search.

    `enrich=False` skips the slow, flaky scrapers (Metacritic, HowLongToBeat:
    ~1–10 s per game against ~0.3 s for IGDB) and caches the entry as
    `enriched=False`, which keeps it pending so the background sweep completes it.
    `use_llm=False` (the same quick pass) goes straight to the name search; the
    row is then cached as `method='search'`, which keeps it pending too."""
    logger.info('Resolving IGDB for slug=%r name=%r', podcast_slug, name)
    # corrections.json outranks everything else.
    correction = find_by_podcast(name, pub_ts, podcast_id)
    pinned_id  = (correction or {}).get('igdb_id')
    sig        = corrections.fingerprint(correction)
    with state.lock:
        cached = state.igdb_cache.get(podcast_slug)
    # Already resolved, under the correction still in force: refresh that game's
    # data rather than search again. A new search can land on another game (IGDB
    # added a same-name remaster since), silently undoing a resolution that was
    # right. Re-searching takes a purge: a correction, or an explicit igdb-refresh.
    # A plain search result is the exception while the LLM is on: it's provisional.
    renew_id = (cached.igdb_id if cached and cached.igdb_id and not pinned_id
                and cached.correction_sig == sig
                and not (llm.enabled() and cached.method == 'search') else None)
    method = 'pin' if correction else None
    try:
        result = None
        if pinned_id:
            # A pinned id is authoritative — don't let canonical resolution redirect
            # it (e.g. a remake IGDB models as a "port" of an earlier version).
            result = fetch_by_id(pinned_id, canonical=False)
        elif renew_id:
            # The cached id is already the canonical one, so no redirect — but the
            # entry keeps its is_child, which ranks it within its catalog group.
            result = fetch_by_id(renew_id, canonical=False)
            if result:
                result = result._replace(is_child=cached.is_child)
                method = cached.method
        if result is None and not pinned_id:
            # Never resolved, a miss, a provisional search, or a renewed id IGDB no
            # longer has. A correction's search_name/hint_date means a curator
            # chose the search, so the LLM stays out of it.
            found = (_resolve_with_llm(name, podcast_id, pub_ts)
                     if use_llm and not correction else None)
            if found is not None:
                result, method = found or None, 'llm'
            else:
                result = fetch_by_name(*_search_args(name, pub_ts, podcast_id, correction))
                method = method or 'search'
    except Exception as exc:
        logger.warning('IGDB resolution failed slug=%r name=%r: %s', podcast_slug, name, exc)
        return

    if enrich and result and result.data is not None and (shared := _enrichment_of(result.id, podcast_slug)):
        # Another appearance of this game was enriched within the TTL: the scrapers
        # (~1–10 s a game) would only fetch the same figures again.
        result.data.update(shared)
    elif enrich and result and result.data is not None:
        # Real Metacritic score (overrides the IGDB aggregate already in the blob),
        # and durée de vie — HowLongToBeat primary, IGDB time-to-beat fallback. Both
        # best-effort: any failure leaves the IGDB value / hides the stat.
        mc = metacritic.fetch_metascore(result.name)
        if mc is not None:
            result.data['metacritic'] = mc
        result.data['timeToBeatHours'] = (
            hltb.fetch_time_to_beat(result.name, result.data.get('released'))
            or fetch_time_to_beat(result.id)
        )

    state.store_entry(IgdbEntry(
        podcast_slug=podcast_slug,
        igdb_id=result.id             if result else None,
        igdb_slug=(result.slug or make_slug(result.name)) if result else None,
        name=result.name              if result else None,
        data=result.data              if result else None,
        is_child=result.is_child      if result else False,
        cached_at=utcnow().isoformat(),
        # Fingerprint the correction actually used, so a later sweep can tell when a
        # shipped corrections.json rules differently on this appearance than it did here.
        correction_sig=sig,
        # Nothing to enrich on a miss.
        enriched=enrich or not (result and result.data is not None),
        method=method,
    ))


_ENRICHED_FIELDS = ('metacritic', 'timeToBeatHours')


def _enrichment_of(igdb_id: int, podcast_slug: str) -> dict | None:
    """The scraped figures of another enriched, unexpired appearance of `igdb_id`
    (not this one's own: renewing it is how its figures get refreshed)."""
    with state.lock:
        siblings = [e for e in state.igdb_cache.values()
                    if e.igdb_id == igdb_id and e.enriched and e.data
                    and e.podcast_slug != podcast_slug]
    fresh = fresh_slugs((e.podcast_slug, e) for e in siblings)
    entry = next((e for e in siblings if e.podcast_slug in fresh), None)
    return {f: entry.data.get(f) for f in _ENRICHED_FIELDS} if entry else None


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

def fresh_slugs(cache_items) -> set:
    """Cache keys resolved within the IGDB TTL window. Compares parsed datetimes,
    not ISO strings, so a whole-second timestamp (no fractional part) can't
    mis-sort against a fractional cutoff."""
    cutoff = utcnow() - datetime.timedelta(hours=Config.IGDB_TTL_HOURS)
    return {
        slug for slug, entry in cache_items
        if datetime.datetime.fromisoformat(entry.cached_at) > cutoff
    }


def appearance_pending(game, appearance, cache, fresh) -> bool:
    """Whether the resolver should (re)resolve this appearance.

    Pending when it is TTL-stale or never cached (`fresh`), when it was cached
    without enrichment (`POST /refresh`'s quick pass), or when the correction in
    force now fingerprints differently than when it was last resolved — the
    latter is how a corrections.json shipped to an already-deployed instance takes
    effect: an added, changed *or removed* correction shifts the fingerprint and
    re-resolves exactly the affected appearances, nothing else."""
    if appearance.podcast_slug not in fresh:
        return True
    cached = cache.get(appearance.podcast_slug)
    if cached is None or not cached.enriched:
        return True
    if llm.enabled() and cached.method == 'search':
        return True             # provisional: the LLM hasn't had its say yet
    current = corrections.fingerprint(find_by_podcast(
        game.name, appearance.episode.pub_ts, appearance.episode.podcast_id))
    return cached.correction_sig != current


def count_pending() -> int:
    """Count appearances the resolver still considers pending. Only the background
    tick and the admin console ask, so it isn't memoised."""
    with state.lock:
        games = list(state.game_index.values())
        cache = dict(state.igdb_cache)
    fresh = fresh_slugs(cache.items())
    return sum(1 for game in games for a in game.appearances
               if appearance_pending(game, a, cache, fresh))


# ── The sweep ─────────────────────────────────────────────────────────────────

_resolve_lock   = threading.Lock()
_resolve_thread: threading.Thread | None = None
_resolve_stop:   threading.Event  | None = None


def _resolve_pending(stop: threading.Event) -> None:
    global _resolve_stop
    try:
        with state.lock:
            games      = dict(state.game_index)
            cache_snap = list(state.igdb_cache.items())
        if not games:
            return

        cache = dict(cache_snap)
        fresh = fresh_slugs(cache_snap)

        for game in games.values():
            if stop.is_set():
                break
            pending = [a for a in game.appearances
                       if appearance_pending(game, a, cache, fresh)]
            for appearance in pending:
                if stop.is_set():
                    break
                resolve_appearance(game, appearance)
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
                if a.podcast_slug not in state.igdb_cache]
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
            # Never-cached, unenriched, TTL-expired and re-corrected appearances
            # alike (a resolve refreshes cached_at, so this self-limits).
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
