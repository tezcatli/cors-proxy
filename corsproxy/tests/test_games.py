import datetime
from unittest.mock import patch, MagicMock

import pytest
import requests as real_requests

import db
from contract import assert_contract, CONTRACT
from conftest import auth_header
from games import (
    _extract_chapters, _extract_game_names, _extract_legacy_names,
    _find_timestamp, _is_non_game_chapter, _parse_feed, _parse_timestamp,
    _strip_html, _upsert_games,
)

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


# ── _strip_html ────────────────────────────────────────────────────────────────

def test_strip_html_removes_tags():
    assert _strip_html('<b>hello</b>') == 'hello'

def test_strip_html_converts_p_to_newline():
    result = _strip_html('<p>line1</p><p>line2</p>')
    assert 'line1' in result and 'line2' in result

def test_strip_html_decodes_entities():
    assert _strip_html('&amp;') == '&'
    assert _strip_html('&lt;') == '<'

def test_strip_html_falsy_returns_empty():
    assert _strip_html('') == ''
    assert _strip_html(None) == ''


# ── _parse_timestamp ───────────────────────────────────────────────────────────

def test_parse_timestamp_mm_ss():
    assert _parse_timestamp('01:30') == 90

def test_parse_timestamp_hh_mm_ss():
    assert _parse_timestamp('1:00:00') == 3600

def test_parse_timestamp_empty():
    assert _parse_timestamp('') == 0
    assert _parse_timestamp(None) == 0


# ── _extract_game_names ───────────────────────────────────────────────────────

def test_extract_game_names_guillemets():
    names = _extract_game_names('On a joué à «Zelda» et «Mario»')
    assert names == ['Zelda', 'Mario']

def test_extract_game_names_empty():
    assert _extract_game_names('No guillemets here') == []
    assert _extract_game_names(None) == []

def test_extract_game_names_ignores_single_char():
    assert _extract_game_names('«A»') == []


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


# ── _extract_chapters ─────────────────────────────────────────────────────────

def test_extract_chapters_basic():
    chapters = _extract_chapters('00:30 Zelda\n01:00 Mario')
    assert len(chapters) == 2
    assert chapters[0] == {'timestampSeconds': 30, 'timestamp': '00:30', 'title': 'Zelda'}

def test_extract_chapters_hh_mm_ss():
    chapters = _extract_chapters('1:00:00 Some Game')
    assert chapters[0]['timestampSeconds'] == 3600

def test_extract_chapters_ignores_non_timestamp_lines():
    chapters = _extract_chapters('Just text\n00:30 Zelda')
    assert len(chapters) == 1


# ── _is_non_game_chapter ──────────────────────────────────────────────────────

@pytest.mark.parametrize('title', [
    'intro', 'Intro', 'INTRO',
    'les news', 'Le News',
    'com des coms',
    'outro', 'Outro',
    'générique',
    'bande-annonce', 'bande annonce',
])
def test_is_non_game_chapter_true(title):
    assert _is_non_game_chapter(title)

@pytest.mark.parametrize('title', ['Zelda', 'Mario Kart 8', 'Hollow Knight'])
def test_is_non_game_chapter_false(title):
    assert not _is_non_game_chapter(title)


# ── _find_timestamp ───────────────────────────────────────────────────────────

CHAPTERS = [
    {'timestampSeconds': 30,  'timestamp': '00:30', 'title': 'Intro'},
    {'timestampSeconds': 90,  'timestamp': '01:30', 'title': 'Zelda Breath of the Wild'},
    {'timestampSeconds': 180, 'timestamp': '03:00', 'title': 'Mario Kart'},
    {'timestampSeconds': 270, 'timestamp': '04:30', 'title': 'Outro'},
]

def test_find_timestamp_exact_match():
    ts = _find_timestamp('Mario Kart', CHAPTERS)
    assert ts == {'timestamp': '03:00', 'timestampSeconds': 180}

def test_find_timestamp_partial_match():
    ts = _find_timestamp('Zelda', CHAPTERS)
    assert ts is not None
    assert ts['timestamp'] == '01:30'

def test_find_timestamp_no_match():
    assert _find_timestamp('Halo', CHAPTERS) is None

def test_find_timestamp_skips_non_game():
    assert _find_timestamp('Intro', CHAPTERS) is None


# ── _parse_feed ───────────────────────────────────────────────────────────────

def test_parse_feed_returns_game_list():
    games = _parse_feed(MINIMAL_RSS)
    names = [g['name'] for g in games]
    assert 'Zelda' in names
    assert 'Mario Kart' in names

def test_parse_feed_filters_non_game_episodes():
    games = _parse_feed(MINIMAL_RSS)
    assert len(games) == 2

