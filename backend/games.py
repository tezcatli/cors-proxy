"""Blueprint at /games: the HTTP surface over the in-memory catalog.

The work lives elsewhere — `catalog_state` (the data), `feeds` (RSS → catalog),
`resolver` (IGDB resolution and the background tick), `serializers` (payloads),
`review` (the admin console's quality view). This module only validates
requests, caches the two big read payloads, and wires the rest together.

Handlers read the catalog directly; anything that writes it runs on the worker
(`worker.call`), so a request can't race the background sweep.
"""
import logging

from flask import Blueprint, abort, jsonify, request, Response

import catalog_state as state
import corrections
import feeds
import resolver
import review
import serializers
import worker
from auth import require_admin, require_auth
from igdb import search_games
from limiter import limiter
from models import PodcastGame
from podcasts import PODCAST_BY_ID
from questions import question_for
from serializers import Member
from utils import make_slug

logger = logging.getLogger(__name__)

games_bp = Blueprint('games', __name__, url_prefix='/games')
games_bp.before_request(require_auth)

# Serialised-response caches: (state.data_version, body_text, etag).
_catalog_cache: tuple | None = None
_feed_cache:    tuple | None = None


def _conditional_cached(cache, key, build_payload):
    """Conditional JSON response backed by a cached serialised body + ETag.

    `cache` is the current `(key, body_text, etag)` tuple (or None). On a hit the
    body is neither re-serialised nor re-hashed. Returns `(response, cache_tuple)`;
    the caller stores the returned tuple back under the lock.
    """
    if cache and cache[0] == key:
        resp = Response(cache[1], mimetype='application/json')
        resp.set_etag(cache[2])
    else:
        resp = jsonify(build_payload())
        resp.add_etag()
        cache = (key, resp.get_data(as_text=True), resp.get_etag()[0])
    resp.headers['Cache-Control'] = 'no-cache'
    return resp.make_conditional(request), cache


# ── Reads ─────────────────────────────────────────────────────────────────────

@games_bp.route('/episodes')
def games_episodes():
    global _feed_cache
    with state.lock:
        version  = state.data_version
        cache    = _feed_cache
        episodes = list(state.episodes)
    resp, new_cache = _conditional_cached(
        cache, version,
        lambda: [serializers.serialise_episode_slim(ep) for ep in episodes],
    )
    if new_cache is not cache:
        with state.lock:
            _feed_cache = new_cache
    return resp


@games_bp.route('/episode')
def games_episode():
    slug = request.args.get('slug')
    if not slug:
        abort(400, 'slug parameter is required')
    with state.lock:
        episode = state.episode_index.get(slug)
    if episode is None:
        abort(404, 'Episode not found')
    return jsonify(serializers.serialise_episode(episode))


@games_bp.route('', strict_slashes=False)
def catalog():
    global _catalog_cache
    # Read-only: the background tick keeps the feed fresh. The one exception is a
    # cold start whose startup fetch failed — there is nothing to serve yet.
    if not state.episodes:
        try:
            worker.call(feeds.refresh_feed, key='feeds')
        except Exception as exc:   # network error, malformed XML, etc.
            abort(502, f'RSS feed unavailable: {exc}')
        resolver.schedule_resolve()
    with state.lock:
        cache = _catalog_cache
        key   = state.data_version
    resp, new_cache = _conditional_cached(
        cache, key,
        lambda: {'games': serializers.build_catalog()},
    )
    if new_cache is not cache:
        with state.lock:
            _catalog_cache = new_cache
    return resp


@games_bp.route('/<string:slug>')
def game_detail(slug):
    return jsonify(serializers.load_game(slug))


# ── Refreshes ─────────────────────────────────────────────────────────────────

@games_bp.route('/refresh', methods=['POST'])
@limiter.limit("10 per minute")
def refresh():
    try:
        worker.call(feeds.refresh_feed, key='feeds')
    except Exception as exc:   # network error, malformed XML, etc.
        if not state.episodes:
            abort(502, f'RSS feed unavailable: {exc}')
        logger.warning('Manual refresh failed; serving cached catalog: %s', exc)
    # Even on a failed fetch: a previous tick may have brought in games that
    # haven't resolved yet, and the user is looking right now.
    worker.call(resolver.quick_pass, resolver.REFRESH_BUDGET_S, key='quick-pass')
    return jsonify({'games': serializers.build_catalog()})


def _purge_and_resolve(members: list[Member], cache) -> None:
    _purge_with_games(members, cache)
    resolver.resolve_members(members)


def _purge_with_games(members: list[Member], cache) -> int:
    """An explicit IGDB refresh: ask these appearances' questions again, and
    re-fetch the games they were answered with — the one way to get a game's data
    (and its Metacritic score) again before the TTL. Returns how many questions."""
    state.expire_games(e.igdb_id for _, a in members if (e := cache.get(a.podcast_slug)))
    keys = {question_for(g, a.episode).key for g, a in members}
    state.purge_cache(keys)
    return len(keys)


