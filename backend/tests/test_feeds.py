"""Feeds into the catalog (`feeds.py`): appearances, several podcasts, a feed unchanged."""
from dataclasses import replace
from unittest.mock import patch

import catalog_state as state
import feeds
from utils import make_slug
from rss import parse_feed as _parse_feed, assign_url_slugs as _assign_url_slugs
from podcasts import PODCAST_BY_ID
from catalog_fixtures import mock_rss_response


def test_same_day_episodes_both_kept():
    # Two DISTINCT episodes, same calendar day, both mention «Zelda», different guids.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Matin on a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>day-a</guid><enclosure url="https://example.com/a.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
  <item><title>Soir on rejoue a \xc2\xabZelda\xc2\xbb</title>
    <guid>day-b</guid><enclosure url="https://example.com/b.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 20:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    _, game_index = feeds.build_indexes(_parse_feed(rss))
    zelda = game_index[make_slug('Zelda')]
    assert {a.episode.slug for a in zelda.appearances} == {'day-a', 'day-b'}


def test_multi_feed_merges_same_game_across_podcasts():
    # A game covered by BOTH podcasts merges into one PodcastGame with two
    # appearances tagged with their distinct podcast_ids; url_slugs stay unique.
    soj_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>soj-zelda</guid><enclosure url="https://example.com/soj.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    fdg_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Episode 50 - Zelda</title>
    <guid>fdg-zelda</guid><enclosure url="https://example.com/fdg.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 10 Jan 2025 09:00:00 +0000</pubDate><description>Analyse complete</description></item>
</channel></rss>"""
    soj = PODCAST_BY_ID['silence-on-joue']
    fdg = PODCAST_BY_ID['fin-du-game']
    episodes = (
        _parse_feed(soj_rss, extractor=soj.extractor, podcast_id=soj.id)
        + _parse_feed(fdg_rss, extractor=fdg.extractor, podcast_id=fdg.id)
    )
    _assign_url_slugs(episodes)
    assert len({ep.url_slug for ep in episodes}) == len(episodes)  # globally unique

    _, game_index = feeds.build_indexes(episodes)
    zelda = game_index[make_slug('Zelda')]
    assert len(zelda.appearances) == 2
    assert {a.episode.podcast_id for a in zelda.appearances} == {'silence-on-joue', 'fin-du-game'}


def test_multi_feed_episodes_interleave_by_date():
    # The combined feed must be newest-first across BOTH podcasts, so a recent FDG
    # episode sorts above older SOJ episodes instead of all SOJ coming first.
    soj_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Vieux \xc2\xabZelda\xc2\xbb</title>
    <guid>soj-old</guid><enclosure url="https://example.com/o.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>x</description></item>
  <item><title>Recent \xc2\xabMario\xc2\xbb</title>
    <guid>soj-new</guid><enclosure url="https://example.com/n.mp3" type="audio/mpeg" length="0" />
    <pubDate>Wed, 01 Jan 2025 09:00:00 +0000</pubDate><description>x</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    fdg_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Episode 50 - Balatro</title>
    <guid>fdg-mid</guid><enclosure url="https://example.com/m.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 10 May 2024 09:00:00 +0000</pubDate><description>x</description></item>
</channel></rss>"""
    soj, fdg = PODCAST_BY_ID['silence-on-joue'], PODCAST_BY_ID['fin-du-game']
    feeds_by_url = {soj.feed_url: soj_rss, fdg.feed_url: fdg_rss}
    with patch.object(feeds, 'PODCASTS', [soj, fdg]), \
         patch('feeds.http.get', side_effect=lambda url, **_: mock_rss_response(feeds_by_url[url])):
        feeds.refresh_feed()
    assert [e.slug for e in state.episodes] == ['soj-new', 'fdg-mid', 'soj-old']


def test_intra_episode_duplicate_deduped():
    # Same game mentioned twice in ONE episode → a single appearance.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Special \xc2\xabZelda\xc2\xbb et encore \xc2\xabZelda\xc2\xbb</title>
    <guid>solo</guid><enclosure url="https://example.com/s.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    _, game_index = feeds.build_indexes(_parse_feed(rss))
    zelda = game_index[make_slug('Zelda')]
    assert len(zelda.appearances) == 1


def test_unchanged_feed_keeps_the_data_version(client):
    # Polled every tick and nearly always 304: rebuilding would bump the version
    # and invalidate every client's catalog ETag for nothing.
    with patch('feeds.http.get', return_value=mock_rss_response()):
        feeds.refresh_feed()
    version = state.data_version
    with patch('feeds.http.get', return_value=mock_rss_response(status=304)):
        feeds.refresh_feed()
    assert state.data_version == version
