"""What the catalog's tests share: sample feeds, a seeded catalog, its answers."""
from dataclasses import replace
from unittest.mock import MagicMock

import catalog_state as state
import feeds
import games as games_module
from db import utcnow
from utils import make_slug
from contract import CONTRACT
from conftest import cache_entry, set_cache
from rss import parse_feed as _parse_feed, assign_url_slugs as _assign_url_slugs
from podcasts import PODCAST_BY_ID
from questions import question_for


GAMES = CONTRACT['games']


MINIMAL_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <item>
      <title>On a joue a \xc2\xabZelda\xc2\xbb et \xc2\xabMario Kart\xc2\xbb</title>
      <guid isPermaLink="false">ep1guid</guid>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="0" />
      <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
      <description>00:30 Zelda
01:00 Mario Kart
01:30 Outro</description>
    </item>
    <item>
      <title>Quelle est la meilleure plateforme ?</title>
      <guid isPermaLink="false">ep2guid</guid>
      <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="0" />
      <pubDate>Mon, 08 Jan 2024 00:00:00 +0000</pubDate>
      <description>No games here</description>
    </item>
  </channel>
</rss>"""


# Fix the guillemet bytes in the constant (they were escaped above for clarity)
MINIMAL_RSS = MINIMAL_RSS.replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())


def mock_rss_response(content=MINIMAL_RSS, status=200):
    m = MagicMock()
    m.content = content
    m.status_code = status
    m.raise_for_status.return_value = None
    return m


def _ask(name, pub_ts=None, podcast_id='silence-on-joue'):
    """The question `name`, heard in a `podcast_id` episode published at `pub_ts`, asks."""
    from models import Episode, PodcastGame
    from questions import question_for
    episode = Episode(title='t', slug='g', audio_url=None, pub_ts=pub_ts, image_url=None,
                      description=None, chapters=[], games=[], podcast_id=podcast_id)
    return question_for(PodcastGame(make_slug(name), name), episode)


def _igdb_hit(name):
    from igdb import IgdbResult
    return IgdbResult(id=7, name=name, slug=make_slug(name),
                      data={'coverImageId': 'abc'}, is_child=False)


def _seed(rss, cache, podcast_id='silence-on-joue'):
    """Parse an RSS blob into the module's in-memory state with a given IGDB cache."""
    podcast  = PODCAST_BY_ID[podcast_id]
    episodes = _parse_feed(rss, extractor=podcast.extractor, podcast_id=podcast.id)
    _assign_url_slugs(episodes)
    episode_index, game_index = feeds.build_indexes(episodes)
    state.episodes = episodes
    state.episode_index   = episode_index
    state.game_index      = game_index
    set_cache(cache)
    state.data_version   += 1
    games_module._catalog_cache   = None
    return episodes


_NOW = '2999-01-01T00:00:00'


def _entry(podcast_slug, igdb_id, igdb_slug, name, **data):
    return cache_entry(podcast_slug, igdb_id, igdb_slug, name, dict(data), False, _NOW)


_TWO_EPISODES_SAME_NAME = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabSilent Hill 2\xc2\xbb</title>
    <guid>remake</guid><enclosure url="https://example.com/a.mp3" type="audio/mpeg" length="0" />
    <pubDate>Tue, 15 Oct 2024 00:00:00 +0000</pubDate><description>00:30 Silent Hill 2</description></item>
  <item><title>On a joue a \xc2\xabSilent Hill 2\xc2\xbb</title>
    <guid>original</guid><enclosure url="https://example.com/b.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2001 00:00:00 +0000</pubDate><description>00:30 Silent Hill 2</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())


_FDG_RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Episode 166 - Chrono Trigger</title>
    <guid>fdg1</guid><enclosure url="https://example.com/f.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 05 Jun 2026 00:00:00 +0000</pubDate><description>00:30 Chrono Trigger</description></item>
</channel></rss>"""


_SOJ_RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabChrono Trigger\xc2\xbb</title>
    <guid>soj1</guid><enclosure url="https://example.com/s.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 05 Jun 2026 00:00:00 +0000</pubDate><description>00:30 Chrono Trigger</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())


def _single_soj_game():
    """Build a one-game index from an SOJ episode; return (game, appearance)."""
    podcast  = PODCAST_BY_ID['silence-on-joue']
    episodes = _parse_feed(_SOJ_RSS, extractor=podcast.extractor, podcast_id=podcast.id)
    _, game_index = feeds.build_indexes(episodes)
    state.game_index = game_index
    game = next(iter(game_index.values()))
    return game, game.appearances[0]


def _fresh_entry(appearance):
    """A fresh answer for `appearance`'s question, on a fresh game."""
    return cache_entry(appearance.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger',
                       {'metacritic': 90}, False, utcnow().isoformat())


_EXPIRED = '2000-01-01T00:00:00'
