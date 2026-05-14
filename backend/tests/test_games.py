import datetime
from unittest.mock import patch, MagicMock

import pytest

import games as games_module
from contract import assert_contract, CONTRACT
from conftest import auth_header
from rss import extract_game_names as _extract_game_names, extract_legacy_names as _extract_legacy_names, parse_feed as _parse_feed

GAMES = CONTRACT['games']

MINIMAL_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <item>
      <title>On a joue a \xc2\xabZelda\xc2\xbb et \xc2\xabMario Kart\xc2\xbb</title>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="0" />
      <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
      <description>00:30 Zelda
01:00 Mario Kart
01:30 Outro</description>
    </item>
    <item>
      <title>Quelle est la meilleure plateforme ?</title>
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

def test_parse_feed_filters_non_game_episodes():
    episodes = _parse_feed(MINIMAL_RSS)
    assert len(episodes) == 1
    assert len(episodes[0].games) == 2

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


# ── GET /games ────────────────────────────────────────────────────────────────

def test_no_auth_returns_401(client):
    r = client.get('/silence/games')
    assert_contract(r, GAMES['catalog']['unauthorized'])


def test_catalog_returns_list(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        r = client.get('/silence/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])
    data = r.get_json()
    assert isinstance(data, list)
    assert any(g['name'] == 'Zelda' for g in data)


def test_catalog_response_has_igdb_field(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        r = client.get('/silence/games', headers=auth_header())
    data = r.get_json()
    assert all('igdb' in g for g in data)


def test_cache_hit_skips_fetch(client):
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
        client.get('/silence/games', headers=auth_header())
    mock_get.assert_called_once()


def test_expired_cache_refetches(client):
    games_module._cached_at = (datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                               - datetime.timedelta(hours=9))
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('games._schedule_resolve'):
        r = client.get('/silence/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])
    mock_get.assert_called_once()


def test_catalog_deduplicates_by_igdb_slug(client):
    rss_two_names = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
    <description>00:30 Zelda</description>
  </item>
  <item>
    <title>On a joue a \xc2\xabZelda BotW\xc2\xbb</title>
    <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate>
    <description>00:30 Zelda BotW</description>
  </item>
</channel></rss>"""
    rss_two_names = rss_two_names.replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())

    from models import IgdbEntry
    igdb_cache = {
        'zelda-20240115':      IgdbEntry('zelda-20240115',      1, 'zelda', 'Zelda', None, False, '2099-01-01'),
        'zelda-botw-20240122': IgdbEntry('zelda-botw-20240122', 1, 'zelda', 'Zelda', None, False, '2099-01-01'),
    }
    with patch('games.http.get', return_value=mock_rss_response(rss_two_names)), \
         patch('games._schedule_resolve'), \
         patch.object(games_module, '_igdb_cache', igdb_cache):
        r = client.get('/silence/games', headers=auth_header())

    data = r.get_json()
    zelda_entries = [g for g in data if g['slug'] == 'zelda']
    assert len(zelda_entries) == 1
    assert zelda_entries[0]['episodeCount'] == 2


def test_catalog_igdb_is_slim(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        r = client.get('/silence/games', headers=auth_header())
    data = r.get_json()
    for game in data:
        if game['igdb'] is not None:
            assert set(game['igdb'].keys()) == {'metacritic'}


# ── GET /games/<slug> ─────────────────────────────────────────────────────────

def test_game_detail_returns_episodes(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
    r = client.get('/silence/games/Zelda', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)
    assert len(data['episodes']) > 0
    assert data['episodes'][0]['audioUrl'] == 'https://example.com/ep1.mp3'


# ── POST /games/refresh ───────────────────────────────────────────────────────

def test_refresh_always_fetches(client):
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get:
        r = client.post('/silence/games/refresh', headers=auth_header())
    assert_contract(r, GAMES['refresh']['success'])
    mock_get.assert_called_once()


# ── POST /games/<slug>/igdb-refresh ──────────────────────────────────────────

def test_igdb_refresh_returns_game_detail(client):
    episodes = _parse_feed(MINIMAL_RSS)
    episode_index, game_index = games_module._build_indexes(episodes)
    games_module._cached_episodes = episodes
    games_module._episode_index   = episode_index
    games_module._game_index      = game_index
    with patch('games._resolve_one'):
        r = client.post('/silence/games/Zelda/igdb-refresh', headers=auth_header())
    assert_contract(r, GAMES['igdb_refresh']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)


# ── GET /games/igdb ───────────────────────────────────────────────────────────

def test_igdb_returns_map(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
    r = client.get('/silence/games/igdb?slug=zelda&slug=mario-kart', headers=auth_header())
    assert_contract(r, GAMES['igdb']['success'])
    data = r.get_json()
    assert isinstance(data, dict)
