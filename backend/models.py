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


@dataclass
class GameAppearance:
    """Links one PodcastGame to the Episode it appears in, with the game-specific timestamp."""
    episode: Episode        # reference into catalog_state.episodes — not a copy
    mention: GameMention
    podcast_slug: str       # make_slug(name) + '-' + episode.slug (RSS guid); key into catalog_state.resolutions and DB


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
    enriched: bool = True   # False until Metacritic/HLTB have run (see resolver.resolve_one)


@dataclass
class Resolution:
    """Which IGDB game one appearance is, keyed by podcast_slug (make_slug(name) +
    '-' + episode guid). The decision only: the game's data lives in IgdbGame."""
    podcast_slug: str
    igdb_id: Optional[int]  # None = IGDB was asked and had no match (a negative cache)
    is_child: bool          # True when resolved to a parent/version_parent
    resolved_at: str        # ISO-8601 UTC timestamp
    correction_sig: str = ''  # fingerprint of the correction in force when resolved
    method: str | None = None  # 'search' | 'llm' | 'pin'; None = legacy row, accepted as is


@dataclass(frozen=True)
class IgdbEntry:
    """What the readers see of an appearance: its Resolution joined with its
    IgdbGame — `game` is None on a miss, or while a dropped game is re-fetched."""
    resolution: Resolution
    game: Optional[IgdbGame]

    @property
    def podcast_slug(self) -> str:        return self.resolution.podcast_slug
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
