import datetime
from dataclasses import replace
from unittest.mock import patch, MagicMock

import pytest

import catalog_state as state
import feeds
import games as games_module
import resolver
import review
import serializers
from db import get_db, utcnow
from utils import make_slug
from contract import assert_contract, CONTRACT
from conftest import auth_header, cache_entry, set_cache
import db as _db
from rss import extract_game_names as _extract_game_names, extract_legacy_names as _extract_legacy_names, extract_fdg_names as _extract_fdg_names, parse_feed as _parse_feed, assign_url_slugs as _assign_url_slugs, sanitize_html as _sanitize_html
from podcasts import PODCAST_BY_ID

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


# ── _extract_game_names ───────────────────────────────────────────────────────

def test_extract_game_names_guillemets():
    names = _extract_game_names('On a joué à «Zelda» et «Mario»')
    assert names == ['Zelda', 'Mario']


# ── _extract_legacy_names ─────────────────────────────────────────────────────

@pytest.mark.parametrize('title,expected', [
    ('Silence, on joue ! Gears of War 3, Resistance 3',
     ['Gears of War 3', 'Resistance 3']),
    ('Silence, on joue ! Battlefield 3, Uncharted 3, Dark Souls',
     ['Battlefield 3', 'Uncharted 3', 'Dark Souls']),
    ('Silence on joue ! World of Warcraft, Donkey Kong Country et Splatterhouse',
     ['World of Warcraft', 'Donkey Kong Country', 'Splatterhouse']),
    ('Silence on joue! Kinect, Fable III et James Bond',
     ['Kinect', 'Fable III', 'James Bond']),
    ('Silence on joue ! Skyrim, Shinobi',
     ['Skyrim', 'Shinobi']),
    ('Silence on joue! Batman Arkham City',
     ['Batman Arkham City']),
    ('Silence, on joue: Dreamcast, Gears of War 2...',
     ['Dreamcast', 'Gears of War 2']),
    ('La semaine des jeux vidéo ! The Legend of Zelda : Phantom Hourglass, PES 2008',
     ['The Legend of Zelda : Phantom Hourglass', 'PES 2008']),
])
def test_extract_legacy_names(title, expected):
    assert _extract_legacy_names(title) == expected

@pytest.mark.parametrize('title', [
    'Silence on joue! Spécial E3 2011',
    'Silence on joue ! Grand entretien avec Juliette',
    'Silence on joue ! Le bilan 2021',
    'Silence on joue ! En public à Muséogames',
    'Not a SOJ title at all',
])
def test_extract_legacy_names_skipped(title):
    assert _extract_legacy_names(title) == []

# ── _extract_fdg_names (Fin du Game title format) ─────────────────────────────

@pytest.mark.parametrize('title,expected', [
    ('Episode 167 - Ghost of Tsushima (feat. Julie le Baron)', ['Ghost of Tsushima']),
    ('Episode 163 - Tony Hawk\'s Underground 2',                ['Tony Hawk\'s Underground 2']),
    ('Episode 166 - Castlevania: Symphony of the Night (feat. Théo Arbogast)',
     ['Castlevania: Symphony of the Night']),                       # colon inside name kept
    ('Episode 89 : StarCraft II',                              ['StarCraft II']),  # colon separator
    ('Episode 22 - Resident Evil 2 (Remake)',                 ['Resident Evil 2 (Remake)']),  # non-feat paren kept
    ('Episode 142 - Les Sims (Feat. Héloïse Linossier & Margorito)', ['Les Sims']),  # capital Feat + &
    ('Episode 01 - Celeste',                                  ['Celeste']),  # zero-padded number
])
def test_extract_fdg_names(title, expected):
    assert _extract_fdg_names(title) == expected


@pytest.mark.parametrize('title', [
    'L\'avenir de Fin du Game',
    'Annonce Saison Six de Fin du Game',
    'Episode Bonus - Lancement du Patreon',   # non-numbered bonus → excluded
    '',
])
def test_extract_fdg_names_non_game(title):
    assert _extract_fdg_names(title) == []


def test_extract_game_names_falls_back_to_legacy():
    names = _extract_game_names('Silence, on joue ! Gears of War 3, Resistance 3')
    assert names == ['Gears of War 3', 'Resistance 3']

def test_extract_game_names_guillemets_take_priority():
    names = _extract_game_names('Silence on joue ! «Skyrim», «Doom» et «L.A. Noire» débarquent sur la Switch')
    assert names == ['Skyrim', 'Doom', 'L.A. Noire']


# ── _parse_feed ───────────────────────────────────────────────────────────────

def test_parse_feed_returns_game_list():
    episodes = _parse_feed(MINIMAL_RSS)
    names = {g.name for ep in episodes for g in ep.games}
    assert 'Zelda' in names
    assert 'Mario Kart' in names

def test_parse_feed_includes_non_game_episodes():
    episodes = _parse_feed(MINIMAL_RSS)
    assert len(episodes) == 2
    game_ep = next(ep for ep in episodes if ep.games)
    assert len(game_ep.games) == 2
    no_game_ep = next(ep for ep in episodes if not ep.games)
    assert no_game_ep.title == 'Quelle est la meilleure plateforme ?'

def test_parse_feed_uses_raw_podcast_name():
    # parse_feed no longer applies corrections — canonical name comes from IGDB
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
      <item>
        <title>On a joue \xc2\xab artic eggs \xc2\xbb</title>
        <enclosure url="https://example.com/ep3.mp3" type="audio/mpeg" length="0" />
        <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate><description></description>
      </item></channel></rss>"""
    rss = rss.replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    episodes = _parse_feed(rss)
    assert episodes[0].games[0].name.strip() == 'artic eggs'

def test_parse_feed_sets_audio_url():
    episodes = _parse_feed(MINIMAL_RSS)
    assert episodes[0].audio_url == 'https://example.com/ep1.mp3'

def test_parse_feed_parses_pub_ts():
    episodes = _parse_feed(MINIMAL_RSS)
    assert isinstance(episodes[0].pub_ts, int)
    assert episodes[0].pub_ts > 0

def test_parse_feed_resolves_timestamps():
    episodes = _parse_feed(MINIMAL_RSS)
    zelda = next(g for g in episodes[0].games if g.name == 'Zelda')
    assert zelda.timestamp == '00:30'
    assert zelda.timestamp_seconds == 30


# ── HTML sanitisation ──────────────────────────────────────────────────────────

def test_sanitize_html_drops_script_and_event_handlers():
    dirty = '<p>Hi</p><script>alert(1)</script><img src=x onerror="alert(2)">'
    clean = _sanitize_html(dirty)
    assert '<script' not in clean
    assert 'onerror' not in clean
    assert 'alert' not in clean          # script body dropped entirely
    assert '<p>Hi</p>' in clean

def test_sanitize_html_keeps_whitelisted_formatting():
    clean = _sanitize_html('<p>a <strong>b</strong> <em>c</em></p><ul><li>x</li></ul>')
    assert clean == '<p>a <strong>b</strong> <em>c</em></p><ul><li>x</li></ul>'

def test_sanitize_html_neutralises_javascript_urls():
    clean = _sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert 'javascript:' not in clean
    assert '>x</a>' in clean

def test_sanitize_html_keeps_safe_links():
    clean = _sanitize_html('<a href="https://example.com">link</a>')
    assert 'href="https://example.com"' in clean

def test_parse_feed_sanitizes_description():
    rss = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
  <item>
    <title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <enclosure url="https://example.com/ep.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
    <content:encoded><![CDATA[<p>Bonjour</p><script>alert(1)</script>]]></content:encoded>
  </item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    episodes = _parse_feed(rss)
    assert '<script' not in (episodes[0].description or '')
    assert '<p>Bonjour</p>' in episodes[0].description


# ── Episode identity (guid) + L2 collision ──────────────────────────────────────

def test_parse_feed_uses_guid_as_slug():
    episodes = _parse_feed(MINIMAL_RSS)
    assert episodes[0].slug == 'ep1guid'
    assert episodes[1].slug == 'ep2guid'

def test_parse_feed_guid_fallback_to_enclosure():
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>No Guid Here</title>
    <enclosure url="https://example.com/x.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description></description></item>
</channel></rss>"""
    ep = _parse_feed(rss)[0]
    assert ep.slug == make_slug('https://example.com/x.mp3')

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
</channel></rss>"""
    fdg_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Episode 50 - Balatro</title>
    <guid>fdg-mid</guid><enclosure url="https://example.com/m.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 10 May 2024 09:00:00 +0000</pubDate><description>x</description></item>
</channel></rss>"""
    soj = PODCAST_BY_ID['silence-on-joue']
    fdg = PODCAST_BY_ID['fin-du-game']
    episodes = (
        _parse_feed(soj_rss, extractor=soj.extractor, podcast_id=soj.id)
        + _parse_feed(fdg_rss, extractor=fdg.extractor, podcast_id=fdg.id)
    )
    episodes.sort(key=lambda e: e.pub_ts or 0, reverse=True)
    order = [e.slug for e in episodes]
    assert order == ['soj-new', 'fdg-mid', 'soj-old']     # interleaved, newest-first
    pts = [e.pub_ts or 0 for e in episodes]
    assert pts == sorted(pts, reverse=True)


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