@games_bp.route('/<string:slug>/igdb-refresh', methods=['POST'])
@limiter.limit("10 per minute")
def game_igdb_refresh(slug):
    # This entry's appearances (by igdb_slug, or the name_slug fallback).
    members, cache, _ = serializers.match_appearances(slug)
    worker.call(_purge_and_resolve, members, cache)
    return jsonify(serializers.load_members(members, make_slug(slug)))


# ── Admin: resolution stats & corrections ─────────────────────────────────────

@games_bp.route('/resolution-stats')
def resolution_stats():
    require_admin()
    return jsonify(review.resolution_stats())


@games_bp.route('/igdb-search')
def igdb_search():
    require_admin()
    query = (request.args.get('q') or '').strip()
    if not query:
        abort(400, 'q parameter is required')
    try:
        results = search_games(query)
    except Exception as exc:
        logger.warning('IGDB search failed q=%r: %s', query, exc)
        abort(502, f'IGDB search failed: {exc}')
    return jsonify({'results': results})


def _correction_target(payload: dict) -> tuple[PodcastGame, str, list[Member]]:
    """Validate a correction request → (game, podcast_id, affected appearances).

    podcast_id '' scopes the correction to every podcast. Validated against the
    live catalog, so a name that no longer exists in the feed can't be written —
    the failure mode a hand-edited corrections.json has (see `unmatched_slugs`)."""
    name_slug  = (payload.get('nameSlug') or '').strip()
    podcast_id = (payload.get('podcastId') or '').strip()
    if not name_slug:
        abort(400, 'nameSlug is required')
    if podcast_id and podcast_id not in PODCAST_BY_ID:
        abort(400, f'Unknown podcastId: {podcast_id}')
    with state.lock:
        game = state.game_index.get(name_slug)
    if game is None:
        abort(404, 'Game not found')
    members = [(game, a) for a in game.appearances
               if not podcast_id or a.episode.podcast_id == podcast_id]
    if not members:
        abort(404, 'No appearances for that podcast')
    return game, podcast_id, members


def _answer_after_correction(members: list[Member]) -> None:
    """A correction changes the question these appearances ask: answer the new
    one, and drop the old one's answer, which nothing asks any more. Nothing to
    purge — and the games already cached are still good."""
    resolver.resolve_members(members)
    state.prune_igdb_cache()


def _require_writable():
    if not corrections.is_writable():
        abort(409, 'corrections.json is read-only in this deployment. Curate it in '
                   'dev, where the repo is bind-mounted, then commit and deploy.')


def _reresolve(members: list[Member], name_slug: str) -> dict:
    """Answer synchronously, so the response reflects the edited file."""
    worker.call(_answer_after_correction, members)
    return serializers.load_members(members, name_slug)


@games_bp.route('/corrections', methods=['PUT'])
@limiter.limit("30 per minute")
def set_correction():
    require_admin()
    _require_writable()
    payload = request.get_json(silent=True) or {}
    game, podcast_id, members = _correction_target(payload)

    igdb_id = payload.get('igdbId')
    if igdb_id is not None:
        try:
            igdb_id = int(igdb_id)
        except (TypeError, ValueError):
            abort(400, 'igdbId must be an integer')
    # Absent = leave the display name alone; '' = drop the override.
    display_name = payload.get('displayName', corrections._UNSET)
    if igdb_id is None and display_name is corrections._UNSET:
        abort(400, 'pass igdbId and/or displayName')

    # Keyed on the feed's own wording, which is what corrections.json matches on.
    corrections.upsert(game.name, podcast_id, igdb_id=igdb_id, display_name=display_name)

    if igdb_id is None:
        # A rename doesn't change which IGDB game this is — display_name is applied
        # at response time by group_display_name. Re-resolving would burn a round
        # of IGDB + Metacritic + HLTB calls to arrive at the same entry.
        state.bump_version()
        return jsonify(serializers.load_members(members, game.name_slug))
    return jsonify(_reresolve(members, game.name_slug))


@games_bp.route('/corrections', methods=['DELETE'])
@limiter.limit("30 per minute")
def delete_correction():
    require_admin()
    _require_writable()
    payload = request.get_json(silent=True) or {}
    game, podcast_id, members = _correction_target(payload)
    if not corrections.remove(game.name, podcast_id):
        abort(404, 'No correction at that scope')
    return jsonify(_reresolve(members, game.name_slug))


@games_bp.route('/podcasts/<string:podcast_id>/igdb-refresh', methods=['POST'])
@limiter.limit("2 per minute")
def podcast_igdb_refresh(podcast_id):
    require_admin()
    if podcast_id not in PODCAST_BY_ID:
        abort(404, 'Unknown podcast')
    with state.lock:
        members = [(game, a) for game in state.game_index.values() for a in game.appearances
                   if a.episode.podcast_id == podcast_id]
    purged = worker.call(lambda: _purge_with_games(members, state.entries()))
    # Background sweep (this can be hundreds of rate-limited IGDB calls); the
    # console shows progress through `pending` in /resolution-stats.
    resolver.schedule_resolve()
    return jsonify({'purged': purged})
