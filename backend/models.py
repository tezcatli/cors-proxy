from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Chapter:
    timestamp: str
    timestamp_seconds: int
    title: str


@dataclass
class GameMention:
    """One game name extracted from a single episode title, with its matched chapter timestamp."""
    name: str
    timestamp: Optional[str]
    timestamp_seconds: int


@dataclass
class Episode:
    title: str
    slug: str               # make_slug(title) — stable lookup key
    audio_url: Optional[str]
    pub_ts: Optional[int]
    image_url: Optional[str]
    description: Optional[str]
    chapters: list[Chapter]
    games: list[GameMention]


@dataclass
class GameAppearance:
    """Links one PodcastGame to the Episode it appears in, with the game-specific timestamp."""
    episode: Episode        # reference into _cached_episodes — not a copy
    mention: GameMention
    podcast_slug: str       # make_slug(name) + '-' + YYYYMMDD; key into _igdb_cache and DB


@dataclass
class PodcastGame:
    """All appearances of one game name across the entire feed."""
    name_slug: str          # make_slug(name); key in _game_index
    name: str               # raw podcast name as written in the episode title
    appearances: list[GameAppearance] = field(default_factory=list)
    latest_pub_ts: int = 0
    episode_count: int = 0


@dataclass
class IgdbEntry:
    """One resolved IGDB row, keyed by date-qualified podcast_slug."""
    podcast_slug: str
    igdb_id: Optional[int]
    igdb_slug: Optional[str]
    name: Optional[str]     # canonical IGDB name
    data: Optional[dict]    # normalised IGDB data blob (JSON-serialisable)
    is_child: bool          # True when resolved to a parent/version_parent
    cached_at: str          # ISO-8601 UTC timestamp
