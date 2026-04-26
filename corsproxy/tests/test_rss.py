import datetime
import json
from unittest.mock import patch, MagicMock

import jwt
import pytest
import requests as real_requests

import db
from config import Config
from contract import assert_contract, CONTRACT
from rss import (
    _correct, _extract_chapters, _extract_game_names,
    _find_timestamp, _is_non_game_chapter, _parse_feed, _parse_timestamp,
    _strip_html,
)

RSS = CONTRACT['rss']

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


def auth_header(email='user@example.com'):
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    token = jwt.encode(
        {'sub': '1', 'email': email, 'iat': now,
         'exp': now + datetime.timedelta(hours=1)},
        Config.JWT_SECRET, algorithm='HS256',
    )
    return {'Authorization': f'Bearer {token}'}


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


# ── _correct ──────────────────────────────────────────────────────────────────

def test_correct_known_misspelling():
    assert _correct('Artic Eggs') == 'Arctic Eggs'

def test_correct_case_insensitive():
    assert _correct('artic eggs') == 'Arctic Eggs'

def test_correct_passthrough():
    assert _correct('Elden Ring') == 'Elden Ring'


# ── _parse_feed ───────────────────────────────────────────────────────────────

def test_parse_feed_returns_game_list():
    games = _parse_feed(MINIMAL_RSS)
    names = [g['name'] for g in games]
    assert 'Zelda' in names
    assert 'Mario Kart' in names

def test_parse_feed_filters_non_game_episodes():
    games = _parse_feed(MINIMAL_RSS)
    assert len(games) == 2

def test_parse_feed_sets_audio_url():
    games = _parse_feed(MINIMAL_RSS)
    zelda = next(g for g in games if g['name'] == 'Zelda')
    assert zelda['episodes'][0]['audioUrl'] == 'https://example.com/ep1.mp3'

def test_parse_feed_resolves_timestamps():
    games = _parse_feed(MINIMAL_RSS)
    zelda = next(g for g in games if g['name'] == 'Zelda')
    assert zelda['episodes'][0]['timestamp'] == '00:30'
    assert zelda['episodes'][0]['timestampSeconds'] == 30

def test_parse_feed_sorted_alphabetically():
    games = _parse_feed(MINIMAL_RSS)
    assert games[0]['name'].lower() <= games[1]['name'].lower()


# ── HTTP endpoint ─────────────────────────────────────────────────────────────

def test_no_auth_returns_401(client):
    r = client.get('/rss/games')
    assert_contract(r, RSS['games']['unauthorized'])


def test_games_returns_list(client):
    with patch('rss.http.get', return_value=mock_rss_response()):
        r = client.get('/rss/games', headers=auth_header())
    assert_contract(r, RSS['games']['success'])
    data = r.get_json()
    assert isinstance(data, list)
    assert any(g['name'] == 'Zelda' for g in data)


def test_cache_hit_skips_fetch(client):
    with patch('rss.http.get', return_value=mock_rss_response()) as mock_get:
        client.get('/rss/games', headers=auth_header())
        client.get('/rss/games', headers=auth_header())
    mock_get.assert_called_once()


def test_expired_cache_refetches(client):
    stale = (datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
             - datetime.timedelta(minutes=61)).isoformat()
    with db.get_db() as conn:
        conn.execute(
            'INSERT INTO games_cache (key, data, cached_at) VALUES (?, ?, ?)',
            ('feed', json.dumps([{'name': 'Old Game', 'episodes': []}]), stale),
        )
    with patch('rss.http.get', return_value=mock_rss_response()) as mock_get:
        r = client.get('/rss/games', headers=auth_header())
    assert_contract(r, RSS['games']['success'])
    mock_get.assert_called_once()


def test_upstream_error_returns_502(client):
    with patch('rss.http.get',
               side_effect=real_requests.exceptions.ConnectionError('down')):
        r = client.get('/rss/games', headers=auth_header())
    assert_contract(r, RSS['games']['upstream_error'])