# ── AI chapter injection (L2 gotcha + L5 guard) ────────────────────────────────

def _blank_episode(title, slug):
    from models import Episode
    return Episode(title=title, slug=slug, audio_url=None, pub_ts=None,
                   image_url=None, description=None, chapters=[], games=[])

def test_inject_ai_chapters_matches_on_title_slug():
    # episode.slug is now a guid; injection must still match on make_slug(title).
    ep = _blank_episode('My Episode', 'guid-xyz')
    ai_index = {make_slug('My Episode'): [
        {'start_s': 30, 'title': 'Intro'}, {'start_s': 90, 'title': 'Zelda'},
    ]}
    feeds.inject_ai_chapters([ep], ai_index)
    assert [c.title for c in ep.chapters] == ['Intro', 'Zelda']

def test_inject_ai_chapters_skips_malformed_entries():
    ep = _blank_episode('Bad Ep', 'g')
    ai_index = {make_slug('Bad Ep'): [
        {'title': 'no start'},                # missing start_s → skipped
        {'start_s': 10},                       # missing title  → skipped
        {'start_s': 20, 'title': 'Good'},      # kept
    ]}
    feeds.inject_ai_chapters([ep], ai_index)
    assert [c.title for c in ep.chapters] == ['Good']


# ── Catalog episodeCount (L4) ───────────────────────────────────────────────────

def test_catalog_counts_distinct_episodes():
    # Two name variants resolving to ONE igdb_slug, co-occurring in ONE episode,
    # must count that episode once (not twice).
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb et \xc2\xabZelda BOTW\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/e.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    episodes = _parse_feed(rss)
    episode_index, game_index = feeds.build_indexes(episodes)
    state.episodes = episodes
    state.episode_index   = episode_index
    state.game_index      = game_index
    now = '2999-01-01T00:00:00'
    set_cache({
        f"{make_slug('Zelda')}-g1":
            cache_entry('z-g1', 1, 'zelda-botw', 'Zelda BOTW', {'metacritic': 97}, False, now),
        f"{make_slug('Zelda BOTW')}-g1":
            cache_entry('zb-g1', 1, 'zelda-botw', 'Zelda BOTW', {'metacritic': 97}, False, now),
    })
    catalog = serializers.build_catalog()
    entry = next(g for g in catalog if g['slug'] == 'zelda-botw')
    assert entry['episodeCount'] == 1


def test_count_pending_respects_ttl():
    """TTL-expired-but-cached appearances are counted as pending; freshly cached
    ones are not. Guards the datetime compare."""
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/e.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    episodes = _parse_feed(rss)
    _, game_index = feeds.build_indexes(episodes)
    state.game_index = game_index
    slugs = [a.podcast_slug for g in game_index.values() for a in g.appearances]
    assert slugs

    def cache_with(cached_at):
        return {s: cache_entry(s, 1, 'zelda', 'Zelda', {'metacritic': 90}, False, cached_at) for s in slugs}

    set_cache(cache_with(utcnow().isoformat()))
    assert resolver.count_pending() == 0                # fresh → nothing pending

    set_cache(cache_with('2000-01-01T00:00:00'))
    assert resolver.count_pending() == len(slugs)       # TTL-expired → all pending


# ── GET /games ────────────────────────────────────────────────────────────────

def test_no_auth_returns_401(client):
    r = client.get('/games')
    assert_contract(r, GAMES['catalog']['unauthorized'])


