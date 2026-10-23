"""Dataclasses shared across the backend — no logic.

`Episode`, `Chapter`, `GameMention` (a game an episode names), `PodcastGame` (one
per name slug) and `GameAppearance` (a name in one episode); the IGDB cache's
`Resolution` (which game a question is answered with) and `IgdbGame` (that
game's data), joined for readers as `IgdbEntry`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Chapter:
    timestamp: str
    timestamp_seconds: int
    title: str
    game_name: Optional[str] = None


@dataclass
class GameMention:
    """One game name extracted from a single episode title, with its matched chapter timestamp."""
    name: str
    timestamp: Optional[str]
    timestamp_seconds: int
    # The hosts' verdict, read from the transcript (`llm.read_transcript`):
    # {verdict, pros, cons, at}. None until the episode is transcribed and read.
    critique: Optional[dict] = None
    # Added from the transcript's reading rather than parsed from the title, so
    # replaced by the next reading (`feeds._apply_readings`).
    read: bool = False


@dataclass
class Episode:
    title: str
    slug: str               # stable RSS guid (fallback: enclosure-URL/title) — episode identity & lookup key
    audio_url: Optional[str]
    pub_ts: Optional[int]
    image_url: Optional[str]
    description: Optional[str]
    chapters: list[Chapter]
    games: list[GameMention]
    url_slug: str = ''      # human-readable make_slug(title), de-duplicated — used only for routing/URLs
    podcast_id: str = ''    # source podcast id (e.g. 'silence-on-joue', 'fin-du-game')
    chapters_read: bool = False  # chapters from the transcript's reading, replaced by the next one
    # The games the title (or the description's reading) proposed, before the
    # transcript's reading confirms them; `games` is what is kept. None until the
    # first rebuild sets it aside (`feeds._apply_readings`).
    proposed: Optional[list[GameMention]] = None
    # The names whose IGDB answers tell its games apart (`critiques.identify`):
    # asked by the catalog like its games' own, so the next build can use them.
    identified: list[str] = field(default_factory=list)


@dataclass
class GameAppearance:
    """Links one PodcastGame to the Episode it appears in, with the game-specific timestamp."""
    episode: Episode        # reference into catalog_state.episodes — not a copy
    mention: GameMention
    podcast_slug: str       # make_slug(name) + '-' + episode.slug (RSS guid); the appearance's identity


@dataclass
class PodcastGame:
    """All appearances of one game name across the entire feed."""
    name_slug: str          # make_slug(name); key in _game_index
    name: str               # raw podcast name as written in the episode title
    appearances: list[GameAppearance] = field(default_factory=list)


@dataclass
class IgdbGame:
    """One IGDB game's data, shared by every appearance resolved to it — so it is
    fetched, scraped and refreshed once per game, not once per episode."""
    igdb_id: int
    igdb_slug: str          # IGDB's own slug, used for URL routing
    name: str               # canonical IGDB name
    data: dict              # normalised IGDB data blob (JSON-serialisable)
    fetched_at: str         # ISO-8601 UTC; the IGDB TTL runs from here
    enriched: bool = True   # False until Metacritic/HLTB have run (see resolver._store_game)


@dataclass
class Resolution:
    """The answer to one question (`questions.Question`), stored under its key:
    which IGDB game the appearances asking it are. The decision only — the game's
    data lives in IgdbGame — with what it was decided on, so the LLM is asked again
    only when that changes."""
    question: str
    igdb_id: Optional[int]  # None = no candidate fits: the question stays open
    is_child: bool          # True when resolved to a parent/version_parent
    decided_at: str         # ISO-8601 UTC timestamp
    method: str | None = None  # 'pin' (a curator) | 'llm' | 'search' (IGDB's ranking,
                               # provisional while the LLM is on); None = legacy row
    # The LLM's reading (titles it suggested searching) and the evidence judged
    # (candidate ids). None = not asked, or a legacy row.
    titles: list[str] | None = None
    candidates: list[int] | None = None
    # Consecutive failures (IGDB error, LLM unavailable) and when to try again: a
    # failing question is retried on a growing delay, not on every sweep.
    attempts: int = 0
    last_error: str | None = None
    retry_at: str | None = None   # ISO-8601 UTC; None = settled


@dataclass(frozen=True)
class IgdbEntry:
    """What the readers see of an appearance: its Resolution joined with its
    IgdbGame — `game` is None on a miss, or while a dropped game is re-fetched."""
    resolution: Resolution
    game: Optional[IgdbGame]

    @property
    def igdb_id(self) -> Optional[int]:   return self.resolution.igdb_id
    @property
    def is_child(self) -> bool:           return self.resolution.is_child
    @property
    def igdb_slug(self) -> Optional[str]: return self.game.igdb_slug if self.game else None
    @property
    def name(self) -> Optional[str]:      return self.game.name if self.game else None
    @property
    def data(self) -> Optional[dict]:     return self.game.data if self.game else None
