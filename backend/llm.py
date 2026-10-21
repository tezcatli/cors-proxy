"""An LLM (via OpenRouter) for what a search engine can't judge: which of IGDB's
candidates a podcast's wording means (a French translation, an abbreviation, an
old game named in a 2026 episode), and which games an episode critiques.

Off when `OPENROUTER_API_KEY` is unset, and every caller has a non-LLM fallback,
so an outage never blocks the catalog. Each answer is cached in `llm_cache` by
(task, prompt version, input): one input costs one call, ever. Bump a task's
version when its prompt changes, so the cache stops answering for the old one.

Answers are provisional: they are reviewed in the admin console (in dev), and
what that commits to corrections.json always wins.
"""
import hashlib
import json
import logging

import requests as http

from config import Config
from db import get_db, utcnow

logger = logging.getLogger(__name__)

_URL     = 'https://openrouter.ai/api/v1/chat/completions'
_TIMEOUT = 60


def enabled() -> bool:
    return bool(Config.OPENROUTER_API_KEY)


def ask(task: str, version: int, system: str, payload: dict,
        cached_only: bool = False, any_version: bool = False) -> dict | None:
    """The model's JSON object answer to `payload` under `system`, cached.

    None when the LLM is off or the call fails; a failure isn't cached, so the
    caller's next attempt asks again. `cached_only` never calls the model: it
    answers from the cache or returns None. `any_version` (with `cached_only`)
    falls back to the newest answer an older prompt gave for this input: a
    prompt change must not empty the catalog while the new answers come in.
    """
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    key  = hashlib.sha256(f'{task}\0{version}\0{text}'.encode()).hexdigest()
    with get_db() as conn:
        row = conn.execute('SELECT answer FROM llm_cache WHERE key = ?', (key,)).fetchone()
        if not row and any_version:
            row = conn.execute('SELECT answer FROM llm_cache WHERE task = ? AND input = ? '
                               'ORDER BY version DESC LIMIT 1', (task, text)).fetchone()
    if row:
        return json.loads(row['answer'])
    if cached_only or not enabled():
        return None
    try:
        resp = http.post(_URL, timeout=_TIMEOUT, headers={
            'Authorization': f'Bearer {Config.OPENROUTER_API_KEY}',
        }, json={
            'model': Config.LLM_MODEL,
            'temperature': 0,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': text}],
        })
        resp.raise_for_status()
        answer = json.loads(resp.json()['choices'][0]['message']['content'])
        if not isinstance(answer, dict):
            raise ValueError(f'expected a JSON object, got {type(answer).__name__}')
    except Exception as exc:
        logger.warning('LLM %s failed: %s', task, exc)
        return None
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO llm_cache (key, task, version, input, answer, model, created_at) '
            'VALUES (?,?,?,?,?,?,?)',
            (key, task, version, text, json.dumps(answer, ensure_ascii=False),
             Config.LLM_MODEL, utcnow().isoformat()))
    return answer


# ── Resolving a podcast's game name to an IGDB entry ──────────────────────────
# The LLM reads, IGDB knows: the model never states a fact about a game — the
# games newest to a news show are newer than its training. It suggests titles to
# search for (a reading of the name), and it judges the candidates IGDB returns
# (names, alternative names, release dates) against the name and the episode's
# date: a show reviewing new releases talks about a game out shortly before, and
# IGDB is full of older namesakes.

_TITLES_V = 3
_TITLES = """You help find video games heard on podcasts in the IGDB database.
Given a name as a podcast wrote it and its context (show, episode date), suggest up to
three titles worth searching IGDB for besides the name itself: a French title's
international one ("Le Vaillant Petit Page" -> "The Plucky Squire"), an
abbreviation expanded ("GTA V" -> "Grand Theft Auto V"), a typo fixed. Only
readings of the name: the game may be newer than anything you know, so never
replace it with a game you know. Nothing to suggest is a fine answer.
Answer with JSON only: {"titles": ["..."]}"""


def suggest_titles(name: str, context: dict) -> list[str] | None:
    """Extra titles to search IGDB for ([] = none); None when the LLM is unavailable."""
    answer = ask('titles', _TITLES_V, _TITLES, {'name': name, **context})
    if answer is None:
        return None
    return [t for t in answer.get('titles', []) if isinstance(t, str) and t.strip()][:3]


_PICK_V = 3
_PICK = """You help match video game names heard on podcasts to the IGDB database.
Given a name as a podcast wrote it, its context (show, what it covers, the date
of the episode) and IGDB candidates (id, name, other names, release date), pick
the candidate the podcast is talking about. The game may be newer than anything
you know: judge from the names and the dates, not from memory. A show covering
new releases reviews a game released shortly before the episode — or soon
after, for a preview — so prefer it over an older or later game of the same
name (a 2024 remake over the 1998 original); a retrospective show discusses the
original. Prefer the main game over a DLC, bundle or edition unless the name
says otherwise. If no candidate is the game, answer null.
Answer with JSON only: {"id": <candidate id or null>}"""


def pick_candidate(name: str, context: dict, candidates: list[dict]) -> int | bool | None:
    """The chosen candidate's id; False when the model says none fits; None when
    the LLM is unavailable. An id outside `candidates` counts as unavailable — the
    model is only trusted to choose, never to supply an id."""
    answer = ask('pick', _PICK_V, _PICK, {'name': name, **context, 'candidates': candidates})
    if answer is None:
        return None
    chosen = answer.get('id')
    if chosen is None:
        return False
    if chosen not in {c['id'] for c in candidates}:
        logger.warning('LLM picked %r, not among the candidates for %r', chosen, name)
        return None
    return chosen


# ── Which games an episode critiques ──────────────────────────────────────────
# For shows whose titles don't reliably name the game ("Wolverine Is a Disaster").
# Critiques only, not every game discussed: measured on 200 episodes this halves
# the games (451 → 219) — news, best-of lists, series retrospectives and games
# named for comparison drop out; a grab bag of recent releases keeps each game.

_REVIEWED_V = 2
_REVIEWED = """You index video game podcast episodes so listeners can find CRITIQUES of games.
Given one episode (show, title, date, description), list the games it critiques:
a game the hosts have played and give their verdict on — a review, or one game's
segment in a grab bag of recent releases they have been playing. Nothing else:
- not games brought up for comparison or context, nor a game's predecessors;
- not retrospectives on a series, history or "required playing" episodes;
- not best-of / game-of-the-year lists or rankings;
- not previews, trailers, announcements, news or recommendations ("one more thing");
- nothing that isn't a video game.
Use each game's full official title as IGDB lists it. Most episodes critique one
game or none; a grab bag several. When unsure, leave the game out.
Answer with JSON only: {"reviewed": ["..."]}"""


def reviewed_games(episode: dict, cached_only: bool = False,
                   any_version: bool = False) -> list[str] | None:
    """The games `episode` critiques ([] = none); None when not known (the LLM is
    unavailable, or `cached_only` and it hasn't been asked yet). `any_version`
    accepts an older prompt's answer (see `ask`)."""
    answer = ask('reviewed', _REVIEWED_V, _REVIEWED, episode,
                 cached_only=cached_only, any_version=any_version)
    if answer is None:
        return None
    return [g.strip() for g in answer.get('reviewed', []) if isinstance(g, str) and g.strip()]
