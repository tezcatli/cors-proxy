"""Fetching the podcast feeds and rebuilding the in-memory catalog from them.

Everything here that writes runs on the worker (`worker.py`), one job at a time,
so none of it takes a lock of its own beyond `catalog_state.lock` for readers.
"""
import datetime
import json
import logging
import pathlib
import re
import time

import requests as http

import catalog_state as state
import critiques
import llm
import transcribe
from config import Config
from corrections import unmatched_slugs
from db import utcnow
from models import Chapter, Episode, GameAppearance, GameMention, PodcastGame
from podcasts import PODCASTS, PODCAST_BY_ID
from rss import parse_feed, assign_url_slugs, is_game_catalog_excluded, find_chapter_for_game
from utils import make_slug, plain_text

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
        _point_mentions(episode)
        injected += 1
    if injected:
        logger.info('Injected AI chapters into %d episodes', injected)


def _point_mentions(episode: Episode) -> None:
    """Start each game mention at its chapter, once the episode has chapters."""
    for mention in episode.games:
        matched = find_chapter_for_game(mention.name, episode.chapters)
        if matched:
            mention.timestamp = matched.timestamp
            mention.timestamp_seconds = matched.timestamp_seconds


# ── Transcript readings ───────────────────────────────────────────────────────
# What the LLM read in an episode's transcript (`ingest.py`): its sections, the
# game each is about and the hosts' verdict. Only cached readings are used while
# rebuilding, as for the games read from descriptions.

def _readings(episodes: list[Episode]) -> dict[str, list[dict]]:
    """The cached reading of every transcribed episode, by guid."""
    models = {guid: row.model for guid, row in transcribe.rows().items() if row.model}
    return {ep.slug: sections for ep in episodes
            if ep.slug in models and ep.podcast_id in PODCAST_BY_ID
            and (sections := llm.read_transcript(transcribe.reading_input(ep, models[ep.slug])))
            is not None}


# The games an episode's reading proposes as tests: the ones its hosts judge —
# a critique or a palmarès' entry. Which are tests is `critiques.select`'s call
# (five minutes, no palmarès-only game, the title's game vetoed by a reading
# that hears it only in the news). The reading only describes each section
# (`llm.KINDS`), so this can change without reading again.
CRITIQUE_KINDS = {'review', 'impressions', 'ranking'}


def _game_sections(sections: list[dict]) -> list[dict]:
    """The sections that critique a game, once per game."""
    first: dict[str, dict] = {}
    for s in sections:
        if s['kind'] in CRITIQUE_KINDS:
            first.setdefault(make_slug(s['game']), s)
    return list(first.values())


def _read_games(sections: list[dict]) -> list[str]:
    """The games an episode is about, by its reading."""
    return [s['game'] for s in _game_sections(sections)]


def _as_chapter(section: dict, title: str) -> Chapter:
    return Chapter(timestamp=_seconds_to_ts(section['start']),
                   timestamp_seconds=section['start'], title=title, game_name=section['game'])


def _apply_readings(episodes: list[Episode], readings: dict[str, list[dict]]) -> None:
    """What an episode's reading makes of it. The title proposes, the reading
    confirms: a game the title names is kept when the reading finds a section of
    it, whatever kind — a special's title is not a game («Le 500e épisode en
    public», «et plein d'autres»). The reading adds the games it critiques that
    the title doesn't name — a show's title names two games, its hour on
    Microïds' catalogue five more — gives each game its critique, and chapters
    an episode that has none of its own (ads left out). Which of those games
    are tests, and where each starts, is `critiques.select`'s. Idempotent: the Episode
    objects are reused across 304s; what the title proposed is set aside, and
    the games are rebuilt from it on every pass."""
    for ep in episodes:
        if ep.proposed is None:
            ep.proposed = list(ep.games)
        for mention in ep.proposed:
            mention.critique = None
        sections = readings.get(ep.slug)
        if not sections:
            ep.games = list(ep.proposed)
            continue
        spoken = [_as_chapter(s, s['game']) for s in sections if s['game']]
        ep.games = [m for m in ep.proposed if find_chapter_for_game(m.name, spoken)]
        if not ep.chapters or ep.chapters_read:
            ep.chapters = [_as_chapter(s, s['title']) for s in sections if not s['ad']]
            ep.chapters_read = True
            _point_mentions(ep)
        for section in _game_sections(sections):
            named = [Chapter(m.timestamp or '', m.timestamp_seconds, m.name, m.name)
                     for m in ep.games]
            matched = find_chapter_for_game(section['game'], named)
            if matched:
                mention = ep.games[named.index(matched)]
            else:
                mention = GameMention(name=section['game'], timestamp=_seconds_to_ts(section['start']),
                                      timestamp_seconds=section['start'], read=True)
                ep.games.append(mention)
            mention.critique = section['opinion']
        ep.games = critiques.select(PODCAST_BY_ID[ep.podcast_id], ep, sections)


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

        if is_game_catalog_excluded(episode.title) or (
                episode.podcast_id in PODCAST_BY_ID and critiques.palmares(PODCAST_BY_ID[episode.podcast_id], episode.title)):
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


