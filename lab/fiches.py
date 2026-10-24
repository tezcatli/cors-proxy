"""A variant of the resolution — which IGDB entry a test is — measured against
the app's. What it changes, from the measured misses:

- the date decides only between namesakes: a show covering new releases talks
  about older games too, and the app's judge rejected the one candidate named
  exactly (CrossCode, 2018, on a 2025 episode → « none fits »);
- the entry is the one named, never redirected to a parent game (« Miles
  Morales » isn't Marvel's Spider-Man, « The Lost and Damned » isn't GTA IV);
- the episode's date is always given, even for a retrospective show: the game
  existed by then;
- other titles are searched for every show, the LLM-read ones included: the
  name they read can be misspelled (« Donkey Kong Bonanza »).

Its answers are kept in the lab's cache (`lab_fiches`), filled by
`python resolve.py --fiches`; the pages read them, cached only.

Several versions, measured against each other on every judged test
(`VERSIONS`), the score choosing — not a reading of one case: v4's « an exact
name wins », added for one case (Trails from Zero), broke three others on the
control set (Fire Emblem 2013 → the 2003 one). v1 is the first; v4 adds other
titles for every show and the exact name; v6 is given what the episode says
about the game (its sections' titles, pros and cons, the description) and lets
the date decide only what that doesn't. Measured and dropped: the description
alone as context (v5) changed nothing. v7 is v1 with v4's other titles for every
show, and « the main game over an edition » instead of « the original over a
port » (which, once other titles were searched, sent Trails from Zero to Zero no
Kiseki). v8 is v1 searching other titles only when no candidate bears the name
exactly (« Donkey Kong Bonanza », « Spiderbot »): an exact candidate brings no
namesakes in (« Trails from Zero » doesn't fetch « Zero no Kiseki »).

Measured on the 114 judged tests, v1, v4, v7 and v8 each end with two wrong
entries, never the same two: each fixes one (Fire Emblem 2013, Donkey Kong
Bonanza, Trails from Zero, Spiderbot) and breaks another — the limits of
IGDB's search for a name written otherwise. v1, the simplest, is kept; no
version is tuned for one case any more.

v9 changes no prompt and no rule, only the evidence v1's judge is shown — what
IGDB's free-text search misses, ported since (`resolver._unsearched`: every
version gathers it now, the answers measured before it are kept): the entries the catalog already gave
a name spelled alike (`critiques.same`: « BALLxPIT » is « Ball x Pit », the
Besties' answer), the games IGDB lists the name as an alternative name of
(« Rhythm Paradise Groove », « Indiana Jones et le Cercle Ancien »), and each
candidate's first release, early access included (« 33 Immortals », out in
early access five days before the episode, shown as its 1.0 a year later).
New candidates come in only when one of their releases is within the question's
window: an alternative name brought David Bowie's 1994 « Jump » to a 2009 show.

Measured on the 211 judged tests: v1 ends with seven wrong entries (the four
new shows' names IGDB's search misses, Donkey Kong Bonanza, Spiderbot,
Uninvited), v9 with two (Spiderbot; Overwatch, two entries named alike that v9
dates differently, which the same evidence sent either way when asked again).
Over the whole catalog, 43 of the 84 tests without an entry get one (42 right,
« L'histoire de Tomb Raider » debatable), and on 200 tests drawn among those
with one, v9 lands on the same catalog page, but for Super Mario 3D World's
2021 edition on a 2021 episode.

The LLM's noise is measured apart: picks are cached by prompt, as the app
caches them, so a version sharing v1's prompt is shown v1's answer for the same
evidence — Fire Emblem 2013 went to Awakening for v1 and, asked again with the
same evidence, to the 2003 one.
"""
import datetime
import json
from types import SimpleNamespace

import db
import igdb
import llm
import resolver
from podcasts import PODCAST_BY_ID
from questions import question_for
from utils import make_slug, norm_key, plain_text

