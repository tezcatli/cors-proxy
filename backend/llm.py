"""An LLM (via OpenRouter) for what a search engine can't judge: which IGDB entry a
podcast's wording means (a French translation, an abbreviation, an old game
named in a 2026 episode), and which games an episode reviews.

Off when `OPENROUTER_API_KEY` is unset, and every caller has a non-LLM fallback,
so an outage never blocks the catalog. Each answer is cached in `llm_cache` by
(task, prompt version, input): one input costs one call, ever. Bump a task's
version when its prompt changes, so the cache stops answering for the old one.

Answers are provisional: the dev audit (tools/llm_audit.py) reviews them, and
what it commits to corrections.json always wins.
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
        cached_only: bool = False) -> dict | None:
    """The model's JSON object answer to `payload` under `system`, cached.

    None when the LLM is off or the call fails; a failure isn't cached, so the
    caller's next attempt asks again. `cached_only` never calls the model: it
    answers from the cache or returns None.
    """
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    key  = hashlib.sha256(f'{task}\0{version}\0{text}'.encode()).hexdigest()
    with get_db() as conn:
        row = conn.execute('SELECT answer FROM llm_cache WHERE key = ?', (key,)).fetchone()
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
# Two calls, so the model never makes up an id: it first says which game the
# name means, we fetch IGDB's candidates for that, then it picks one of them.

_TITLES_V = 1
_TITLES = """You help match video game names heard on podcasts to the IGDB database.
Given a name as a podcast wrote it and the episode's context, give the official
title(s) IGDB most likely lists the game under: translate a French title to its
international one ("Le Vaillant Petit Page" -> "The Plucky Squire"), expand an
abbreviation ("GTA V" -> "Grand Theft Auto V"), fix a typo. Most likely first,
at most three. If the name is clearly not a video game, return an empty list.
Answer with JSON only: {"titles": ["..."]}"""


def official_titles(name: str, context: dict) -> list[str] | None:
    """Titles to search IGDB for; None when the LLM is unavailable."""
    answer = ask('titles', _TITLES_V, _TITLES, {'name': name, **context})
    if answer is None:
        return None
    return [t for t in answer.get('titles', []) if isinstance(t, str) and t.strip()][:3]


_PICK_V = 1
_PICK = """You help match video game names heard on podcasts to the IGDB database.
Given a name as a podcast wrote it, the episode's context and IGDB candidates
(id, name, release year), pick the candidate the podcast is talking about. Use
the context: a show covering new releases discusses the version current at the
episode's date (a 2024 remake over the 1998 original); a retrospective show
discusses the original. Prefer the main game over a DLC, bundle or edition
unless the name says otherwise. If no candidate is the game, answer null.
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


# ── Which games an episode reviews ────────────────────────────────────────────
# For shows whose titles don't reliably name the game ("Wolverine Is a Disaster").
# Measured on 254 episodes of The Besties and Triple Click: the main game is found
# even when the show's own list omits it, and names come out official.

_REVIEWED_V = 1
_REVIEWED = """You index video game podcast episodes so listeners can find reviews.
Given one episode (show, title, date, description), list the video games it
REVIEWS: games the hosts actually discuss at some length — a full review,
impressions, or a segment of a round-up episode. Leave out games only mentioned
in passing (comparisons, references, a quick aside), and anything that isn't a
video game (films, TV, books, hardware, companies). Use each game's full
official title as IGDB lists it. An episode about news, a general topic or
listener mail usually reviews none: return an empty list.
Answer with JSON only: {"reviewed": ["..."]}"""


def reviewed_games(episode: dict, cached_only: bool = False) -> list[str] | None:
    """The games `episode` reviews ([] = none); None when not known (the LLM is
    unavailable, or `cached_only` and it hasn't been asked yet)."""
    answer = ask('reviewed', _REVIEWED_V, _REVIEWED, episode, cached_only=cached_only)
    if answer is None:
        return None
    return [g.strip() for g in answer.get('reviewed', []) if isinstance(g, str) and g.strip()]
