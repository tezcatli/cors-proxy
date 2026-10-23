"""The admin console's view of resolution quality: which games look mis-resolved."""
import corrections
import ingest
import resolver
import transcribe
from corrections import find_by_podcast
from models import IgdbEntry
from podcasts import PODCASTS
from serializers import Member, best_member, correction_for, group_members
from utils import norm, norm_key

_ROMAN = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
          'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}


def _numerals(text: str) -> str:
    """norm() with standalone roman numerals folded to digits: the podcast writes
    «Hades 2», IGDB says «Hades II». Only whole tokens convert, and both sides get
    the same treatment, so this can only ever make a comparison more lenient."""
    return ' '.join(_ROMAN.get(w, w) for w in norm(text).split())


# Share of words the two names have in common, above which they're taken to be
# the same game. Tuned against the live catalog: 0.5 clears reorderings and
# plurals ("Senua's Saga Hellblade II" / "Hellblade II: Senua's Saga") while
# still flagging "Astrobot" → "Astrobotanica".
_SUSPECT_OVERLAP = 0.5


def is_suspect(podcast_name: str, igdb_name: str) -> bool:
    """True when the IGDB name looks unrelated to the podcast name.

    A flag for human review, not a verdict — so it is deliberately biased toward
    letting things through: a false positive buries the real misses in noise,
    while a miss is still correctable from the game's own page. Passes when the
    names differ only in spacing ("Astrobot"/"Astro Bot"), numeral style
    ("Hades 2"/"Hades II"), a subtitle ("Kirby" → "Kirby and the Forgotten
    World"), or word order/plurals. Flags "Astrobot" → "Astrobotanica".
    Tuned on the live catalogue from 68 mostly-noise rows to ~50 mostly-real ones;
    known false positives: abbreviations ("GTA V") and French titles ("Le Vaillant
    Petit Page" → "The Plucky Squire").
    """
    if norm_key(podcast_name) == norm_key(igdb_name):
        return False
    a, b = _numerals(podcast_name), _numerals(igdb_name)
    if not a or not b or a == b:
        return False
    # Whole-word prefix or containment: a subtitle or a series name.
    if b.startswith(f'{a} ') or a.startswith(f'{b} '):
        return False
    if f' {a} ' in f' {b} ' or f' {b} ' in f' {a} ':
        return False
    # Otherwise fall back to how many words they share, which survives reordering
    # and plural/spelling drift that prefix matching can't.
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / max(len(wa), len(wb)) < _SUSPECT_OVERLAP


def _group_summary(slug: str, members: list[Member],
                   best: tuple[Member, IgdbEntry] | None) -> dict:
    # Report the group under its representative name — the one that actually
    # produced the resolution — not whichever variant happens to sort first.
    # `nameSlugs` lists them all: a group merging several spellings has no single
    # correction target, and the client must not silently pin only one of them.
    game  = best[0][0] if best else members[0][0]
    entry = best[1]    if best else None
    correction = correction_for(members)

    # Classified here rather than filtered here: the admin console shows every
    # group and filters client-side, so a correctly-resolved game stays findable.
    if entry is None:
        status = 'unresolved'
    elif is_suspect(game.name, entry.name or '') and not correction:
        status = 'suspect'
    else:
        status = 'resolved'

    # Newest appearance — the episode a reviewer would open to judge the match.
    newest = max(members, key=lambda m: m[1].episode.pub_ts or 0)[1].episode
    return {
        'status':       status,
        'corrected':    correction is not None,
        'displayName':  (correction or {}).get('display_name'),
        'slug':         slug,
        'name':         game.name,
        'nameSlug':     game.name_slug,
        'nameSlugs':    sorted({g.name_slug for g, _ in members}),
        'igdbName':     entry.name      if entry else None,
        'igdbSlug':     entry.igdb_slug if entry else None,
        'coverImageId': (entry.data or {}).get('coverImageId') if entry else None,
        'released':     (entry.data or {}).get('released') if entry else None,
        'podcasts':     sorted({a.episode.podcast_id for _, a in members if a.episode.podcast_id}),
        'episodeCount': len({a.episode.slug for _, a in members}),
        'latestPubTs':  newest.pub_ts,
        'episodeSlug':  newest.url_slug or newest.slug,
        'episodeTitle': newest.title,
    }


def resolution_stats() -> dict:
    groups, cache = group_members()

    # Per-podcast tallies are counted over appearances (an appearance belongs to
    # exactly one podcast), while the lists below are per catalog entry.
    ingestion = ingest.stats()
    per_podcast = {
        p.id: {'id': p.id, 'label': p.label, 'name': p.name,
               'appearances': 0, 'resolved': 0, 'failed': 0,
               'retrying': 0, 'pending': 0, 'corrected': 0,
               **ingestion.get(p.id, {'episodes': 0, 'transcribed': 0, 'read': 0,
                                      'ingestErrors': 0})}
        for p in PODCASTS
    }
    rows = []

    for slug, members in groups.items():
        for game, appearance in members:
            stats = per_podcast.get(appearance.episode.podcast_id)
            if stats is None:
                continue
            stats['appearances'] += 1
            cached = cache.get(appearance.podcast_slug)
            if cached is not None and cached.igdb_id is not None:
                stats['resolved'] += 1
            elif cached is not None and not cached.resolution.retry_at:
                # A negative cache: IGDB was asked and had nothing. Never-cached
                # rows are neither — only pending.
                stats['failed'] += 1
            if cached is not None and cached.resolution.retry_at:
                # Erroring (IGDB down, LLM unavailable), waiting out its backoff.
                stats['retrying'] += 1
            if resolver.appearance_pending(game, appearance, cache):
                stats['pending'] += 1
            if find_by_podcast(game.name, appearance.episode.pub_ts,
                               appearance.episode.podcast_id):
                stats['corrected'] += 1

        rows.append(_group_summary(slug, members, best_member(members, cache)))

    # Every group, classified by `status` rather than split into fixed lists: the
    # console filters client-side, so a correctly-resolved game stays searchable
    # (the old suspects/unresolved split made ~1500 games unreachable). Newest
    # first — the default review order.
    rows.sort(key=lambda r: r['latestPubTs'] or 0, reverse=True)

    return {
        'podcasts':  list(per_podcast.values()),
        'games':     rows,
        # False in prod: corrections.json ships in the read-only image layer, so
        # curation happens in dev and lands in git. Drives the UI's read-only state.
        'writable':  corrections.is_writable(),
        'pending':   resolver.count_pending(),
        'resolving': resolver.is_resolving(),
        # Hours transcribed and their cost, all shows together; `enabled` = a
        # DeepInfra key, without which nothing more gets transcribed.
        'transcription': {'enabled': transcribe.enabled(), **transcribe.totals()},
    }
