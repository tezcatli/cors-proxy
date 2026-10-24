"""Turning the in-memory catalog into response payloads.

A catalog entry is a group of *appearances* that resolved to the same IGDB game —
not a group of podcast names. Grouping by name would force every appearance of
one name onto a single IGDB entry, so a retrospective episode on Silent Hill 2
(2001) and a review of the 2024 remake would collapse into one, each hiding the
other's episodes. `Member` pairs an appearance with its owning PodcastGame
(needed for the name_slug fallback key and the display name).
"""
from flask import abort

import catalog_state as state
from corrections import find_by_podcast
from models import Episode, GameAppearance, IgdbEntry, PodcastGame
from podcasts import podcast_meta
from utils import make_slug

Member = tuple[PodcastGame, GameAppearance]


# ── Grouping ──────────────────────────────────────────────────────────────────

def _group_key(game: PodcastGame, appearance: GameAppearance,
               cache: dict[str, IgdbEntry]) -> str:
    """The catalog slug an appearance belongs to: its own IGDB slug once resolved,
    else the game's name_slug so unresolved appearances of a name stay together."""
    entry = cache.get(appearance.podcast_slug)
    return entry.igdb_slug if entry and entry.igdb_slug else game.name_slug


def best_member(members: list[Member],
                cache: dict[str, IgdbEntry]) -> tuple[Member, IgdbEntry] | None:
    """The representative (member, entry) of a group, or None when none resolved.

    Prefers non-child entries (a canonical game over a DLC/version redirected to
    its parent); among equals, the most recently resolved.
    """
    candidates = [
        (m, cache[m[1].podcast_slug]) for m in members
        if m[1].podcast_slug in cache and cache[m[1].podcast_slug].igdb_slug
    ]
    if not candidates:
        return None
    non_child = [c for c in candidates if not c[1].is_child]
    pool      = non_child if non_child else candidates
    return max(pool, key=lambda c: c[1].resolution.decided_at)


def group_members() -> tuple[dict[str, list[Member]], dict[str, IgdbEntry]]:
    """Every appearance in the catalog bucketed by group key, plus the IGDB cache
    snapshot the keys were derived from — callers must rank within a group against
    that same snapshot, or a concurrent resolution could move an entry between the
    two reads."""
    with state.lock:
        games = dict(state.game_index)
    cache = state.entries()
    groups: dict[str, list[Member]] = {}
    for game in games.values():
        for appearance in game.appearances:
            groups.setdefault(_group_key(game, appearance, cache), []).append((game, appearance))
    return groups, cache


def correction_for(members: list[Member]) -> dict | None:
    """The corrections.json entry ruling on these appearances, if any. Such a
    resolution is intentional however little the names look alike («Les gardiens
    de la galaxie» → «Marvel's Guardians of the Galaxy»), so it stays out of the
    review queue — and it drives the UI's "remove the correction" affordance and
    the display-name field."""
    return next((c for g, a in members
                 if (c := find_by_podcast(g.name, a.episode.pub_ts,
                                          a.episode.podcast_id))), None)


def group_display_name(members: list[Member],
                       best: tuple[Member, IgdbEntry] | None) -> str:
    """Display name for a catalog group: corrections override > IGDB canonical >
    raw podcast name. The correction is looked up against the representative
    appearance's own wording and episode date, since a dated correction only
    applies to the episode it was written for."""
    if best:
        (game, appearance), entry = best
        if not entry.is_child:
            corr = find_by_podcast(appearance.mention.name, appearance.episode.pub_ts,
                                   appearance.episode.podcast_id)
            if corr and corr.get('display_name'):
                return corr['display_name']
        if entry.name:
            return entry.name
        return game.name
    return members[0][0].name


# ── Episodes ──────────────────────────────────────────────────────────────────

def _resolution(mention, episode: Episode) -> tuple[str, str, str | None] | None:
    """(igdb_name, igdb_slug, cover_image_id) of one of the episode's games, or
    None while it has no page."""
    game  = state.game_index.get(make_slug(mention.name))
    entry = state.entry(game, episode) if game else None
    if not (entry and entry.igdb_slug):
        return None
    cover_image_id = entry.data.get('coverImageId') if entry.data else None
    return entry.name or mention.name, entry.igdb_slug, cover_image_id


