"""
Podcast registry: the source-of-truth list of feeds the catalog is built from.

Each podcast carries its feed URL and the title→game-name extractor appropriate
for that show's title convention. The rest of the pipeline (parsing, indexing,
IGDB resolution, serialisation) is podcast-agnostic — it just loops over this
list and stamps each Episode with the owning podcast's `id`.

Feed URLs are overridable via env (`<ID>_FEED_URL`, dashes → underscores,
uppercased) so a deployment can repoint a feed without a code change.
"""

import os
from dataclasses import dataclass
from typing import Callable

import rss


@dataclass(frozen=True)
class Podcast:
    id:    str                       # stable slug, also exposed to the frontend
    label: str                       # short badge text (e.g. 'SoJ', 'FDG')
    name:  str                       # human-readable display name
    feed_url: str
    extractor: Callable[[str], list[str]]   # title -> list of raw game names
    language: str                    # what the hosts speak: 'fr' | 'en' (transcription)
    # Whether the episode's publication date is a useful hint for *when the game
    # came out*. True for a news show covering new releases; False for a
    # retrospective show, where the episode date says nothing about the game's
    # release year and the date window would actively mis-resolve it.
    use_date_hint: bool = True
    # For a show whose titles don't reliably name the game: an LLM reads each
    # episode's title and description and says which games it reviews
    # (`resolver.schedule_llm_reads`). Without the LLM such a show contributes
    # no episodes. `skip_title` drops items that aren't the show (another
    # podcast's teaser) before anything is asked.
    games_by_llm: bool = False
    skip_title: str | None = None


def _feed_url(podcast_id: str, default: str) -> str:
    return os.getenv(f'{podcast_id.replace("-", "_").upper()}_FEED_URL', default)


PODCASTS: list[Podcast] = [
    Podcast(
        id='silence-on-joue',
        label='SoJ',
        name='Silence on Joue',
        feed_url=_feed_url('silence-on-joue',
                           'https://feeds.acast.com/public/shows/silence-on-joue'),
        extractor=rss.extract_game_names,
        language='fr',
    ),
    Podcast(
        id='fin-du-game',
        label='FDG',
        name='Fin du Game',
        feed_url=_feed_url('fin-du-game',
                           'https://feeds.acast.com/public/shows/fin-du-game'),
        extractor=rss.extract_fdg_names,
        language='fr',
        # Retrospective show: a 2026 episode on Symphony of the Night (1997) must
        # not search IGDB around 2026, or it lands on an unrelated recent game.
        use_date_hint=False,
    ),
    Podcast(
        id='triple-click',
        label='TC',
        name='Triple Click',
        feed_url=_feed_url('triple-click', 'https://feeds.simplecast.com/6WD3bDj7'),
        extractor=lambda _title: [],
        language='en',
        games_by_llm=True,
        # Maximum Fun cross-promotes its other shows in this feed.
        skip_title=r'^Beanscast\b|\[TEASER\]',
    ),
    Podcast(
        id='the-besties',
        label='BES',
        name='The Besties',
        feed_url=_feed_url('the-besties', 'https://feeds.simplecast.com/Urk3897_'),
        extractor=lambda _title: [],
        language='en',
        games_by_llm=True,
    ),
]

# Quick lookups by id.
PODCAST_BY_ID: dict[str, Podcast] = {p.id: p for p in PODCASTS}


def podcast_meta(podcast_id: str) -> dict | None:
    """Slim `{id, label, name}` for serialisation, or None for an unknown id."""
    p = PODCAST_BY_ID.get(podcast_id)
    return {'id': p.id, 'label': p.label, 'name': p.name} if p else None