def test_parse_feed_uses_raw_podcast_name():
    # _parse_feed no longer applies corrections — canonical name comes from IGDB
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
      <item>
        <title>On a joue \xc2\xab artic eggs \xc2\xbb</title>
        <enclosure url="https://example.com/ep3.mp3" type="audio/mpeg" length="0" />
        <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate><description></description>
      </item></channel></rss>"""
    rss = rss.replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    games = _parse_feed(rss)
    assert games[0]['name'].strip() == 'artic eggs'

def test_parse_feed_sets_audio_url():
    games = _parse_feed(MINIMAL_RSS)
    zelda = next(g for g in games if g['name'] == 'Zelda')
    assert zelda['episodes'][0]['audioUrl'] == 'https://example.com/ep1.mp3'

def test_parse_feed_resolves_timestamps():
    games = _parse_feed(MINIMAL_RSS)
    zelda = next(g for g in games if g['name'] == 'Zelda')
    assert zelda['episodes'][0]['timestamp'] == '00:30'
    assert zelda['episodes'][0]['timestampSeconds'] == 30


# ── GET /games ────────────────────────────────────────────────────────────────

def test_no_auth_returns_401(client):
    r = client.get('/games')
    assert_contract(r, GAMES['catalog']['unauthorized'])


def test_catalog_returns_list(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._start_warming'):
        r = client.get('/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])
    data = r.get_json()
    assert isinstance(data, list)
    assert any(g['name'] == 'Zelda' for g in data)


def test_catalog_response_has_igdb_field(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._start_warming'):
        r = client.get('/games', headers=auth_header())
    data = r.get_json()
    assert all('igdb' in g for g in data)


def test_cache_hit_skips_fetch(client):
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('games._start_warming'):
        client.get('/games', headers=auth_header())
        client.get('/games', headers=auth_header())
    mock_get.assert_called_once()


def test_expired_cache_refetches(client):
    stale = (datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
             - datetime.timedelta(minutes=61)).isoformat()
    with db.get_db() as conn:
        conn.execute(
            'INSERT INTO games (display_name, rss_at) VALUES (?, ?)',
            ('Old Game', stale),
        )
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('games._start_warming'):
        r = client.get('/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])
    mock_get.assert_called_once()


def test_upstream_error_returns_502(client):
    with patch('games.http.get',
               side_effect=real_requests.exceptions.ConnectionError('down')):
        r = client.get('/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['upstream_error'])


def test_catalog_has_no_episodes(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._start_warming'):
        r = client.get('/games', headers=auth_header())
    data = r.get_json()
    assert all('episodes' not in g for g in data)
    assert all('episodeCount' in g for g in data)
    assert all('latestPubTs' in g for g in data)


def test_catalog_igdb_is_slim(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._start_warming'):
        r = client.get('/games', headers=auth_header())
    data = r.get_json()
    for game in data:
        if game['igdb'] is not None:
            assert set(game['igdb'].keys()) == {'metacritic'}


# ── GET /games/<slug> ─────────────────────────────────────────────────────────

def test_game_detail_returns_episodes(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._start_warming'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/Zelda', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)
    assert len(data['episodes']) > 0
    assert data['episodes'][0]['audioUrl'] == 'https://example.com/ep1.mp3'


def test_game_detail_not_found(client):
    r = client.get('/games/nonexistent-game', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['not_found'])


def test_game_detail_stale_name_fallback(client):
    """IGDB warming may rename display_name; the old podcast name should still resolve."""
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._start_warming'):
        client.get('/games', headers=auth_header())
    with db.get_db() as conn:
        conn.execute(
            "UPDATE games SET display_name = 'The Legend of Zelda' WHERE lower(display_name) = 'zelda'"
        )
    r = client.get('/games/Zelda', headers=auth_header())
    assert r.status_code == 200
    data = r.get_json()
    assert data['name'] == 'The Legend of Zelda'
    assert isinstance(data['episodes'], list)
    assert len(data['episodes']) > 0


def test_game_detail_no_auth(client):
    r = client.get('/games/Zelda')
    assert_contract(r, GAMES['game_detail']['unauthorized'])


# ── POST /games/refresh ───────────────────────────────────────────────────────

def test_refresh_always_fetches(client):
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('games._start_warming'):
        r = client.post('/games/refresh', headers=auth_header())
    assert_contract(r, GAMES['refresh']['success'])
    mock_get.assert_called_once()


def test_refresh_bypasses_ttl(client):
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('games._start_warming'):
        client.get('/games', headers=auth_header())
        assert mock_get.call_count == 1
        r = client.post('/games/refresh', headers=auth_header())
    assert mock_get.call_count == 2
    data = r.get_json()
    assert isinstance(data, list)


def test_refresh_upstream_error(client):
    with patch('games.http.get',
               side_effect=real_requests.exceptions.ConnectionError('down')):
        r = client.post('/games/refresh', headers=auth_header())
    assert_contract(r, GAMES['refresh']['upstream_error'])


# ── POST /games/<slug>/igdb-refresh ──────────────────────────────────────────

def test_igdb_refresh_returns_game_detail(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._start_warming'):
        client.get('/games', headers=auth_header())
    with patch('games._warm_one'):
        r = client.post('/games/Zelda/igdb-refresh', headers=auth_header())
    assert_contract(r, GAMES['igdb_refresh']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)


def test_igdb_refresh_not_found(client):
    r = client.post('/games/nonexistent-game/igdb-refresh', headers=auth_header())
    assert_contract(r, GAMES['igdb_refresh']['not_found'])


# ── GET /games/igdb ───────────────────────────────────────────────────────────

def test_igdb_returns_map(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._start_warming'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/igdb?name=Zelda&name=Mario+Kart', headers=auth_header())
    assert_contract(r, GAMES['igdb']['success'])
    data = r.get_json()
    assert isinstance(data, dict)


def test_igdb_empty_names_returns_empty(client):
    r = client.get('/games/igdb', headers=auth_header())
    assert r.status_code == 200
    assert r.get_json() == {}


def test_igdb_no_auth_returns_401(client):
    r = client.get('/games/igdb?name=Zelda')
    assert_contract(r, GAMES['igdb']['unauthorized'])