_V1 = """You help match a video game named in a podcast episode to the IGDB database.
Given the name as the podcast wrote it, the episode (show, what it covers, its
title and date) and IGDB candidates (id, name, other names, release date), pick
the candidate that IS the game named.
- Judge from the names first: the candidate whose name or other name is the game
  named, however spelled. The game may be newer than anything you know.
- A podcast discusses games of any age — a show covering new releases talks
  about older games too — so a release date never rules a candidate out, except
  a game released long after the episode.
- Use the dates only to choose between candidates of the same name (a remake and
  its original, namesakes): for a show covering new releases, the one out
  shortly before the episode (or soon after, for a preview); otherwise the most
  likely given the episode's title.
- Pick exactly what is named: a standalone expansion or spin-off named as such
  is that entry, not its parent game; prefer the original release over a bundle,
  edition or port unless the name says otherwise.
If no candidate is the game named, answer null.
Answer with JSON only: {"id": <candidate id or null>}"""

_V4 = """You help match a video game named in a podcast episode to the IGDB database.
Given the name as the podcast wrote it, the episode (show, what it covers, its
title and date) and IGDB candidates (id, name, other names, release date), pick
the candidate that IS the game named.
- Judge from the names first: the candidate whose name or other name is the game
  named, however spelled. When one candidate's name is exactly the name given,
  it is that one: the rules below only choose between candidates that all match
  the name. The game may be newer than anything you know.
- A podcast discusses games of any age — a show covering new releases talks
  about older games too — so a release date never rules a candidate out, except
  a game released long after the episode.
- Use the dates only to choose between candidates of the same name (a remake and
  its original, namesakes): for a show covering new releases, the one out
  shortly before the episode (or soon after, for a preview); otherwise the most
  likely given the episode's title.
- Pick exactly what is named: a standalone expansion or spin-off named as such
  is that entry, not its parent game; prefer the original release over a bundle,
  edition or port unless the name says otherwise — never a differently named
  original over the release named.
If no candidate is the game named, answer null.
Answer with JSON only: {"id": <candidate id or null>}"""

_V7 = """You help match a video game named in a podcast episode to the IGDB database.
Given the name as the podcast wrote it, the episode (show, what it covers, its
title and date) and IGDB candidates (id, name, other names, release date), pick
the candidate that IS the game named.
- Judge from the names first: the candidate whose name or other name is the game
  named, however spelled. The game may be newer than anything you know.
- A podcast discusses games of any age — a show covering new releases talks
  about older games too — so a release date never rules a candidate out, except
  a game released long after the episode.
- Use the dates only to choose between candidates of the same name (a remake and
  its original, namesakes): for a show covering new releases, the one out
  shortly before the episode (or soon after, for a preview); otherwise the most
  likely given the episode's title.
- Pick exactly what is named: a standalone expansion or spin-off named as such
  is that entry, not its parent game; prefer the main game over a bundle, an
  edition, a season or a DLC unless the name says otherwise. A localised title
  names that release, not the original it translates.
If no candidate is the game named, answer null.
Answer with JSON only: {"id": <candidate id or null>}"""

_V6 = """You help match a video game discussed in a podcast episode to the IGDB database.
Given the name as the podcast wrote it, the episode (show, what it covers, its
title, description and date), what the hosts say about the game (the sections
on it: their titles, the pros and cons heard) and IGDB candidates (id, name,
other names, release date), pick the candidate that IS the game discussed.
- The candidates that can be it are those whose name or other name is the game
  named, however written: spelled differently, abbreviated, a subtitle left out,
  a localised title. The game may be newer than anything you know.
- Among them, what the episode says decides: a subtitle, a platform, a remake or
  a remaster, a release it mentions.
- When it doesn't say, the date decides: a show covering new releases discusses
  the one released shortly before the episode (or soon after, for a preview),
  never one released years after it; a retrospective show, the original release.
- An expansion or spin-off named as such is that entry, not its parent game.
Answer null only when no candidate can be the game named.
Answer with JSON only: {"id": <candidate id or null>}"""

# version → (prompt, other titles searched for every show, the episode's evidence
# given). titles: False (v1: only for the shows whose names aren't an LLM's),
# True (every show), 'fallback' (every show, only when no candidate bears the
# name exactly). v9 is v1 with the evidence now in `resolver.gather_evidence`.
VERSIONS = {1: (_V1, False, False), 4: (_V4, True, False), 6: (_V6, True, True), 7: (_V7, True, False),
            8: (_V1, 'fallback', False), 9: (_V1, False, False)}
DEFAULT = 9   # chosen by the score on every judged test (v1 4 6 7 8 9 measured)


