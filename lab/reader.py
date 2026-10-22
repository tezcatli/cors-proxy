"""A variant of the reading: the transcript read for its TESTS directly, with
the curator's definition — instead of sections, kinds and rules in code that
only approximate it (a « review » section of two minutes, an aside the reading
calls impressions).

Cached in the lab's `llm_cache` (task `lab_tests`); `python read.py --tests`
reads the reference episodes, the pages read the cache only.
"""
import llm
import transcribe

VERSION = 1
_PROMPT = """You index episodes of video game podcasts from their transcript, to build a base of
game TESTS.
A test is a video game the hosts have played themselves and give their opinion
on, at length: at least five minutes of the episode spent on that game (an ad in
the middle doesn't count against it). A full review, or impressions of a game
they are playing, both are tests; one game is one test.
Not a test:
- a game in the news: an announcement, a trailer, a release date, sales, studio news;
- a demo, trailer or showcase only watched, not played;
- an entry in a best-of, a ranking, an awards ceremony or a year in review;
- a game recommended in passing, or in listener mail;
- a game named for comparison or as an aside;
- a game discussed for less than five minutes;
- anything that isn't a video game (a board game, a film, a series, a book).
The transcript is automatic speech-to-text: names are often misspelled; the
episode's title and description spell them right — use their spelling.
For each test: "game", its exact name; "start_s" and "end_s", where the talk about
it begins and ends (only the second values of the [Xs - Ys] markers); "votes", one
verdict per host who gives one on the game, each just "enthusiastic",
"positive", "mixed" or "negative" ([] when nobody does); "pros" and "cons", at
most 3 short items each.
Answer with JSON only: {"tests": [{"game": "...", "start_s": 0, "end_s": 0,
"votes": [], "pros": [], "cons": []}]} — {"tests": []} when the episode has none."""


def tests(episode, read: bool = False) -> list[dict] | None:
    """[{game, start, end, verdict, pros, cons}] from the cache — or, with
    `read`, from the model (None if it is unavailable or nothing is transcribed)."""
    row = transcribe.rows().get(episode.slug)
    if not (row and row.model):
        return None
    payload = transcribe.reading_input(episode, row.model)
    message = None
    if read:
        segments = transcribe.load(episode.slug).segments
        text = '\n'.join(f'[{s:.0f}s - {e:.0f}s] {t.strip()}' for s, e, t in segments)
        message = (f"Show: {payload['show']}\nTitle: {payload['title']}\n"
                   f"Description (written by the show):\n{payload['description']}\n\n"
                   f"Write every pro and con in {llm._LANGUAGES.get(payload['language'], 'English')}.\n\n"
                   f'<transcript>\n{text}\n</transcript>')
    answer = llm.ask('lab_tests', VERSION, _PROMPT, payload, message=message, timeout=300, cached_only=not read)
    if answer is None:
        return None
    out = []
    for t in answer.get('tests') or []:
        if not (isinstance(t, dict) and isinstance(t.get('game'), str) and t['game'].strip()):
            continue
        start, end = t.get('start_s'), t.get('end_s')
        if not (isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start):
            continue
        listed = lambda k: [x.strip() for x in t.get(k) or [] if isinstance(x, str) and x.strip()][:3]
        out.append({'game': t['game'].strip(), 'start': start, 'end': end,
                    'verdict': llm.verdict([v for v in t.get('votes') or [] if isinstance(v, str)]),
                    'pros': listed('pros'), 'cons': listed('cons')})
    return out
