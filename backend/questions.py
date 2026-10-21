"""What resolving a game mention asks.

An appearance (a game name heard in one episode) doesn't need its own answer: a
show doesn't review two different games under one name within a year, so every
appearance of a name in a show's year asks the same question, answered once
(`resolver.resolve`) and stored under its key (`catalog_state.resolutions`). The
key is a pure value of the appearance and corrections.json — which is why a
changed correction needs no bookkeeping: it changes the question, the new one is
unanswered, and the old one, asked by no appearance any more, is pruned.

The evidence, though, is anchored on a date: shows covering new releases review
games out shortly before the episode, and IGDB is full of older namesakes. A
question is judged as of its first airing — the earliest episode asking it, the
nearest to the game's release (`catalog_state.asked` keeps that one).

Three kinds, by who answers:
  pin     a curator's `igdb_id`: the answer itself
  search  a curator's `search_name` / `hint_date`: the query, answered by IGDB's
          ranking — the curator chose the search, so the LLM stays out of it
  name    no correction: the LLM judges IGDB's candidates (the ranking stands in,
          provisionally, while it is unavailable)
"""
import datetime
from dataclasses import dataclass

from corrections import find_by_podcast
from igdb import Window, window_around
from models import Episode, PodcastGame
from podcasts import PODCAST_BY_ID
from utils import make_slug


@dataclass(frozen=True)
class Question:
    key:        str              # identity: where its answer is stored
    kind:       str              # 'pin' | 'search' | 'name'
    name:       str              # as the podcast wrote it — what the LLM reads
    podcast_id: str
    aired:      int | None       # the episode's date, when it bounds the game's release
    query:      str              # what IGDB is searched for
    window:     Window | None    # release dates the search prefers, around `aired`
    pin:        int | None = None


def _year(ts: int | None) -> int | None:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).year if ts else None


def question_for(game: PodcastGame, episode: Episode) -> Question:
    """The question `game`'s mention in `episode` asks."""
    aired      = episode.pub_ts
    correction = find_by_podcast(game.name, episode.pub_ts, episode.podcast_id) or {}

    if correction.get('igdb_id'):
        igdb_id = correction['igdb_id']
        return Question(key=f'pin|{igdb_id}', kind='pin', name=game.name,
                        podcast_id=episode.podcast_id, aired=aired, query=game.name,
                        window=None, pin=igdb_id)

    # What the episode's date says of the game's. A curated day is the most precise;
    # a show covering new games was talking about a recent one — one question per
    # name and year; a retrospective show's date says nothing.
    podcast = PODCAST_BY_ID.get(episode.podcast_id)
    if correction.get('hint_date'):
        day   = datetime.datetime.fromisoformat(correction['hint_date']).replace(
                    tzinfo=datetime.timezone.utc)
        aired, scope = int(day.timestamp()), correction['hint_date']
    elif (podcast and not podcast.use_date_hint) or aired is None:
        aired, scope = None, 'undated'
    else:
        scope = str(_year(aired))
    window = window_around(aired) if aired else None

    if correction.get('search_name') or correction.get('hint_date'):
        query = correction.get('search_name') or game.name
        return Question(key=f'search|{make_slug(query)}|{scope}', kind='search',
                        name=game.name, podcast_id=episode.podcast_id, aired=aired,
                        query=query, window=window)
    return Question(key=f'name|{episode.podcast_id}|{scope}|{game.name_slug}', kind='name',
                    name=game.name, podcast_id=episode.podcast_id, aired=aired,
                    query=game.name, window=window)
