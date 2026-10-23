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
        cached_only: bool = False, any_version: bool = False,
        message: str | None = None, timeout: int = _TIMEOUT) -> dict | None:
    """The model's JSON object answer to `payload` under `system`, cached.

    None when the LLM is off or the call fails; a failure isn't cached, so the
    caller's next attempt asks again. `cached_only` never calls the model: it
    answers from the cache or returns None. `any_version` (with `cached_only`)
    falls back to the newest answer an older prompt gave for this input: a
    prompt change must not empty the catalog while the new answers come in.
    `message` is what the model is sent when `payload` only identifies the input
    — a transcript is too big to keep a second copy of in the cache.
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
        resp = http.post(_URL, timeout=timeout, headers={
            'Authorization': f'Bearer {Config.OPENROUTER_API_KEY}',
        }, json={
            'model': Config.LLM_MODEL,
            'temperature': 0,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': message or text}],
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


# Chosen in the lab (`lab/fiches.py`, v1) on every judged test: the previous
# prompt rejected the one candidate named exactly when it was older than a news
# show's episode (CrossCode, 2018, on a 2025 episode → « none fits »).
_PICK_V = 4
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


# ── Reading an episode's transcript ───────────────────────────────────────────
# One reading gives the episode's chapters, the game each section is about, what
# kind of section it is and what the hosts think of it — a description: what the
# catalog makes of it is decided in feeds.py. The transcript is speech-to-text, so names come out
# phonetic («GICNEP» for Jiknep): the episode's own title and description are
# given as context and their spelling wins — no hand-kept lexicon. The language
# is named outright: told only "the episode's language", the model answered in
# Spanish two times out of three on an English show.

_TRANSCRIPT_V = 1
_TRANSCRIPT = """You index episodes of video game podcasts from their transcript.
Split the episode into its main sections and give each a short title.
- A section in which the hosts discuss one video game at length (they played it,
  give impressions or a verdict) is about that game: game = its exact name. This
  holds when the game comes up in the news, too.
