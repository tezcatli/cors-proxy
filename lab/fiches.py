"""A variant of the resolution — which IGDB entry a test is — measured against
the app's. What it changes, from the measured misses:

- the date decides only between namesakes: a show covering new releases talks
  about older games too, and the app's judge rejected the one candidate named
  exactly (CrossCode, 2018, on a 2025 episode → « none fits »);
- the entry is the one named, never redirected to a parent game (« Miles
  Morales » isn't Marvel's Spider-Man, « The Lost and Damned » isn't GTA IV);
- the episode's date is always given, even for a retrospective show: the game
  existed by then.

Its answers are kept in the lab's cache (`lab_fiches`), filled by
`python resolve.py --fiches`; the pages read them, cached only.
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
from utils import make_slug

VERSION = 1
_PICK = """You help match a video game named in a podcast episode to the IGDB database.
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


def _table(conn) -> None:
    conn.execute('CREATE TABLE IF NOT EXISTS main.lab_fiches (key TEXT PRIMARY KEY, answer TEXT)')


def _key(name: str, episode) -> str:
    year = datetime.datetime.fromtimestamp(episode.pub_ts, datetime.UTC).year if episode.pub_ts else 'undated'
    return f'{VERSION}|{episode.podcast_id}|{year}|{make_slug(name)}'


def lookup(name: str, episode) -> tuple[bool, dict | None]:
    """(decided, the entry or None when none fits), from the cache only."""
    with db.get_db() as conn:
        _table(conn)
        row = conn.execute('SELECT answer FROM main.lab_fiches WHERE key = ?', (_key(name, episode),)).fetchone()
    return (False, None) if row is None else (True, json.loads(row['answer']))


def _fiche(result) -> dict | None:
    return result and {'id': result.id, 'name': result.name, 'slug': result.slug,
                       'released': result.data.get('released'), 'coverImageId': result.data.get('coverImageId')}


def decide(name: str, episode) -> dict | None:
    """Ask IGDB and the LLM, and cache the answer. A curator's pin stands."""
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
        titles = [] if podcast.games_by_llm else (llm.suggest_titles(name, context) or [])
        candidates, _ = resolver.gather_evidence(question, titles)
        ids = sorted(candidates)
        answer = llm.ask('lab_pick', VERSION, _PICK,
                         {'name': name, **context, 'candidates': [candidates[i] for i in ids]}) if ids else {'id': None}
        if answer is None:
            raise RuntimeError('LLM unavailable')
        chosen = answer.get('id')
        fiche = _fiche(igdb.fetch_by_id(chosen, canonical=False)) if chosen in candidates else None
    with db.get_db() as conn:
        _table(conn)
        conn.execute('INSERT OR REPLACE INTO main.lab_fiches VALUES (?, ?)',
                     (_key(name, episode), json.dumps(fiche, ensure_ascii=False)))
    return fiche