def _build_resolved(episode: Episode) -> dict[str, tuple[str, str, str | None]]:
    """Build a timestamp → (igdb_name, igdb_slug, cover_image_id) map for one episode."""
    return {m.timestamp: r for m in episode.games
            if m.timestamp and (r := _resolution(m, episode))}


def _game(mention, episode: Episode) -> dict:
    """One of the episode's tests: its name, start, page and cover when it has one."""
    entry: dict = {'name': mention.name, 'timestamp': mention.timestamp,
                   'timestampSeconds': mention.timestamp_seconds}
    if r := _resolution(mention, episode):
        entry['resolvedName'], entry['slug'] = r[0], r[1]
        if r[2]:
            entry['coverImageId'] = r[2]
    return entry


def serialise_episode(episode: Episode, mention=None) -> dict:
    """Serialise an Episode to the single canonical JSON shape used everywhere,
    its chapters and games annotated with their IGDB resolution.

    `mention`, when given (game-detail context), fills the top-level timestamp
    fields with that game's position in the episode; otherwise they default to
    None/0 (whole-episode context).
    """
    resolved = _build_resolved(episode)
    chapters = []
    for chapter in episode.chapters:
        ch: dict = {
            'timestamp':        chapter.timestamp,
            'timestampSeconds': chapter.timestamp_seconds,
            'title':            chapter.title,
        }
        if chapter.timestamp in resolved:
            igdb_name, igdb_slug, cover_image_id = resolved[chapter.timestamp]
            ch['resolvedName'] = igdb_name
            ch['slug']         = igdb_slug
            if cover_image_id:
                ch['coverImageId'] = cover_image_id
        chapters.append(ch)

    games = [{**_game(g, episode), 'critique': g.critique} for g in episode.games]

    return {
        'title':            episode.title,
        'slug':             episode.slug,
        'urlSlug':          episode.url_slug,
        'audioUrl':         episode.audio_url,
        'pubTs':            episode.pub_ts,
        'imageUrl':         episode.image_url,
        'description':      episode.description,
        'chapters':         chapters,
        'games':            games,
        'podcast':          podcast_meta(episode.podcast_id),
        'timestamp':        mention.timestamp        if mention else None,
        'timestampSeconds': mention.timestamp_seconds if mention else 0,
        # That game's test: {verdict, pros, cons, at}; None outside a game's
        # context, or while the episode is unread.
        'critique':         mention.critique          if mention else None,
    }


def _verdict(mention) -> str | None:
    """A test's verdict alone (`llm.VERDICTS`); None while unread or when the
    hosts give none."""
    return (mention.critique or {}).get('verdict')


def serialise_episode_slim(episode: Episode) -> dict:
    """Lightweight episode shape for the feed *list* (`GET /games/episodes`).

    Omits `description` and `chapters` — together ~70% of the full feed payload —
    since the feed's test cards (TestCard) never read them; they're served by the
    single-episode endpoint instead. `games` is kept, each with its page, cover and
    verdict: the feed shows an episode by its tests (and its names power the
    client-side search)."""
    return {
        'title':            episode.title,
        'slug':             episode.slug,
        'urlSlug':          episode.url_slug,
        'audioUrl':         episode.audio_url,
        'pubTs':            episode.pub_ts,
        'imageUrl':         episode.image_url,
        'games':            [{**_game(g, episode), 'verdict': _verdict(g)}
                             for g in episode.games],
        'podcast':          podcast_meta(episode.podcast_id),
        'timestamp':        None,
        'timestampSeconds': 0,
    }


# ── Catalog and game detail ───────────────────────────────────────────────────