- Any other section (intro, news round-up, listener mail, outro, a board game,
  anything that isn't a video game) has game = null.
- An ad or sponsor read is a section of its own with "ad": true (false for every
  other section).
- Two consecutive sections about the same thing are one section.
The transcript is automatic speech-to-text: names of games, people and running
jokes are often misspelled phonetically. When a name in the episode's title or
description is what was said, use their spelling; otherwise clean up the name
as transcribed.
Timestamps: use only the second values of the [Xs - Ys] markers; sections follow
one another with no gap or overlap, from the first marker to the last.
For each video-game section, describe it — what happens, not whether it
matters: "kind" is
- "review": the hosts have played the game and judge it;
- "impressions": they are playing it and say how it's going, without concluding;
- "news": the game is in the news — an announcement, a trailer, a release, sales;
- "ranking": its entry in a best-of, a ranking or a year in review — even when
  the hosts played it and judge it there, this is the kind;
- "recommendation": a host recommends it in passing (listener mail, a tip);
- "mention": it is named in passing or for comparison.
And whatever the kind, from what the hosts actually say: "votes", one verdict
per host who gives one on the game itself, each just the word "enthusiastic",
"positive", "mixed" or "negative", no name (["positive", "mixed"]; [] when
nobody does); "pros" and "cons", at most 3 short items each; "verdict_s", the
second where their opinion is stated most clearly.
Answer with JSON only: {"sections": [{"title": "...", "game": "..." or null,
"kind": null, "ad": false, "start_s": 0, "end_s": 95, "votes": [], "pros": [],
"cons": [], "verdict_s": 0}]}"""

_LANGUAGES = {'fr': 'French', 'en': 'English'}
VERDICTS = ('negative', 'mixed', 'positive')
# The reader's words, on the scale shown. It is asked for four, but tells
# «enthusiastic» from «positive» apart no better than chance — measured: two
# readings of 20 episodes disagreed on 11 of 58 verdicts there, against 7 on
# every other boundary together.
_SCORES = {'negative': 0, 'mixed': 1, 'positive': 2, 'enthusiastic': 2}
# What a game section is. The reader describes; what the catalog keeps is
# decided in code (`feeds.CRITIQUE_KINDS`), so a change of policy re-reads nothing.
KINDS = ('review', 'impressions', 'ranking', 'news', 'recommendation', 'mention')


def verdict(votes: list[str]) -> str | None:
    """The hosts' verdicts averaged on the scale `VERDICTS`; a tie between two
    steps goes to «mixed» — hosts split down the middle are mixed. None when
    nobody gave one."""
    # «Patrick Hellio: mixed» counts as «mixed»: whose vote it is can't be told
    # from a transcript, only that it was cast.
    words  = [v.rsplit(':', 1)[-1].strip().lower() for v in votes]
    scores = [_SCORES[w] for w in words if w in _SCORES]
    if not scores:
        return None
    mean = sum(scores) / len(scores)
    lo = int(mean)
    nearest = sorted((lo, min(lo + 1, len(VERDICTS) - 1)),
                     key=lambda s: (abs(s - mean), abs(s - 1)))[0]
    return VERDICTS[nearest]


def _sections(answer: dict) -> list[dict]:
    sections = []
    for raw in answer.get('sections') or []:
        if not isinstance(raw, dict) or not isinstance(raw.get('title'), str):
            continue
        try:
            start, end = int(raw['start_s']), int(raw['end_s'])
        except (KeyError, TypeError, ValueError):
            continue
        game = raw.get('game') if isinstance(raw.get('game'), str) and raw['game'].strip() else None
        kind = opinion = None
        if game:
            kind = raw.get('kind') if raw.get('kind') in KINDS else 'mention'
            listed = lambda k: [x.strip() for x in raw.get(k) or [] if isinstance(x, str) and x.strip()][:3]
            at = raw.get('verdict_s')
            opinion = {'verdict': verdict([v for v in raw.get('votes') or [] if isinstance(v, str)]),
                       'pros': listed('pros'), 'cons': listed('cons'),
                       'at': int(at) if isinstance(at, (int, float)) else start}
        sections.append({'title': raw['title'].strip(), 'game': game and game.strip(),
                         'kind': kind, 'start': start, 'end': end, 'opinion': opinion,
                         'ad': raw.get('ad') is True})
    return sorted(sections, key=lambda s: s['start'])


def read_transcript(episode: dict, segments: list | None = None) -> list[dict] | None:
    """The sections of a transcribed episode: [{title, game, kind, start, end,
    opinion, ad}]. A game section has a `kind` (`KINDS`) and the hosts' `opinion`
    = {verdict, pros, cons, at}, `verdict` None when nobody gives one; any other
    section has neither.

    `episode` identifies the reading (show, language, guid, transcript model,
    title, description); the transcript itself, `segments` ([[start, end, text]]),
    is only sent. With segments the model reads the episode (None if it is
    unavailable); without, the cache answers — an older prompt's reading standing
    in while the current one comes (`any_version`) — or None if it hasn't read it."""
    message = None
    if segments is not None:
        transcript = '\n'.join(f'[{s:.0f}s - {e:.0f}s] {t.strip()}' for s, e, t in segments)
        message = (f"Show: {episode['show']}\nTitle: {episode['title']}\n"
                   f"Description (written by the show):\n{episode['description']}\n\n"
                   f"Write every title, pro and con in {_LANGUAGES.get(episode['language'], 'English')}.\n\n"
                   f'<transcript>\n{transcript}\n</transcript>')
    lookup = segments is None
    answer = ask('transcript', _TRANSCRIPT_V, _TRANSCRIPT, episode, message=message,
                 timeout=300, cached_only=lookup, any_version=lookup)
    return None if answer is None else _sections(answer)


def has_current_reading(episode: dict) -> bool:
    """Whether the current prompt has read this episode (not just an older one)."""
    return ask('transcript', _TRANSCRIPT_V, _TRANSCRIPT, episode, cached_only=True) is not None
