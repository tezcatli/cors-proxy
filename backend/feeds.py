"""Fetching the podcast feeds and rebuilding the in-memory catalog from them."""
import datetime
import json
import logging
import pathlib
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html import unescape as _html_unescape

import requests as http

import catalog_state as state
import llm
from config import Config
from corrections import unmatched_slugs
from db import utcnow
from models import Chapter, Episode, GameAppearance, GameMention, PodcastGame
from podcasts import PODCASTS
from rss import parse_feed, assign_url_slugs, is_game_catalog_excluded, find_chapter_for_game
from utils import make_slug

logger = logging.getLogger(__name__)


# ── AI chapter injection ──────────────────────────────────────────────────────

def _seconds_to_ts(secs: float) -> str:
    s = int(secs)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def _load_ai_chapter_index() -> dict[str, list]:
    path = pathlib.Path(__file__).parent / 'chapters.json'
    if not path.exists():
        logger.warning('chapters.json not found at %s', path)
        return {}
    with path.open(encoding='utf-8') as f:
        data = json.load(f)
    index = {}
    for ep in data.get('episodes', []):
        slug = make_slug(ep.get('title', ''))
        if slug:
            index[slug] = ep.get('chapters', [])
    return index


def inject_ai_chapters(episodes: list[Episode], ai_index: dict) -> None:
    injected = 0
    for episode in episodes:
        # chapters.json is keyed by make_slug(title); episode.slug is now the guid,
        # so match on the title slug here.
        title_slug = make_slug(episode.title)
        if episode.chapters or title_slug not in ai_index:
            continue
        raw_chapters = ai_index[title_slug]
        chapters = [
            Chapter(
                timestamp=_seconds_to_ts(c['start_s']),
                timestamp_seconds=int(c['start_s']),
                title=c['title'],
                game_name=c.get('game_name'),
            )
            for c in raw_chapters
            if c.get('start_s') is not None and c.get('title')
            and c['title'] not in ('Publicité', 'Transition')
        ]
        episode.chapters = chapters
        for mention in episode.games:
            matched = find_chapter_for_game(mention.name, chapters)
            if matched:
                mention.timestamp = matched.timestamp
                mention.timestamp_seconds = matched.timestamp_seconds
        injected += 1
    if injected:
        logger.info('Injected AI chapters into %d episodes', injected)


# ── Indexes ───────────────────────────────────────────────────────────────────

def build_indexes(episodes: list[Episode]) -> tuple[dict, dict]:
    """Build episode_index and game_index from a list of Episode objects."""
    episode_index: dict[str, Episode]     = {}
    game_index:    dict[str, PodcastGame] = {}

    for episode in episodes:
        episode_index[episode.slug] = episode
        # Register the pretty url_slug too, so /games/episode resolves either the
        # guid (legacy/cached links) or the human-readable slug.
        if episode.url_slug:
            episode_index[episode.url_slug] = episode

        if is_game_catalog_excluded(episode.title):
            continue

        for mention in episode.games:
            name_slug    = make_slug(mention.name)
            # Per-episode cache/appearance key (episode.slug is the stable guid).
            # Same game in the same episode collides → deduped; distinct episodes
            # (incl. same-day) get distinct keys and are both kept.
            podcast_slug = f'{name_slug}-{episode.slug}'

            if name_slug not in game_index:
                game_index[name_slug] = PodcastGame(name_slug=name_slug, name=mention.name)
            else:
                existing = game_index[name_slug]
                # Drop only a true intra-episode duplicate (same game twice in one item).
                if any(a.podcast_slug == podcast_slug for a in existing.appearances):
                    logger.info('Duplicate mention %r in episode %r, skipping', podcast_slug, episode.title)
                    continue

            game_index[name_slug].appearances.append(GameAppearance(
                episode=episode,
                mention=mention,
                podcast_slug=podcast_slug,
            ))

    return episode_index, game_index


# ── Fetching ──────────────────────────────────────────────────────────────────