def build_catalog() -> list[dict]:
    result = []
    groups, cache = group_members()
    for slug, members in groups.items():
        best  = best_member(members, cache)
        entry = best[1] if best else None
        igdb_slim = {
            'metacritic':   entry.data.get('metacritic'),
            'coverImageId': entry.data.get('coverImageId'),
        } if entry and entry.data else None
        # Count distinct episodes (by guid) — two name variants co-occurring in one
        # episode must not double-count it.
        episode_slugs = {a.episode.slug for _, a in members}
        pub_tss       = [a.episode.pub_ts for _, a in members if a.episode.pub_ts is not None]
        # Source podcasts that cover this game (drives badges + the header filter).
        podcasts = sorted({a.episode.podcast_id for _, a in members if a.episode.podcast_id})
        # One verdict per test, newest first: no rule averages a game's tests.
        tests = {}
        for _, a in sorted(members, key=lambda m: m[1].episode.pub_ts or 0, reverse=True):
            tests.setdefault(a.episode.slug, _verdict(a.mention))
        result.append({
            'slug':         slug,
            'name':         group_display_name(members, best),
            'igdb':         igdb_slim,
            'episodeCount': len(episode_slugs),
            'latestPubTs':  max(pub_tss) if pub_tss else None,
            'podcasts':     podcasts,
            'verdicts':     list(tests.values()),
        })

    return sorted(result, key=lambda g: g['name'].lower())


def match_appearances(slug: str) -> tuple[list[Member], dict[str, IgdbEntry], bool]:
    """The appearances that make up the catalog entry `slug`, the cache snapshot
    they were grouped against, and whether the match was a resolved igdb_slug.

    Falls back to the name_slug group (unresolved appearances of that name) and,
    for a name whose appearances have since all resolved, to every appearance of
    the name — so an old /game/<name_slug> link still lands somewhere sensible
    instead of 404ing. Aborts 404 when nothing matches.
    """
    groups, cache = group_members()
    if slug in groups and any(
            (e := cache.get(a.podcast_slug)) and e.igdb_slug == slug for _, a in groups[slug]):
        return groups[slug], cache, True
    name_slug = make_slug(slug)
    if name_slug in groups:
        return groups[name_slug], cache, False
    with state.lock:
        game = state.game_index.get(name_slug)
    if game:
        return [(game, a) for a in game.appearances], cache, False
    abort(404, 'Game not found')


def load_game(slug: str) -> dict:
    """Game-detail response for an igdb_slug (or a name_slug fallback for an
    unresolved game). `igdb` is the data dict or None; `nameSlugs` lists the raw
    podcast names behind the entry, which the corrections API keys on."""
    members, cache, resolved = match_appearances(slug)
    # Newest first: a group can mix appearances from several name variants and
    # both podcasts, whose per-name order says nothing about the group's.
    ordered    = sorted(members, key=lambda m: m[1].episode.pub_ts or 0, reverse=True)
    correction = correction_for(members)
    payload = {
        'episodes':  [serialise_episode(a.episode, mention=a.mention) for _, a in ordered],
        'nameSlugs': sorted({g.name_slug for g, _ in members}),
        # Lets the admin UI offer "remove the correction" without a second call,
        # and pre-fill the picker's « Nom affiché » field with the current
        # override (top-level `name` may already *be* that override).
        'corrected':   correction is not None,
        'displayName': (correction or {}).get('display_name'),
    }
    # `resolved` guarantees a member entry carries this igdb_slug, so best is set.
    if resolved and (best := best_member(members, cache)):
        # igdbName is the entry's true IGDB name — what the picker shows as the
        # current resolution, unaffected by a display_name override.
        return {**payload, 'slug': slug, 'igdbName': best[1].name,
                'name': group_display_name(members, best), 'igdb': best[1].data}
    return {**payload, 'slug': make_slug(slug), 'igdbName': None,
            'name': members[0][0].name, 'igdb': None}


def load_members(members: list[Member], name_slug: str) -> dict:
    """Game detail for these appearances as they currently resolve — they may have
    moved to another igdb_slug (or back to `name_slug`) since they were collected."""
    _, cache = group_members()
    best = best_member(members, cache)
    return load_game(best[1].igdb_slug if best and best[1].igdb_slug else name_slug)
