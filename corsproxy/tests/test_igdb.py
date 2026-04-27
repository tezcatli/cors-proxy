import json
import datetime
from unittest.mock import patch, MagicMock
import jwt
import requests as real_requests
import pytest
from config import Config
import db
import igdb as igdb_module
from contract import assert_contract, IGDB
from conftest import auth_header


def mock_response(data):
    m = MagicMock()
    m.json.return_value = data
    m.raise_for_status.return_value = None
    return m


SAMPLE = [{
    'id': 1,
    'name': 'Test Game',
    'aggregated_rating': 85.0,
    'aggregated_rating_count': 5,
    'rating': 80.0,
    'first_release_date': 1609459200,
    'summary': 'A great game.',
    'genres': [{'name': 'Action'}],
    'platforms': [{'name': 'PC (Microsoft Windows)'}],
    'cover': {'image_id': 'abc123'},
    'age_ratings': [{'category': 1, 'rating': 10}],
    'involved_companies': [{'developer': True, 'company': {'name': 'Test Studio'}}],
}]


@pytest.fixture(autouse=True)
def bypass_igdb_infra(monkeypatch):
    monkeypatch.setattr(igdb_module, '_get_token', lambda: 'test-token')
    monkeypatch.setattr(igdb_module._throttle, 'acquire', lambda: None)


# ── Authentication ─────────────────────────────────────────────────────────

def test_no_auth_returns_401(client):
    r = client.get('/igdb/game?name=zelda')
    assert_contract(r, IGDB['game']['unauthorized'])

def test_invalid_token_returns_401(client):
    r = client.get('/igdb/game?name=zelda',
                   headers={'Authorization': 'Bearer bad.token.here'})
    assert_contract(r, IGDB['game']['unauthorized'])

def test_expired_token_returns_401(client):
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    token = jwt.encode(
        {'sub': 1, 'email': 'x@x.com', 'iat': past, 'exp': past},
        Config.JWT_SECRET, algorithm='HS256',
    )
    r = client.get('/igdb/game?name=zelda',
                   headers={'Authorization': f'Bearer {token}'})
    assert_contract(r, IGDB['game']['unauthorized'])


# ── Missing name ───────────────────────────────────────────────────────────

def test_missing_name_returns_400(client):
    r = client.get('/igdb/game', headers=auth_header())
    assert_contract(r, IGDB['game']['missing_name'])


# ── Cache miss → upstream fetch ────────────────────────────────────────────

def test_cache_miss_fetches_upstream(client):
    with patch('igdb.http.post', return_value=mock_response(SAMPLE)) as mock_post:
        r = client.get('/igdb/game?name=test+game', headers=auth_header())
    assert_contract(r, IGDB['game']['success'])
    data = r.get_json()
    assert data['coverImageId'] == 'abc123'
    assert data['metacritic'] == 85
    assert data['developer'] == 'Test Studio'
    assert data['esrb'] == 'T'
    mock_post.assert_called_once()


# ── Cache hit → no upstream call ───────────────────────────────────────────

def test_cache_hit_skips_upstream(client):
    with patch('igdb.http.post', return_value=mock_response(SAMPLE)):
        client.get('/igdb/game?name=test+game&year=2021', headers=auth_header())

    with patch('igdb.http.post') as mock_post:
        r = client.get('/igdb/game?name=test+game&year=2021', headers=auth_header())
    assert_contract(r, IGDB['game']['success'])
    mock_post.assert_not_called()


# ── Expired cache → refetch ────────────────────────────────────────────────

def test_expired_cache_refetches_upstream(client):
    stale = (datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
             - datetime.timedelta(days=31)).isoformat()
    with db.get_db() as conn:
        conn.execute(
            'INSERT INTO igdb_cache (key, data, cached_at) VALUES (?, ?, ?)',
            ('testgame', json.dumps(SAMPLE[0]), stale),
        )
    fresh = [dict(SAMPLE[0], name='Fresh Game')]
    with patch('igdb.http.post', return_value=mock_response(fresh)) as mock_post:
        r = client.get('/igdb/game?name=test+game', headers=auth_header())
    assert_contract(r, IGDB['game']['success'])
    mock_post.assert_called_once()