# Per-podcast HTTP cache validators and last-parsed episode lists. The cached
# episode lists let a 304 ("unchanged") keep that feed's episodes while another
# feed is re-parsed — every refresh recombines all feeds into one catalog.
_feed_meta:     dict[str, dict] = {}            # podcast_id -> {etag, last_modified}
_feed_episodes: dict[str, list[Episode]] = {}   # podcast_id -> last parsed episodes


def _fetch_feed(podcast) -> bool:
    """Fetch one podcast's feed; (re)parse it into `_feed_episodes` on a 200.

    Returns True when the feed changed (200, re-parsed), False on 304/unchanged.
    Raises on network/HTTP/parse errors — caller decides how to handle.
    """
    headers = {'User-Agent': 'PodcastCatalog/1.0'}
    meta = _feed_meta.get(podcast.id, {})
    if meta.get('etag'):          headers['If-None-Match']    = meta['etag']
    if meta.get('last_modified'): headers['If-Modified-Since'] = meta['last_modified']

    resp = http.get(podcast.feed_url, timeout=Config.REQUEST_TIMEOUT, headers=headers)
    if resp.status_code == 304 and podcast.id in _feed_episodes:
        logger.info('Feed %s unchanged (304); keeping cached episodes', podcast.id)
        return False
    resp.raise_for_status()
    _feed_meta[podcast.id] = {
        'etag':          resp.headers.get('ETag'),
        'last_modified': resp.headers.get('Last-Modified'),
    }
    _feed_episodes[podcast.id] = parse_feed(
        resp.content, extractor=podcast.extractor, podcast_id=podcast.id)
    return True


_refresh_lock = threading.Lock()


def refresh_feed() -> None:
    """Fetch every registered podcast, then recombine all feeds into one catalog.

    Each feed is fetched independently (per-feed ETag); a single feed failing
    doesn't abort the others as long as we already have cached episodes for it.
    If *no* feed yields any episodes, the whole refresh raises so the caller can
    keep serving the previous cache rather than blanking it.

    Serialized: a caller that waited on the lock while another thread refreshed
    piggybacks on that result instead of re-fetching (the concurrent callers are
    a cold-start catalog request, the periodic thread, and POST /refresh — all of
    which just want "fresh now").
    """
    before = state.cached_at
    with _refresh_lock:
        if state.cached_at is not before:
            return

        errors: list[str] = []
        changed = False
        for podcast in PODCASTS:
            try:
                changed |= _fetch_feed(podcast)
            except Exception as exc:
                errors.append(f'{podcast.id}: {exc}')
                logger.warning('Feed fetch failed for %s: %s', podcast.id, exc)

        # The feeds are polled every few minutes and almost always answer 304:
        # rebuilding then would bump data_version and invalidate every client's
        # ETag for nothing.
        if not changed and state.episodes:
            with state.lock:
                state.cached_at = utcnow()
            return
        _rebuild(errors)


def rebuild() -> None:
    """Recombine the feeds already fetched into the catalog — after the LLM has
    answered for new episodes, which changes their games but not the feeds."""
    with _refresh_lock:
        _rebuild([])


def _rebuild(errors: list[str]) -> None:
    """Combine every feed's episodes into the catalog. Caller holds _refresh_lock."""
    # Cached lists survive a 304 or a failed fetch.
    episodes = [ep for podcast in PODCASTS for ep in _feed_episodes.get(podcast.id, [])]
    if not episodes:
        raise RuntimeError('No episodes from any feed: ' + '; '.join(errors) if errors
                           else 'No episodes from any feed')

    # Interleave the feeds newest-first; otherwise each feed's block would stay
    # contiguous (e.g. all SOJ before any FDG) and the later podcasts would be
    # buried at the bottom of the episodes feed. Stable sort keeps ties/undated
    # items in their existing intra-feed order.
    episodes.sort(key=lambda e: e.pub_ts or 0, reverse=True)
    episodes = _apply_llm_games(episodes)

    assign_url_slugs(episodes)
    inject_ai_chapters(episodes, _load_ai_chapter_index())
    episode_index, game_index = build_indexes(episodes)
    with state.lock:
        state.episodes      = episodes
        state.episode_index = episode_index
        state.game_index    = game_index
        state.cached_at     = utcnow()
        state.data_version += 1
    dead = unmatched_slugs(game_index.keys())
    if dead:
        logger.warning('%d correction(s) match no game name in the feed: %s',
                       len(dead), ', '.join(dead))
    state.prune_igdb_cache()