def refresh_feed() -> None:
    """Fetch every registered podcast, then recombine all feeds into one catalog.

    Each feed is fetched independently (per-feed ETag); a single feed failing
    doesn't abort the others as long as we already have cached episodes for it.
    If *no* feed yields any episodes, the whole refresh raises so the caller can
    keep serving the previous cache rather than blanking it.
    """
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
    _rebuild([])


def _rebuild(errors: list[str]) -> None:
    """Combine every feed's episodes into the catalog."""
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
    readings = _readings(episodes)
    episodes = _apply_llm_games(episodes, readings)

    assign_url_slugs(episodes)
    inject_ai_chapters(episodes, _load_ai_chapter_index())
    _apply_readings(episodes, readings)
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
    # With every feed in, the catalog is whole: the legacy decisions can be
    # matched to the questions their appearances ask.
    state.reconcile(complete=all(p.id in _feed_episodes for p in PODCASTS))


# ── Games read by the LLM ─────────────────────────────────────────────────────
# Shows with `games_by_llm`: an episode's games are whatever the LLM said it
# critiques. Only cached answers are used while rebuilding, which must not wait on
# a model; the cache is filled one episode per worker job (`resolver.schedule_llm_reads`)
# or, within POST /refresh's budget, by `read_new_episodes`. Until then an episode
# stays out.

def _llm_shows() -> dict[str, object]:
    return {p.id: p for p in PODCASTS if p.games_by_llm}


def _llm_episode(podcast, ep: Episode) -> dict | None:
    """What the LLM is shown of `ep`, or None for an item that isn't the show."""
    if podcast.skip_title and re.search(podcast.skip_title, ep.title):
        return None
    return {
        'show':        podcast.name,
        'title':       ep.title,
        'date':        (datetime.datetime.fromtimestamp(ep.pub_ts, datetime.timezone.utc)
                        .date().isoformat() if ep.pub_ts else None),
        'description': plain_text(ep.description)[:2000],
    }


def _apply_llm_games(episodes: list[Episode],
                     readings: dict[str, list[dict]] | None = None) -> list[Episode]:
    """Give LLM-read episodes their games from the cache — from the transcript's
    reading once there is one, from the description's until then; keep out the
    ones not read yet, and the ones about no game. Idempotent: the Episode
    objects are reused across 304s."""
    shows = _llm_shows()
    kept = []
    for ep in episodes:
        podcast = shows.get(ep.podcast_id)
        if podcast:
            payload = _llm_episode(podcast, ep)
            # An older prompt's answer stands in until the current one is cached,
            # so a prompt change doesn't drop these episodes (and, with them,
            # their IGDB resolutions) for the half hour the re-read takes.
            if payload is None:
                names = None
            elif (readings or {}).get(ep.slug) is not None:
                names = _read_games(readings[ep.slug])
            else:
                names = llm.reviewed_games(payload, cached_only=True, any_version=True)
            if not names:
                continue
            # A few episodes have chapters (The Besties, 2014–16): point each game
            # at its own, as the title-parsed shows do.
            ep.games, ep.proposed = [], None   # proposed anew from this pass's names
            for n in names:
                chapter = find_chapter_for_game(n, ep.chapters)
                ep.games.append(GameMention(
                    name=n,
                    timestamp=chapter.timestamp if chapter else None,
                    timestamp_seconds=chapter.timestamp_seconds if chapter else 0))
        kept.append(ep)
    return kept


def all_episodes() -> list[Episode]:
    """Every fetched episode that is the show, newest first — the catalog leaves
    out the LLM-read shows' episodes not read yet, the ingestion must not."""
    return sorted((ep for podcast in PODCASTS for ep in _feed_episodes.get(podcast.id, [])
                   if not (podcast.skip_title and re.search(podcast.skip_title, ep.title))),
                  key=lambda e: e.pub_ts or 0, reverse=True)


def unread_episodes() -> list[dict]:
    """What the LLM is shown of every fetched episode it hasn't read yet."""
    if not llm.enabled():
        return []
    return [payload for podcast in _llm_shows().values()
            for ep in _feed_episodes.get(podcast.id, [])
            if (payload := _llm_episode(podcast, ep)) is not None
            and llm.reviewed_games(payload, cached_only=True) is None]


def read_episode(payload: dict) -> bool:
    """Ask the LLM about one episode; True once it has answered (now or before)."""
    return llm.reviewed_games(payload) is not None


def read_new_episodes(deadline: float | None = None) -> int:
    """Read every unread episode — until the monotonic `deadline`, if given — and
    rebuild the catalog if any answered. Returns how many answered."""
    answered = 0
    for payload in unread_episodes():
        if deadline is not None and time.monotonic() >= deadline:
            break
        answered += read_episode(payload)
    if answered:
        logger.info('LLM read %d new episode(s); rebuilding the catalog', answered)
        rebuild()
    return answered