# ── Not found in IGDB ──────────────────────────────────────────────────────

def test_not_found_returns_null(client):
    with patch('igdb.http.post', return_value=mock_response([])):
        r = client.get('/igdb/game?name=unknowngame', headers=auth_header())
    assert_contract(r, IGDB['game']['not_found'])
    assert r.get_json() is None

def test_not_found_is_cached(client):
    with patch('igdb.http.post', return_value=mock_response([])) as mock_post:
        client.get('/igdb/game?name=unknowngame', headers=auth_header())
        client.get('/igdb/game?name=unknowngame', headers=auth_header())
    # first request: search + name fallback = 2 upstream calls; second is a cache hit
    assert mock_post.call_count == 2


# ── Upstream errors ────────────────────────────────────────────────────────

def test_upstream_connection_error_returns_502(client):
    with patch('igdb.http.post',
               side_effect=real_requests.exceptions.ConnectionError('down')):
        r = client.get('/igdb/game?name=zelda', headers=auth_header())
    assert_contract(r, IGDB['game']['upstream_error'])

def test_upstream_timeout_returns_502(client):
    with patch('igdb.http.post',
               side_effect=real_requests.exceptions.Timeout('timeout')):
        r = client.get('/igdb/game?name=zelda', headers=auth_header())
    assert_contract(r, IGDB['game']['upstream_error'])


# ── Missing credentials ────────────────────────────────────────────────────

def test_no_credentials_returns_503(client, monkeypatch):
    monkeypatch.setattr(Config, 'IGDB_CLIENT_ID', '')
    r = client.get('/igdb/game?name=zelda', headers=auth_header())
    assert_contract(r, IGDB['game']['no_creds'])


# ── normKey deduplication ──────────────────────────────────────────────────

def test_normalized_names_share_cache(client):
    with patch('igdb.http.post', return_value=mock_response(SAMPLE)) as mock_post:
        client.get('/igdb/game?name=Test+Game&year=2021', headers=auth_header())
        client.get('/igdb/game?name=test+game&year=2021', headers=auth_header())
    mock_post.assert_called_once()


# ── Year filter ────────────────────────────────────────────────────────────

def test_year_filter_added_to_query(client):
    with patch('igdb.http.post', return_value=mock_response(SAMPLE)) as mock_post:
        client.get('/igdb/game?name=test+game&year=2021', headers=auth_header())
    body = mock_post.call_args[1].get('data', '')
    assert 'search "test game"' in body
    assert 'first_release_date >=' in body


def test_name_fallback_on_search_empty(client):
    responses = [mock_response([]), mock_response(SAMPLE)]
    with patch('igdb.http.post', side_effect=responses) as mock_post:
        r = client.get('/igdb/game?name=test+game', headers=auth_header())
    assert_contract(r, IGDB['game']['success'])
    assert mock_post.call_count == 2
    assert 'search "test game"' in mock_post.call_args_list[0][1]['data']
    assert 'where (' in mock_post.call_args_list[1][1]['data']
    assert 'name ~ "test game"' in mock_post.call_args_list[1][1]['data']


def test_year_filter_fallback_on_empty(client):
    # search+year → name+year → search (no year) finds result
    responses = [mock_response([]), mock_response([]), mock_response(SAMPLE)]
    with patch('igdb.http.post', side_effect=responses) as mock_post:
        r = client.get('/igdb/game?name=test+game&year=2021', headers=auth_header())
    assert_contract(r, IGDB['game']['success'])
    assert mock_post.call_count == 3
    assert 'first_release_date >=' in mock_post.call_args_list[0][1]['data']
    assert 'first_release_date >=' in mock_post.call_args_list[1][1]['data']
    assert 'first_release_date >=' not in mock_post.call_args_list[2][1]['data']