# ── Games read by the LLM ─────────────────────────────────────────────────────
# Shows with `games_by_llm`: an episode's games are whatever the LLM said it
# critiques. Only cached answers are used while rebuilding (that runs on request
# paths and must not wait on a model); `ask_llm_for_new_episodes` fills the cache
# from the background, then rebuilds. Until then an episode stays out.

def _llm_shows() -> dict[str, object]:
    return {p.id: p for p in PODCASTS if p.games_by_llm}


def _llm_episode(podcast, ep: Episode) -> dict | None:
    """What the LLM is shown of `ep`, or None for an item that isn't the show."""
    if podcast.skip_title and re.search(podcast.skip_title, ep.title):
        return None
    text = re.sub(r'\s+', ' ', _html_unescape(re.sub(r'<[^>]+>', ' ', ep.description or '')))
    return {
        'show':        podcast.name,
        'title':       ep.title,
        'date':        (datetime.datetime.fromtimestamp(ep.pub_ts, datetime.timezone.utc)
                        .date().isoformat() if ep.pub_ts else None),
        'description': text.strip()[:2000],
    }


def _apply_llm_games(episodes: list[Episode]) -> list[Episode]:
    """Give LLM-read episodes their games from the cache; keep out the ones not
    read yet, and the ones that review no game. Idempotent: the Episode objects
    are reused across 304s."""
    shows = _llm_shows()
    kept = []
    for ep in episodes:
        podcast = shows.get(ep.podcast_id)
        if podcast:
            payload = _llm_episode(podcast, ep)
            names = llm.reviewed_games(payload, cached_only=True) if payload else None
            if not names:
                continue
            # A few episodes have chapters (The Besties, 2014–16): point each game
            # at its own, as the title-parsed shows do.
            ep.games = []
            for n in names:
                chapter = find_chapter_for_game(n, ep.chapters)
                ep.games.append(GameMention(
                    name=n,
                    timestamp=chapter.timestamp if chapter else None,
                    timestamp_seconds=chapter.timestamp_seconds if chapter else 0))
        kept.append(ep)
    return kept


_llm_lock     = threading.Lock()
_LLM_PARALLEL = 4


def ask_llm_for_new_episodes(budget_s: float | None = None) -> int:
    """Ask the LLM about every fetched episode it hasn't read, then rebuild the
    catalog if any answered. Returns how many answered. A run already in
    progress makes this a no-op (the first launch reads hundreds of episodes)."""
    if not llm.enabled() or not _llm_lock.acquire(blocking=False):
        return 0
    try:
        deadline = time.monotonic() + budget_s if budget_s is not None else None
        todo = [payload for podcast in _llm_shows().values()
                for ep in _feed_episodes.get(podcast.id, [])
                if (payload := _llm_episode(podcast, ep)) is not None
                and llm.reviewed_games(payload, cached_only=True) is None]

        def read(payload) -> bool:
            if deadline is not None and time.monotonic() >= deadline:
                return False
            return llm.reviewed_games(payload) is not None

        # A few at a time: each call takes seconds, and the first launch has
        # hundreds of episodes to read.
        with ThreadPoolExecutor(_LLM_PARALLEL) as pool:
            answered = sum(pool.map(read, todo))
        if answered:
            logger.info('LLM read %d new episode(s); rebuilding the catalog', answered)
            rebuild()
        return answered
    finally:
        _llm_lock.release()