def test_catalog_returns_list(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        r = client.get('/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])
    data = r.get_json()
    assert isinstance(data['games'], list)
    assert any(g['name'] == 'Zelda' for g in data['games'])


def test_catalog_response_has_igdb_field(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        r = client.get('/games', headers=auth_header())
    data = r.get_json()
    assert all('igdb' in g for g in data['games'])


def test_cache_hit_skips_fetch(client):
    with patch('feeds.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
        client.get('/games', headers=auth_header())
    mock_get.assert_called_once()


def test_catalog_deduplicates_by_igdb_slug(client):
    rss_two_names = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>z1</guid>
    <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
    <description>00:30 Zelda</description>
  </item>
  <item>
    <title>On a joue a \xc2\xabZelda BotW\xc2\xbb</title>
    <guid>z2</guid>
    <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate>
    <description>00:30 Zelda BotW</description>
  </item>
</channel></rss>"""
    rss_two_names = rss_two_names.replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())

    set_cache({
        'zelda-z1':      cache_entry('zelda-z1',      1, 'zelda', 'Zelda', None, False, '2099-01-01'),
        'zelda-botw-z2': cache_entry('zelda-botw-z2', 1, 'zelda', 'Zelda', None, False, '2099-01-01'),
    })
    with patch('feeds.http.get', return_value=mock_rss_response(rss_two_names)), \
         patch('resolver.schedule_resolve'):
        r = client.get('/games', headers=auth_header())

    data = r.get_json()['games']
    zelda_entries = [g for g in data if g['slug'] == 'zelda']
    assert len(zelda_entries) == 1
    assert zelda_entries[0]['episodeCount'] == 2


def test_refresh_serves_cache_on_parse_error(client):
    # warm the in-memory catalog
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    # a malformed feed (non-RequestException) must NOT 500 when we already have data
    with patch('feeds.refresh_feed', side_effect=ValueError('malformed XML')), \
         patch('resolver.quick_pass'), patch('resolver.schedule_resolve'):
        r = client.post('/games/refresh', headers=auth_header())
    assert r.status_code == 200
    assert any(g['name'] == 'Zelda' for g in r.get_json()['games'])


def test_catalog_returns_304_on_matching_etag(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        r1 = client.get('/games', headers=auth_header())
    etag = r1.headers.get('ETag')
    assert etag
    # second load with the same ETag and an unchanged catalog → 304, no re-transfer
    r2 = client.get('/games', headers={**auth_header(), 'If-None-Match': etag})
    assert r2.status_code == 304
    assert r2.get_data() == b''


@pytest.mark.parametrize('url', ['/games', '/games/episodes'])
def test_revalidation_accepts_the_weak_etag_gzip_leaves(client, url):
    # The edge gzips these responses, which turns the ETag weak: the browser then
    # revalidates with W/"…" and must still get a 304, not the full body again.
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    etag = client.get(url, headers=auth_header()).headers['ETag']
    r = client.get(url, headers={**auth_header(), 'If-None-Match': f'W/{etag}'})
    assert r.status_code == 304


def test_catalog_igdb_is_slim(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        r = client.get('/games', headers=auth_header())
    data = r.get_json()['games']
    for game in data:
        if game['igdb'] is not None:
            assert set(game['igdb'].keys()) == {'metacritic', 'coverImageId'}


# ── GET /games/<slug> ─────────────────────────────────────────────────────────

def test_game_detail_returns_episodes(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/Zelda', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)
    assert len(data['episodes']) > 0
    assert data['episodes'][0]['audioUrl'] == 'https://example.com/ep1.mp3'


def test_game_detail_surfaces_display_name_and_igdb_name(client, tmp_corrections):
    # displayName pre-fills the picker's « Nom affiché »; igdbName is the true
    # resolution behind the entry (top-level `name` is already the override).
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2', 'Silent Hill 2'),
    })
    corrections.upsert('Silent Hill 2', display_name='Silent Hill 2 (2001)')
    r = client.get('/games/silent-hill-2', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['success'])
    data = r.get_json()
    assert data['name']        == 'Silent Hill 2 (2001)'
    assert data['displayName'] == 'Silent Hill 2 (2001)'
    assert data['igdbName']    == 'Silent Hill 2'


# ── POST /games/refresh ───────────────────────────────────────────────────────

def test_refresh_always_fetches(client):
    with patch('feeds.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('resolver.quick_pass'), patch('resolver.schedule_resolve'):
        r = client.post('/games/refresh', headers=auth_header())
    assert_contract(r, GAMES['refresh']['success'])
    mock_get.assert_called_once()


def test_catalog_does_not_refetch_once_loaded(client):
    # The background tick owns feed freshness; a read never triggers a fetch
    # beyond the cold-start one, however old the catalog is.
    with patch('feeds.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
        state.cached_at = datetime.datetime(2000, 1, 1)
        client.get('/games', headers=auth_header())
    mock_get.assert_called_once()


def test_unchanged_feed_keeps_the_data_version(client):
    # Polled every tick and nearly always 304: rebuilding would bump the version
    # and invalidate every client's catalog ETag for nothing.
    with patch('feeds.http.get', return_value=mock_rss_response()):
        feeds.refresh_feed()
    version = state.data_version
    with patch('feeds.http.get', return_value=mock_rss_response(status=304)):
        feeds.refresh_feed()
    assert state.data_version == version


def _igdb_hit(name):
    from igdb import IgdbResult
    return IgdbResult(id=7, name=name, slug=make_slug(name),
                      data={'coverImageId': 'abc'}, is_child=False)


def test_refresh_resolves_new_games_without_the_scrapers(client):
    # Someone pulling to refresh after an episode came out should get the new
    # games' names and covers in that response; the slow scrapers wait.
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.fetch_by_name', side_effect=lambda n, ts: _igdb_hit(n)), \
         patch('resolver.metacritic.fetch_metascore') as mc, \
         patch('resolver.hltb.fetch_time_to_beat') as hl, \
         patch('resolver.schedule_resolve'):
        r = client.post('/games/refresh', headers=auth_header())
    mc.assert_not_called()
    hl.assert_not_called()
    zelda = next(g for g in r.get_json()['games'] if g['name'] == 'Zelda')
    assert zelda['igdb'] == {'metacritic': None, 'coverImageId': 'abc'}
    # Not enriched yet → still pending, so the background sweep finishes the job.
    assert all(not g.enriched for g in state.games.values())
    assert resolver.count_pending() == len(state.resolutions)


def test_refresh_leaves_new_games_to_the_sweep_once_the_budget_is_spent(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.fetch_by_name') as by_name, \
         patch('resolver.schedule_resolve') as sweep, \
         patch('resolver.REFRESH_BUDGET_S', 0):
        client.post('/games/refresh', headers=auth_header())
    by_name.assert_not_called()
    sweep.assert_called_once_with()


def test_unenriched_flag_survives_a_restart():
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Zelda')):
        resolver.resolve_one('zelda-g1', 'Zelda', None, enrich=False)
    state.load_igdb_cache_from_db()
    assert state.entry('zelda-g1').game.enriched is False


# ── POST /games/<slug>/igdb-refresh ──────────────────────────────────────────

def test_igdb_refresh_returns_game_detail(client):
    episodes = _parse_feed(MINIMAL_RSS)
    episode_index, game_index = feeds.build_indexes(episodes)
    state.episodes = episodes
    state.episode_index   = episode_index
    state.game_index      = game_index
    with patch('resolver.resolve_one'):
        r = client.post('/games/Zelda/igdb-refresh', headers=auth_header())
    assert_contract(r, GAMES['igdb_refresh']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)


# ── GET /games/episodes ───────────────────────────────────────────────────────

_UNIFIED_EPISODE_KEYS = ('title', 'slug', 'urlSlug', 'audioUrl', 'pubTs', 'imageUrl',
                         'description', 'chapters', 'games', 'podcast', 'timestamp', 'timestampSeconds')

# The feed *list* is a slim shape: `description` and `chapters` are omitted (they're
# served by the single-episode detail) to keep the payload small.
_SLIM_EPISODE_KEYS = tuple(k for k in _UNIFIED_EPISODE_KEYS if k not in ('description', 'chapters'))

def test_episodes_returns_list_with_slim_shape(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/episodes', headers=auth_header())
    assert_contract(r, GAMES['episodes']['success'])
    data = r.get_json()
    assert isinstance(data, list) and len(data) > 0
    for key in _SLIM_EPISODE_KEYS:
        assert key in data[0], f"missing '{key}' in feed episode"
    # Heavy fields must NOT be in the list payload — they belong to the detail endpoint.
    assert 'description' not in data[0]
    assert 'chapters'    not in data[0]


# ── GET /games/episode ────────────────────────────────────────────────────────

def test_episode_detail_returns_unified_shape(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    slug = client.get('/games/episodes', headers=auth_header()).get_json()[0]['slug']
    r = client.get(f'/games/episode?slug={slug}', headers=auth_header())
    assert_contract(r, GAMES['episode']['success'])
    # The single-episode endpoint keeps the FULL shape (incl. description + chapters).
    body = r.get_json()
    for key in _UNIFIED_EPISODE_KEYS:
        assert key in body, f"missing '{key}' in episode detail"

def test_episode_missing_slug_returns_400(client):
    r = client.get('/games/episode', headers=auth_header())
    assert_contract(r, GAMES['episode']['bad_request'])

def test_episode_unknown_slug_returns_404(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/episode?slug=does-not-exist', headers=auth_header())
    assert_contract(r, GAMES['episode']['not_found'])


# ── Per-appearance catalog grouping ───────────────────────────────────────────

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


def test_same_name_resolving_to_two_games_splits_into_two_entries():
    # One podcast name covering two distinct IGDB games (the 2001 original and the
    # 2024 remake) must yield two catalog entries — not one absorbing the other.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake':   _entry(f'{ns}-remake',   2, 'silent-hill-2--1', 'Silent Hill 2', released='2024'),
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2',    'Silent Hill 2', released='2001'),
    })
    catalog = serializers.build_catalog()
    slugs   = {g['slug'] for g in catalog}
    assert {'silent-hill-2', 'silent-hill-2--1'} <= slugs

    # …and each detail page lists only its own episode.
    original = serializers.load_game('silent-hill-2')
    remake   = serializers.load_game('silent-hill-2--1')
    assert [e['slug'] for e in original['episodes']] == ['original']
    assert [e['slug'] for e in remake['episodes']]   == ['remake']
    assert original['igdb']['released'] == '2001'
    assert remake['igdb']['released']   == '2024'


def test_name_variants_resolving_to_one_game_still_merge():
    # The converse of the split: two spellings landing on one igdb_slug stay merged.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
  <item><title>On a joue a \xc2\xabZelda BOTW\xc2\xbb</title>
    <guid>g2</guid><enclosure url="https://example.com/2.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda BOTW</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    _seed(rss, {
        f"{make_slug('Zelda')}-g1":      _entry('a', 1, 'zelda-botw', 'Zelda BOTW'),
        f"{make_slug('Zelda BOTW')}-g2": _entry('b', 1, 'zelda-botw', 'Zelda BOTW'),
    })
    catalog = [g for g in serializers.build_catalog() if g['slug'] == 'zelda-botw']
    assert len(catalog) == 1
    assert catalog[0]['episodeCount'] == 2
    assert len(serializers.load_game('zelda-botw')['episodes']) == 2


def test_unresolved_appearances_group_under_name_slug():
    ns = make_slug('Silent Hill 2')
    # Only the remake episode is resolved; the other is still pending.
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 2, 'silent-hill-2--1', 'Silent Hill 2', released='2024'),
    })
    catalog = {g['slug']: g for g in serializers.build_catalog()}
    assert catalog[ns]['igdb'] is None                       # unresolved bucket
    assert catalog['silent-hill-2--1']['igdb'] is not None
    # The name_slug entry carries only the unresolved appearance.
    assert [e['slug'] for e in serializers.load_game(ns)['episodes']] == ['original']


def test_name_slug_that_is_also_an_igdb_slug_serves_the_resolved_group():
    # make_slug('Silent Hill 2') == the original's igdb_slug. The resolved group
    # must win, so /game/silent-hill-2 is the 2001 game, not a mixed bag.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake':   _entry(f'{ns}-remake',   2, 'silent-hill-2--1', 'Silent Hill 2', released='2024'),
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2',    'Silent Hill 2', released='2001'),
    })
    detail = serializers.load_game(ns)
    assert [e['slug'] for e in detail['episodes']] == ['original']
    assert detail['igdb']['released'] == '2001'


def test_detail_falls_back_to_all_appearances_for_a_fully_resolved_name_slug():
    # A stale /game/<name_slug> link, for a name that is NOT itself an igdb_slug
    # and whose appearances have all resolved, must still render rather than 404.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda BOTW\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda BOTW</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    ns = make_slug('Zelda BOTW')       # 'zelda-botw' ≠ igdb slug below
    _seed(rss, {f'{ns}-g1': _entry(f'{ns}-g1', 1, 'the-legend-of-zelda-breath-of-the-wild', 'Zelda')})
    detail = serializers.load_game(ns)
    assert len(detail['episodes']) == 1
    assert detail['igdb'] is None      # unresolved fallback shape


def test_detail_episodes_are_newest_first():
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})
    pts = [e['pubTs'] for e in serializers.load_game(ns)['episodes']]
    assert pts == sorted(pts, reverse=True)


def test_unknown_slug_still_404s():
    _seed(_TWO_EPISODES_SAME_NAME, {})
    with pytest.raises(Exception):
        serializers.load_game('no-such-game')


# ── Resolution: per-podcast date hint + corrections ───────────────────────────

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


def _resolve_capturing(rss, podcast_id):
    """Run resolve_one for the single appearance of `rss` and report what
    fetch_by_name was called with."""
    podcast  = PODCAST_BY_ID[podcast_id]
    episodes = _parse_feed(rss, extractor=podcast.extractor, podcast_id=podcast.id)
    _, game_index = feeds.build_indexes(episodes)
    state.game_index = game_index
    game       = next(iter(game_index.values()))
    appearance = game.appearances[0]
    with patch('resolver.fetch_by_name', return_value=None) as by_name:
        resolver.resolve_one(appearance.podcast_slug, game.name,
                                  appearance.episode.pub_ts, appearance.episode.podcast_id)
    return by_name


def test_retrospective_podcast_resolves_without_the_date_window():
    # Fin du Game covers old games from recent episodes: passing the episode date
    # would search IGDB around 2026 and land on an unrelated new release.
    by_name = _resolve_capturing(_FDG_RSS, 'fin-du-game')
    assert by_name.call_args.args == ('Chrono Trigger', None)


def test_news_podcast_still_uses_the_episode_date_as_a_hint():
    by_name = _resolve_capturing(_SOJ_RSS, 'silence-on-joue')
    name, pub_ts = by_name.call_args.args
    assert name == 'Chrono Trigger'
    assert pub_ts is not None


def test_a_pinned_correction_beats_the_name_search(tmp_corrections):
    from igdb import IgdbResult
    import corrections
    ns = make_slug('Chrono Trigger')
    corrections.upsert('Chrono Trigger', igdb_id=4242)
    result = IgdbResult(id=4242, name='Chrono Trigger', slug='chrono-trigger',
                        data={'metacritic': 92}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=result) as by_id, \
         patch('resolver.fetch_by_name') as by_name, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve_one(f'{ns}-fdg1', 'Chrono Trigger', 0, 'fin-du-game')
    by_name.assert_not_called()
    # canonical=False: a human's pin must not be redirected to a parent game.
    assert by_id.call_args == ((4242,), {'canonical': False})
    assert state.entry(f'{ns}-fdg1').igdb_slug == 'chrono-trigger'


def test_podcast_scoped_correction_beats_the_all_podcasts_one(tmp_corrections):
    import corrections
    corrections.upsert('Chrono Trigger', igdb_id=1)
    corrections.upsert('Chrono Trigger', 'fin-du-game', igdb_id=2)
    find = corrections.find_by_podcast
    assert find('Chrono Trigger', None, 'fin-du-game')['igdb_id']   == 2
    assert find('Chrono Trigger', None, 'silence-on-joue')['igdb_id'] == 1
    assert find('Chrono Trigger', None, '')['igdb_id']              == 1
    assert find('Other Game', None, 'fin-du-game') is None


# ── Re-resolve when a corrections.json ships to a deployed instance ────────────

def _single_soj_game():
    """Build a one-game index from an SOJ episode; return (game, appearance)."""
    podcast  = PODCAST_BY_ID['silence-on-joue']
    episodes = _parse_feed(_SOJ_RSS, extractor=podcast.extractor, podcast_id=podcast.id)
    _, game_index = feeds.build_indexes(episodes)
    state.game_index = game_index
    game = next(iter(game_index.values()))
    return game, game.appearances[0]


def _fresh_entry(appearance, sig):
    """A freshly-cached (not TTL-stale) entry, so pending depends only on `sig`."""
    return cache_entry(appearance.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger',
                       {'metacritic': 90}, False, utcnow().isoformat(), correction_sig=sig)


def _sig_for(appearance, game):
    import corrections
    return corrections.fingerprint(corrections.find_by_podcast(
        game.name, appearance.episode.pub_ts, appearance.episode.podcast_id))


def test_shipped_pin_makes_a_previously_uncorrected_entry_pending(tmp_corrections):
    import corrections
    game, appearance = _single_soj_game()
    cache = {appearance.podcast_slug: _fresh_entry(appearance, '')}   # resolved with no correction
    assert not resolver.appearance_pending(game, appearance, cache)
    corrections.upsert('Chrono Trigger', igdb_id=4242)               # ship a pin
    assert resolver.appearance_pending(game, appearance, cache)


def test_removed_correction_makes_a_pinned_entry_pending(tmp_corrections):
    import corrections
    game, appearance = _single_soj_game()
    corrections.upsert('Chrono Trigger', igdb_id=4242)
    cache = {appearance.podcast_slug: _fresh_entry(appearance, _sig_for(appearance, game))}
    assert not resolver.appearance_pending(game, appearance, cache)
    corrections.remove('Chrono Trigger')                            # ship its removal
    assert resolver.appearance_pending(game, appearance, cache)


def test_shipped_display_name_does_not_make_an_entry_pending(tmp_corrections):
    import corrections
    game, appearance = _single_soj_game()
    cache = {appearance.podcast_slug: _fresh_entry(appearance, '')}
    corrections.upsert('Chrono Trigger', display_name='Chrono Trigger (SNES)')
    assert not resolver.appearance_pending(game, appearance, cache)


def test_count_pending_flags_a_stale_correction_signature(tmp_corrections):
    import corrections
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: _fresh_entry(appearance, '')})

    assert resolver.count_pending() == 0
    corrections.upsert('Chrono Trigger', igdb_id=4242)
    assert resolver.count_pending() == 1


def test_legacy_igdb_cache_is_split_into_resolutions_and_games():
    # The table before the split: one row per appearance, the game's data copied
    # into each. Two rows on game 1 (the quick pass's and an enriched one), a
    # miss, and a row from before correction_sig existed.
    with get_db() as conn:
        conn.execute('CREATE TABLE igdb_cache (slug TEXT PRIMARY KEY, igdb_id INTEGER, '
                     'igdb_slug TEXT, name TEXT, igdb_data TEXT, is_child INTEGER DEFAULT 0, '
                     'cached_at TEXT NOT NULL, correction_sig TEXT, enriched INTEGER DEFAULT 1, '
                     'method TEXT)')
        conn.executemany('INSERT INTO igdb_cache VALUES (?,?,?,?,?,?,?,?,?,?)', [
            ('zelda-g1', 1, 'zelda', 'Zelda', '{"metacritic": 97}', 0, '2026-01-01', None, 1, None),
            ('zelda-g2', 1, 'zelda', 'Zelda', '{}', 1, '2026-02-01', 'sig', 0, 'llm'),
            ('nope-g3', None, None, None, None, 0, '2026-03-01', '', 1, 'search'),
        ])
    _db.init_db()
    with get_db() as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'igdb_cache'").fetchone()
    state.load_igdb_cache_from_db()

    assert set(state.resolutions) == {'zelda-g1', 'zelda-g2', 'nope-g3'}
    assert state.resolutions['zelda-g1'].correction_sig == ''     # NULL: no correction
    assert (state.resolutions['zelda-g2'].is_child, state.resolutions['zelda-g2'].method) \
        == (True, 'llm')
    assert state.resolutions['nope-g3'].igdb_id is None
    # One game, from its enriched copy even though the other is newer.
    assert list(state.games) == [1]
    assert (state.games[1].data, state.games[1].enriched) == ({'metacritic': 97}, True)


def test_prune_drops_orphaned_resolutions_then_unused_games():
    game, appearance = _single_soj_game()
    gone = 'old-name-gone-guid'                      # an appearance no longer in the feed
    for e in (_fresh_entry(appearance, ''),
              cache_entry(gone, 2, 'gone-game', 'Gone Game')):
        state.store_resolution(e.resolution)
        state.store_game(e.game)
    state.store_game(cache_entry('x', 3, 'never-used', 'Never Used').game)

    state.prune_igdb_cache()

    assert set(state.resolutions) == {appearance.podcast_slug}
    assert set(state.games) == {1}                   # 2 lost its last resolution; 3 had none
    state.load_igdb_cache_from_db()                  # …and the DB agrees
    assert (set(state.resolutions), set(state.games)) == ({appearance.podcast_slug}, {1})


def test_prune_keeps_everything_when_the_feed_parsed_empty():
    # A transient empty parse must not wipe the cache.
    state.store_resolution(cache_entry('a-g1', 1, 'a', 'A').resolution)
    state.store_game(cache_entry('a-g1', 1, 'a', 'A').game)
    state.game_index = {}
    state.prune_igdb_cache()
    assert (set(state.resolutions), set(state.games)) == ({'a-g1'}, {1})


def test_resolve_one_stores_the_correction_fingerprint(tmp_corrections):
    from igdb import IgdbResult
    import corrections
    ns = make_slug('Chrono Trigger')
    corrections.upsert('Chrono Trigger', igdb_id=4242)
    result = IgdbResult(id=4242, name='Chrono Trigger', slug='chrono-trigger',
                        data={'metacritic': 92}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=result), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve_one(f'{ns}-fdg1', 'Chrono Trigger', 0, 'fin-du-game')
    entry    = state.entry(f'{ns}-fdg1')
    expected = corrections.fingerprint(
        corrections.find_by_podcast('Chrono Trigger', 0, 'fin-du-game'))
    assert entry.resolution.correction_sig == expected != ''


# ── The sweep: decisions, then each game's data ───────────────────────────────

_EXPIRED = '2000-01-01T00:00:00'


def _sweep(cached, by_id=None):
    """Run the background sweep over Chrono Trigger's appearance with `cached`
    (a function of the appearance) in the cache; returns the two IGDB mocks."""
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: cached(appearance)})
    with patch('resolver.fetch_by_id', return_value=by_id) as by_id_mock, \
         patch('resolver.fetch_by_name', return_value=_igdb_hit('Chrono Trigger')) as by_name, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.schedule_resolve()
    return by_id_mock, by_name, appearance.podcast_slug


def test_an_expired_game_is_renewed_by_id_not_searched_again(tmp_corrections):
    # A fresh search could land on a same-name game IGDB added since, undoing a
    # resolution that was right; the known id can't.
    from igdb import IgdbResult
    expired_child = lambda a: cache_entry(   # noqa: E731
        a.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger', {'metacritic': 90},
        is_child=True, at=_EXPIRED)
    by_id, by_name, slug = _sweep(expired_child, IgdbResult(
        id=1, name='Chrono Trigger', slug='chrono-trigger', data={'metacritic': 93},
        is_child=False))
    by_id.assert_called_once_with(1, canonical=False)
    by_name.assert_not_called()
    entry = state.entry(slug)
    assert entry.data['metacritic'] == 93
    assert entry.is_child            # still ranks as the DLC/version it was resolved from


def test_a_game_igdb_dropped_is_searched_again(tmp_corrections):
    expired = lambda a: cache_entry(   # noqa: E731
        a.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger', at=_EXPIRED)
    by_id, by_name, slug = _sweep(expired, by_id=None)
    by_id.assert_called_once_with(1, canonical=False)
    assert state.entry(slug) is None and 1 not in state.games
    assert resolver.count_pending() == 1          # the next sweep searches it again


def test_a_cached_miss_is_searched_again_once_expired(tmp_corrections):
    miss = lambda at: lambda a: cache_entry(a.podcast_slug, None, None, None, at=at)  # noqa: E731
    by_id, by_name, _ = _sweep(miss(utcnow().isoformat()))
    by_name.assert_not_called()
    by_id, by_name, slug = _sweep(miss(_EXPIRED))
    by_id.assert_not_called()
    by_name.assert_called_once()
    assert state.entry(slug).igdb_id == 7


def test_a_changed_correction_searches_again(tmp_corrections):
    # Resolved under a correction that has since been removed: its id may be the
    # very thing the curator took back.
    by_id, by_name, _ = _sweep(lambda a: _fresh_entry(a, 'some-older-correction'))
    by_id.assert_not_called()
    by_name.assert_called_once()


def test_an_igdb_error_is_retried_after_a_backoff_not_every_sweep(tmp_corrections):
    game, appearance = _single_soj_game()
    slug = appearance.podcast_slug
    with patch('resolver.fetch_by_name', side_effect=OSError('IGDB down')):
        resolver.resolve_appearance(game, appearance)
    failed = state.resolutions[slug]
    assert (failed.igdb_id, failed.attempts, failed.last_error) == (None, 1, 'IGDB down')
    assert failed.retry_at > utcnow().isoformat()
    assert resolver.count_pending() == 0                   # waiting out its backoff

    state.resolutions[slug] = replace(failed, retry_at=_EXPIRED)
    assert resolver.count_pending() == 1                   # due again
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Chrono Trigger')), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve_appearance(game, appearance)
    settled = state.resolutions[slug]
    assert (settled.igdb_id, settled.attempts, settled.retry_at) == (7, 0, None)


def test_a_failed_retry_keeps_serving_the_previous_match(tmp_corrections):
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: _fresh_entry(appearance, 'some-older-correction')})
    with patch('resolver.fetch_by_name', side_effect=OSError('IGDB down')):
        resolver.resolve_appearance(game, appearance)
    entry = state.entry(appearance.podcast_slug)
    assert (entry.igdb_slug, entry.resolution.attempts) == ('chrono-trigger', 1)


def test_stats_count_erroring_appearances_apart_from_misses(client):
    ns = make_slug('Silent Hill 2')
    miss    = cache_entry(f'{ns}-original', None, None, None)
    failing = cache_entry(f'{ns}-remake', None, None, None)
    failing = type(failing)(replace(failing.resolution, attempts=2,
                                    retry_at='2999-01-01T00:00:00'), None)
    _seed(_TWO_EPISODES_SAME_NAME, {f'{ns}-original': miss, f'{ns}-remake': failing})
    r = client.get('/games/resolution-stats', headers=admin_header())
    soj = next(p for p in r.get_json()['podcasts'] if p['id'] == 'silence-on-joue')
    assert (soj['failed'], soj['retrying'], soj['pending']) == (1, 1, 0)


def test_a_settled_appearance_on_a_fresh_game_costs_nothing(tmp_corrections):
    by_id, by_name, _ = _sweep(lambda a: _fresh_entry(a, ''))
    by_id.assert_not_called()
    by_name.assert_not_called()


# ── Admin gating ──────────────────────────────────────────────────────────────

from conftest import admin_header   # noqa: E402

_ADMIN_GETS  = ['/games/resolution-stats', '/games/igdb-search?q=zelda']


@pytest.mark.parametrize('path', _ADMIN_GETS)
def test_admin_endpoints_reject_anonymous(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize('path', _ADMIN_GETS)
def test_admin_endpoints_reject_non_admin(client, path):
    assert client.get(path, headers=auth_header()).status_code == 403


def test_correction_write_rejects_non_admin(client):
    r = client.put('/games/corrections', headers=auth_header(),
                   json={'nameSlug': 'zelda', 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['forbidden'])


def test_podcast_refresh_rejects_non_admin(client):
    r = client.post('/games/podcasts/fin-du-game/igdb-refresh', headers=auth_header())
    assert_contract(r, GAMES['podcast_igdb_refresh']['forbidden'])


def test_igdb_search_requires_a_query(client):
    r = client.get('/games/igdb-search', headers=admin_header())
    assert_contract(r, GAMES['igdb_search']['bad_request'])


def test_igdb_search_returns_results(client):
    rows = [{'id': 1, 'name': 'Chrono Trigger', 'slug': 'chrono-trigger',
             'released': '1995', 'coverImageId': 'co1'}]
    with patch('games.search_games', return_value=rows):
        r = client.get('/games/igdb-search?q=chrono', headers=admin_header())
    assert_contract(r, GAMES['igdb_search']['success'])
    assert r.get_json()['results'] == rows


def test_correction_rejects_an_unknown_podcast(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.put('/games/corrections', headers=admin_header(),
                   json={'nameSlug': make_slug('Silent Hill 2'),
                         'igdbId': 1, 'podcastId': 'nope'})
    assert_contract(r, GAMES['corrections']['bad_request'])


def test_correction_rejects_an_unknown_game(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.put('/games/corrections', headers=admin_header(),
                   json={'nameSlug': 'no-such-game', 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['not_found'])


def test_correction_write_pins_purges_and_reresolves(client, tmp_corrections):
    import json as _json
    from igdb import IgdbResult
    ns = make_slug('Silent Hill 2')
    # Start from a wrong resolution, as the FDG date-window bug produced.
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 9, 'astrobotanica', 'Astrobotanica'),
    })
    fixed = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2',
                       data={'released': '2001'}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=fixed), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['success'])
    body = r.get_json()
    assert body['slug'] == 'silent-hill-2'
    assert body['igdb']['released'] == '2001'
    assert body['corrected'] is True
    # The stale 'astrobotanica' cache row is gone…
    assert state.entry(f'{ns}-original').igdb_slug == 'silent-hill-2'
    # …and the pin landed in the git-tracked file, keyed on the feed's wording.
    written = _json.loads(tmp_corrections.read_text())['corrections']
    assert written == [{'podcast_name': 'Silent Hill 2', 'igdb_id': 1}]


def test_correction_scoped_to_one_podcast_leaves_the_other_alone(client, tmp_corrections):
    from igdb import IgdbResult
    ns  = make_slug('Chrono Trigger')
    soj = _parse_feed(_SOJ_RSS, extractor=PODCAST_BY_ID['silence-on-joue'].extractor,
                      podcast_id='silence-on-joue')
    fdg = _parse_feed(_FDG_RSS, extractor=PODCAST_BY_ID['fin-du-game'].extractor,
                      podcast_id='fin-du-game')
    episodes = soj + fdg
    _assign_url_slugs(episodes)
    episode_index, game_index = feeds.build_indexes(episodes)
    state.episodes = episodes
    state.episode_index   = episode_index
    state.game_index      = game_index
    set_cache({
        f'{ns}-soj1': _entry(f'{ns}-soj1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
        f'{ns}-fdg1': _entry(f'{ns}-fdg1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
    })
    state.data_version += 1

    fixed = IgdbResult(id=1, name='Chrono Trigger', slug='chrono-trigger',
                       data={'released': '1995'}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=fixed), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1, 'podcastId': 'fin-du-game'})
    assert r.status_code == 200
    # Only the FDG appearance moved; the SOJ one keeps its own resolution — the
    # split the per-appearance grouping exists to allow.
    assert state.entry(f'{ns}-fdg1').igdb_slug == 'chrono-trigger'
    assert state.entry(f'{ns}-soj1').igdb_slug == 'chrono-trigger--3'
    assert [e['slug'] for e in r.get_json()['episodes']] == ['fdg1']


def test_delete_correction_reverts_to_the_name_search(client, tmp_corrections):
    import corrections
    from igdb import IgdbResult
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})
    corrections.upsert('Silent Hill 2', igdb_id=1)

    searched = IgdbResult(id=7, name='Silent Hill 2', slug='silent-hill-2',
                          data={'released': '2001'}, is_child=False)
    with patch('resolver.fetch_by_name', return_value=searched) as by_name, \
         patch('resolver.fetch_by_id') as by_id, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.delete('/games/corrections', headers=admin_header(),
                          json={'nameSlug': ns})
    assert r.status_code == 200
    by_id.assert_not_called()      # no longer pinned
    assert by_name.called
    assert corrections.CORRECTIONS == []


def test_delete_correction_that_does_not_exist_404s(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.delete('/games/corrections', headers=admin_header(),
                      json={'nameSlug': make_slug('Silent Hill 2')})
    assert_contract(r, GAMES['corrections']['not_found'])


def test_corrections_write_is_refused_when_the_file_is_read_only(client, tmp_corrections):
    # Stands in for prod, where corrections.json ships in the read-only image layer.
    _seed(_TWO_EPISODES_SAME_NAME, {})
    with patch('corrections.is_writable', return_value=False):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': make_slug('Silent Hill 2'), 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['read_only'])
    assert 'dev' in r.get_json()['error']


def test_podcast_igdb_refresh_purges_only_that_podcast(client):
    ns  = make_slug('Chrono Trigger')
    soj = _parse_feed(_SOJ_RSS, extractor=PODCAST_BY_ID['silence-on-joue'].extractor,
                      podcast_id='silence-on-joue')
    fdg = _parse_feed(_FDG_RSS, extractor=PODCAST_BY_ID['fin-du-game'].extractor,
                      podcast_id='fin-du-game')
    _, game_index = feeds.build_indexes(soj + fdg)
    state.game_index = game_index
    set_cache({
        f'{ns}-soj1': _entry(f'{ns}-soj1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
        f'{ns}-fdg1': _entry(f'{ns}-fdg1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
    })
    with patch('resolver.schedule_resolve') as sched:
        r = client.post('/games/podcasts/fin-du-game/igdb-refresh',
                        headers=admin_header())
    assert_contract(r, GAMES['podcast_igdb_refresh']['success'])
    assert r.get_json()['purged'] == 1
    assert f'{ns}-fdg1' not in state.resolutions     # purged
    assert f'{ns}-soj1' in state.resolutions         # untouched
    sched.assert_called_once()


def test_podcast_igdb_refresh_unknown_podcast_404s(client):
    r = client.post('/games/podcasts/nope/igdb-refresh', headers=admin_header())
    assert_contract(r, GAMES['podcast_igdb_refresh']['not_found'])


def test_resolution_stats_shape(client):
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        # 'Silent Hill 2' → 'Astrobotanica' is exactly the kind of miss to surface.
        f'{ns}-remake':   _entry(f'{ns}-remake', 9, 'astrobotanica', 'Astrobotanica'),
        f'{ns}-original': cache_entry(f'{ns}-original', None, None, None, None, False, _NOW),
    })
    r = client.get('/games/resolution-stats', headers=admin_header())
    assert_contract(r, GAMES['resolution_stats']['success'])
    body = r.get_json()

    soj = next(p for p in body['podcasts'] if p['id'] == 'silence-on-joue')
    assert soj['appearances'] == 2
    assert soj['resolved']    == 1     # the astrobotanica row
    assert soj['failed']      == 1     # negatively cached (igdb_id NULL)

    by_status = {g['status']: g for g in body['games']}
    assert by_status['suspect']['igdbSlug'] == 'astrobotanica'
    assert by_status['unresolved']['nameSlug'] == ns


@pytest.mark.parametrize('podcast_name,igdb_name', [
    ('Kirby',             'Kirby and the Forgotten World'),   # subtitle
    ('Astrobot',          'Astro Bot'),                       # spacing only
    ('Zelda BOTW',        'Zelda BOTW'),                      # identical
    ('Hades 2',           'Hades II'),                        # roman numerals
    ('Crusader Kings 3',  'Crusader Kings III'),
    ('Planet of Lana 2',  'Planet of Lana II: Children of the Leaf'),  # roman + subtitle
    ('Little Nightmare 3', 'Little Nightmares III'),          # roman + plural
    ('Still Wake The Deep', 'Still Wakes the Deep'),          # typo in the feed
    ('Senua’s Saga Hellblade II', 'Hellblade II: Senua’s Saga'),  # reordered
])
def test_is_suspect_passes_benign_differences(podcast_name, igdb_name):
    assert not review.is_suspect(podcast_name, igdb_name)


@pytest.mark.parametrize('podcast_name,igdb_name', [
    ('Astrobot',                           'Astrobotanica'),   # mid-word prefix
    ('Silent Hill 2',                      'Resident Evil'),
    ('Myst',                               'Mystery of the Malign'),
    ('Castlevania: Symphony of the Night', "Castlevania: Belmont's Curse"),
])
def test_is_suspect_flags_unrelated_names(podcast_name, igdb_name):
    assert review.is_suspect(podcast_name, igdb_name)


def test_suspects_exclude_names_a_human_already_ruled_on(client):
    # «Les gardiens de la galaxie» → «Marvel's Guardians of the Galaxy» is a
    # curated correction: intentional, however unalike the names look. Flagging it
    # every time would bury the real misses.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabLes gardiens de la galaxie\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 x</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    ns = make_slug('Les gardiens de la galaxie')
    _seed(rss, {f'{ns}-g1': _entry(f'{ns}-g1', 1, 'guardians', "Marvel's Guardians of the Galaxy")})
    # The heuristic alone would flag it…
    assert review.is_suspect('Les gardiens de la galaxie',
                                    "Marvel's Guardians of the Galaxy")
    # …but the curated correction rules it out: it reads as resolved, not suspect.
    r = client.get('/games/resolution-stats', headers=admin_header())
    row = next(g for g in r.get_json()['games'] if g['nameSlug'] == ns)
    assert row['status'] == 'resolved'
    assert row['corrected'] is True


def test_stats_reports_a_merged_group_under_its_resolving_name(client):
    # Two spellings merged into one entry. The summary must name the variant that
    # actually resolved (not whichever sorts first) and list every name behind it,
    # so a correction can't silently pin only one of them.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda BOTW\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda BOTW</description></item>
  <item><title>On a joue a \xc2\xabAstrobot\xc2\xbb</title>
    <guid>g2</guid><enclosure url="https://example.com/2.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Astrobot</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    botw, astro = make_slug('Zelda BOTW'), make_slug('Astrobot')
    _seed(rss, {
        # Both land on the same (wrong) igdb_slug → one group, two name variants.
        f'{botw}-g1':  cache_entry(f'{botw}-g1', 9, 'astrobotanica', 'Astrobotanica',
                                              {}, False, '2000-01-01T00:00:00'),
        f'{astro}-g2': cache_entry(f'{astro}-g2', 9, 'astrobotanica', 'Astrobotanica',
                                              {}, False, _NOW),   # newest → representative
    })
    r = client.get('/games/resolution-stats', headers=admin_header())
    suspect = next(g for g in r.get_json()['games'] if g['slug'] == 'astrobotanica')
    assert suspect['status']    == 'suspect'
    assert suspect['nameSlug']  == astro                  # the newest-cached variant
    assert suspect['nameSlugs'] == sorted([astro, botw])  # both surfaced


def test_detail_reports_whether_a_correction_applies(client, tmp_corrections):
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})
    assert serializers.load_game(ns)['corrected'] is False

    corrections.upsert('Silent Hill 2', igdb_id=1)
    assert serializers.load_game(ns)['corrected'] is True


def test_detail_corrected_flag_respects_podcast_scope(client, tmp_corrections):
    # A correction scoped to a podcast this entry has no episodes from must not
    # light up the "remove the correction" affordance.
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})          # seeded as silence-on-joue
    corrections.upsert('Silent Hill 2', 'fin-du-game', igdb_id=1)
    assert serializers.load_game(ns)['corrected'] is False


def test_stats_marks_rows_a_correction_already_rules_on(client, tmp_corrections):
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 9, 'astrobotanica', 'Astrobotanica'),
    })
    # Unruled: the heuristic flags the bad match for review.
    body = client.get('/games/resolution-stats', headers=admin_header()).get_json()
    assert [g['igdbSlug'] for g in body['games'] if g['status'] == 'suspect'] == ['astrobotanica']
    assert body['writable'] is True

    # Once a human has ruled on it, nothing is suspect and every row is marked.
    corrections.upsert('Silent Hill 2', igdb_id=1)
    body = client.get('/games/resolution-stats', headers=admin_header()).get_json()
    assert [g for g in body['games'] if g['status'] == 'suspect'] == []
    soj = next(p for p in body['podcasts'] if p['id'] == 'silence-on-joue')
    assert soj['corrected'] == 2          # both appearances of the name
    assert all(g['corrected'] for g in body['games'])


def test_stats_reports_read_only_deployments(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    with patch('corrections.is_writable', return_value=False):
        body = client.get('/games/resolution-stats', headers=admin_header()).get_json()
    assert body['writable'] is False


# ── Admin console: row shape + display-name edits ─────────────────────────────

def test_stats_row_carries_what_the_console_renders(client, tmp_corrections):
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 2, 'silent-hill-2--1', 'Silent Hill 2',
                               released='2024', coverImageId='co42'),
    })
    body = client.get('/games/resolution-stats', headers=admin_header()).get_json()
    row  = next(g for g in body['games'] if g['slug'] == 'silent-hill-2--1')
    assert row['coverImageId'] == 'co42'
    assert row['released']     == '2024'
    # The episode a reviewer opens to judge the match: the newest appearance.
    assert row['episodeSlug']  == 'on-a-joue-a-silent-hill-2'
    assert row['episodeTitle'] == 'On a joue a «Silent Hill 2»'
    assert row['displayName'] is None


def test_stats_rows_are_newest_first(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    body = client.get('/games/resolution-stats', headers=admin_header()).get_json()
    pts = [g['latestPubTs'] or 0 for g in body['games']]
    assert pts == sorted(pts, reverse=True)


def test_stats_surfaces_the_current_display_name(client, tmp_corrections):
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})
    corrections.upsert('Silent Hill 2', display_name='Silent Hill 2 (2001)')
    body = client.get('/games/resolution-stats', headers=admin_header()).get_json()
    row  = next(g for g in body['games'] if g['nameSlug'] == ns)
    assert row['displayName'] == 'Silent Hill 2 (2001)'
    assert row['corrected'] is True


def test_catalog_applies_a_podcast_scoped_display_name(tmp_corrections):
    # group_display_name must look the correction up at the appearance's own
    # podcast scope, or a podcast_id-scoped rename would show in the admin
    # console (which passes podcast_id) but never in the catalog.
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 2, 'silent-hill-2-remake', 'Silent Hill 2 Remake'),
    })
    corrections.upsert('Silent Hill 2', 'silence-on-joue',
                       display_name='Silent Hill 2 (renommé)')
    names = {g['slug']: g['name'] for g in serializers.build_catalog()}
    assert names['silent-hill-2-remake'] == 'Silent Hill 2 (renommé)'


def test_renaming_does_not_re_resolve(client, tmp_corrections):
    # display_name is applied at response time, so a rename must not burn a round
    # of IGDB + Metacritic + HLTB calls to arrive at the same entry.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2', 'Silent Hill 2'),
    })
    before = state.data_version
    with patch('resolver.fetch_by_id') as by_id, patch('resolver.fetch_by_name') as by_name:
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'displayName': 'Silent Hill 2 (2001)'})
    assert_contract(r, GAMES['corrections']['success'])
    by_id.assert_not_called()
    by_name.assert_not_called()
    # The cached resolution survives…
    assert state.entry(f'{ns}-original').igdb_slug == 'silent-hill-2'
    # …but the derived caches are invalidated so the new name is served.
    assert state.data_version > before
    assert r.get_json()['name'] == 'Silent Hill 2 (2001)'


def test_correction_requires_a_pin_or_a_name(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.put('/games/corrections', headers=admin_header(),
                   json={'nameSlug': make_slug('Silent Hill 2')})
    assert_contract(r, GAMES['corrections']['bad_request'])


def test_correction_rejects_a_non_integer_pin(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.put('/games/corrections', headers=admin_header(),
                   json={'nameSlug': make_slug('Silent Hill 2'), 'igdbId': 'nope'})
    assert_contract(r, GAMES['corrections']['bad_request'])


def test_a_game_is_scraped_once_for_all_its_episodes():
    # Metacritic and HowLongToBeat take ~1–10 s a game: a second episode on the
    # same game reuses the figures instead of scraping them again.
    hit = lambda n, ts: _igdb_hit('Zelda')
    with patch('resolver.fetch_by_name', side_effect=hit), \
         patch('resolver.metacritic.fetch_metascore', return_value=91) as mc, \
         patch('resolver.hltb.fetch_time_to_beat', return_value=40) as hl:
        resolver.resolve_one('zelda-ep1', 'Zelda', None, use_llm=False)
        resolver.resolve_one('zelda-ep2', 'Zelda', None, use_llm=False)
    assert mc.call_count == hl.call_count == 1
    second = state.entry('zelda-ep2')
    assert second.game.enriched
    assert (second.data['metacritic'], second.data['timeToBeatHours']) == (91, 40)


def test_a_correction_moving_onto_a_cached_game_reuses_its_data(client, tmp_corrections):
    # Pinning re-decides which game this is; that game's data is already here.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 9, 'astrobotanica', 'Astrobotanica'),
        f'{ns}-remake':   _entry(f'{ns}-remake', 1, 'silent-hill-2', 'Silent Hill 2',
                                 metacritic=89),
    })
    from igdb import IgdbResult
    pinned = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2',
                        data={}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=pinned), \
         patch('resolver.metacritic.fetch_metascore') as mc:
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1})
    mc.assert_not_called()
    assert r.get_json()['igdb']['metacritic'] == 89
    assert state.entry(f'{ns}-original').igdb_slug == 'silent-hill-2'


def test_an_explicit_igdb_refresh_fetches_the_games_data_again(client):
    # The one way to get a fresh Metacritic score before the TTL.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 1, 'silent-hill-2', 'Silent Hill 2',
                               metacritic=80),
    })
    from igdb import IgdbResult
    same = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2', data={}, is_child=False)
    with patch('resolver.fetch_by_name', return_value=same), \
         patch('resolver.metacritic.fetch_metascore', return_value=89) as mc, \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.post('/games/silent-hill-2/igdb-refresh', headers=auth_header())
    assert r.status_code == 200
    mc.assert_called_once()
    assert state.games[1].data['metacritic'] == 89