def _table(conn) -> None:
    conn.execute('CREATE TABLE IF NOT EXISTS main.lab_fiches (key TEXT PRIMARY KEY, answer TEXT)')


def _key(name: str, episode, version: int = DEFAULT) -> str:
    year = datetime.datetime.fromtimestamp(episode.pub_ts, datetime.UTC).year if episode.pub_ts else 'undated'
    return f'{version}|{episode.podcast_id}|{year}|{make_slug(name)}'


def lookup(name: str, episode, version: int = DEFAULT) -> tuple[bool, dict | None]:
    """(decided, the entry or None when none fits), from the cache only."""
    with db.get_db() as conn:
        _table(conn)
        row = conn.execute('SELECT answer FROM main.lab_fiches WHERE key = ?',
                           (_key(name, episode, version),)).fetchone()
    return (False, None) if row is None else (True, json.loads(row['answer']))


def _fiche(result) -> dict | None:
    return result and {'id': result.id, 'name': result.name, 'slug': result.slug,
                       'released': result.data.get('released'), 'coverImageId': result.data.get('coverImageId')}


def _evidence(name: str, episode) -> list[dict]:
    """What the hosts say about the game: its sections in the episode's reading."""
    from judge import same
    from variants import current
    return [{'title': s['title'], 'pros': (s['opinion'] or {}).get('pros', []),
             'cons': (s['opinion'] or {}).get('cons', [])}
            for s in current._reading(episode) or [] if s['game'] and not s['ad'] and same(s['game'], name)]


def decide(name: str, episode, version: int = DEFAULT) -> dict | None:
    """Ask IGDB and the LLM, and cache the answer. A curator's pin stands."""
    prompt, titles_everywhere, evidence = VERSIONS[version]
    game = SimpleNamespace(name=name, name_slug=make_slug(name))
    question = question_for(game, episode)
    if question.kind == 'pin':
        fiche = _fiche(igdb.fetch_by_id(question.pin, canonical=False))
    else:
        podcast = PODCAST_BY_ID[episode.podcast_id]
        context = {'podcast': podcast.name, 'episode_title': episode.title,
                   'show_covers': 'new releases' if podcast.use_date_hint else 'retrospectives of older games',
                   'episode_date': (datetime.datetime.fromtimestamp(episode.pub_ts, datetime.UTC).date().isoformat()
                                    if episode.pub_ts else None)}
        if evidence:
            context['episode_description'] = plain_text(episode.description)[:1500]
            context['what_the_hosts_say'] = _evidence(name, episode)
        # From v4, every show: a name an LLM wrote from a description can be
        # misspelled too (« Donkey Kong Bonanza »).
        if titles_everywhere == 'fallback':
            candidates, _ = resolver.gather_evidence(question, [])
            exact = any(norm_key(c['name']) == norm_key(name) or
                        any(norm_key(o) == norm_key(name) for o in c['otherNames'] or []) for c in candidates.values())
            if not exact:
                more, _ = resolver.gather_evidence(question, llm.suggest_titles(name, context) or [])
                candidates = {**more, **candidates}
        else:
            titles = (llm.suggest_titles(name, context) or []) if titles_everywhere or not podcast.games_by_llm else []
            candidates, _ = resolver.gather_evidence(question, titles)
        ids = sorted(candidates)
        # Cached by prompt, as the app caches by its prompt's version: a version
        # sharing v1's prompt asks nothing v1 asked — the same question asked
        # twice is the LLM's noise, not the version's doing (Fire Emblem 2013,
        # the same evidence: Awakening for v1, the 2003 one when asked again).
        asked_as = min(v for v, (p, *_) in VERSIONS.items() if p is prompt)
        answer = llm.ask('lab_pick', asked_as, prompt,
                         {'name': name, **context, 'candidates': [candidates[i] for i in ids]}) if ids else {'id': None}
        if answer is None:
            raise RuntimeError('LLM unavailable')
        chosen = answer.get('id')
        fiche = _fiche(igdb.fetch_by_id(chosen, canonical=False)) if chosen in candidates else None
    with db.get_db() as conn:
        _table(conn)
        conn.execute('INSERT OR REPLACE INTO main.lab_fiches VALUES (?, ?)',
                     (_key(name, episode, version), json.dumps(fiche, ensure_ascii=False)))
    return fiche
