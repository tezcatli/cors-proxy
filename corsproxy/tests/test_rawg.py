import json
import datetime
from unittest.mock import patch, MagicMock
import jwt
import requests as real_requests
import pytest
from config import Config
import db
from contract import assert_contract, RAWG


# ── Helpers ────────────────────────────────────────────────────────────────

def auth_header(email='user@example.com'):
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    token = jwt.encode(
        {'sub': '1', 'email': email, 'iat': now,
         'exp': now + datetime.timedelta(hours=1)},
        Config.JWT_SECRET, algorithm='HS256',
    )
    return {'Authorization': f'Bearer {token}'}


def mock_response(data):
    m = MagicMock()
    m.json.return_value = data
    m.raise_for_status.return_value = None
    return m


SAMPLE = {'results': [{'id': 1, 'name': 'Test Game'}], 'count': 1}


# ── Authentication ─────────────────────────────────────────────────────────

def test_no_auth_returns_401(client):
    r = client.get('/rawg/games?search=zelda')
    assert_contract(r, RAWG['games']['unauthorized'])

def test_invalid_token_returns_401(client):
    r = client.get('/rawg/games?search=zelda',
                   headers={'Authorization': 'Bearer bad.token.here'})
    assert_contract(r, RAWG['games']['unauthorized'])

def test_expired_token_returns_401(client):
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    token = jwt.encode(
        {'sub': 1, 'email': 'x@x.com', 'iat': past, 'exp': past},
        Config.JWT_SECRET, algorithm='HS256',
    )
    r = client.get('/rawg/games?search=zelda',
                   headers={'Authorization': f'Bearer {token}'})
    assert_contract(r, RAWG['games']['unauthorized'])


# ── Cache miss → upstream fetch ────────────────────────────────────────────

def test_cache_miss_fetches_upstream(client):
    with patch('rawg.http.get', return_value=mock_response(SAMPLE)) as mock_get:
        r = client.get('/rawg/games?search=zelda', headers=auth_header())
    assert_contract(r, RAWG['games']['success'])
    assert r.get_json() == SAMPLE
    mock_get.assert_called_once()
    params = mock_get.call_args.kwargs['params']
    assert params['key'] == Config.RAWG_KEY
    assert params['search'] == 'zelda'


# ── Cache hit → no upstream call ───────────────────────────────────────────

def test_cache_hit_skips_upstream(client):
    with patch('rawg.http.get', return_value=mock_response(SAMPLE)):
        client.get('/rawg/games?search=zelda', headers=auth_header())

    with patch('rawg.http.get') as mock_get:
        r = client.get('/rawg/games?search=zelda', headers=auth_header())
    assert_contract(r, RAWG['games']['success'])
    mock_get.assert_not_called()


# ── Expired cache → refetch ────────────────────────────────────────────────

def test_expired_cache_refetches_upstream(client):
    stale_time = (datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(days=31)).isoformat()
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO rawg_cache (key, data, cached_at) VALUES (?, ?, ?)",
            ('games?search=zelda', json.dumps(SAMPLE), stale_time),
        )

    fresh = {'results': [{'id': 2, 'name': 'Fresh Game'}]}
    with patch('rawg.http.get', return_value=mock_response(fresh)) as mock_get:
        r = client.get('/rawg/games?search=zelda', headers=auth_header())
    assert_contract(r, RAWG['games']['success'])
    mock_get.assert_called_once()


# ── Upstream errors ────────────────────────────────────────────────────────

def test_upstream_connection_error_returns_502(client):
    with patch('rawg.http.get',
               side_effect=real_requests.exceptions.ConnectionError('down')):
        r = client.get('/rawg/games?search=zelda', headers=auth_header())
    assert_contract(r, RAWG['games']['upstream_error'])

def test_upstream_timeout_returns_502(client):
    with patch('rawg.http.get',
               side_effect=real_requests.exceptions.Timeout('timeout')):
        r = client.get('/rawg/games?search=zelda', headers=auth_header())
    assert_contract(r, RAWG['games']['upstream_error'])


# ── Missing RAWG key ───────────────────────────────────────────────────────

def test_no_rawg_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(Config, 'RAWG_KEY', '')
    r = client.get('/rawg/games?search=zelda', headers=auth_header())
    assert_contract(r, RAWG['games']['no_key'])


# ── Cache key is path-specific ─────────────────────────────────────────────

def test_different_queries_cached_separately(client):
    zelda = {'results': [{'id': 1, 'name': 'Zelda'}]}
    mario = {'results': [{'id': 2, 'name': 'Mario'}]}
    with patch('rawg.http.get', side_effect=[mock_response(zelda), mock_response(mario)]):
        r1 = client.get('/rawg/games?search=zelda', headers=auth_header())
        r2 = client.get('/rawg/games?search=mario', headers=auth_header())
    assert r1.get_json()['results'][0]['name'] == 'Zelda'
    assert r2.get_json()['results'][0]['name'] == 'Mario'
