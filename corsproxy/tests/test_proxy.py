import datetime
from unittest.mock import patch, MagicMock
import jwt
import requests as real_requests
from config import Config
from contract import assert_contract, PROXY


FEED_URL = 'https://feeds.example.com/rss'


def auth_header(email='user@example.com'):
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    token = jwt.encode(
        {'sub': '1', 'email': email, 'iat': now,
         'exp': now + datetime.timedelta(hours=1)},
        Config.JWT_SECRET, algorithm='HS256',
    )
    return {'Authorization': f'Bearer {token}'}


def mock_upstream(body=b'<rss/>', status=200, content_type='text/xml'):
    m = MagicMock()
    m.status_code = status
    m.headers = {'Content-Type': content_type}
    m.raw.stream.return_value = iter([body])
    return m


# ── Authentication ─────────────────────────────────────────────────────────

def test_no_auth_returns_403(client):
    r = client.get(f'/proxy?url={FEED_URL}')
    assert_contract(r, PROXY['unauthorized'])

def test_invalid_token_returns_403(client):
    r = client.get(f'/proxy?url={FEED_URL}',
                   headers={'Authorization': 'Bearer bad.token.here'})
    assert_contract(r, PROXY['unauthorized'])

def test_expired_token_returns_403(client):
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    token = jwt.encode(
        {'sub': '1', 'email': 'x@x.com', 'iat': past, 'exp': past},
        Config.JWT_SECRET, algorithm='HS256',
    )
    r = client.get(f'/proxy?url={FEED_URL}',
                   headers={'Authorization': f'Bearer {token}'})
    assert_contract(r, PROXY['unauthorized'])


# ── Parameter validation ───────────────────────────────────────────────────

def test_missing_url_param_returns_400(client):
    r = client.get('/proxy', headers=auth_header())
    assert_contract(r, PROXY['missing_url'])

def test_empty_url_param_returns_400(client):
    r = client.get('/proxy?url=', headers=auth_header())
    assert_contract(r, PROXY['missing_url'])

def test_non_http_scheme_returns_400(client):
    r = client.get('/proxy?url=ftp://bad.example.com/feed', headers=auth_header())
    assert_contract(r, PROXY['invalid_url'])

def test_relative_url_returns_400(client):
    r = client.get('/proxy?url=/local/path', headers=auth_header())
    assert_contract(r, PROXY['invalid_url'])


# ── Success ────────────────────────────────────────────────────────────────

def test_proxies_upstream_body(client):
    with patch('app.requests.request', return_value=mock_upstream(b'<rss/>')):
        r = client.get(f'/proxy?url={FEED_URL}', headers=auth_header())
    assert_contract(r, PROXY['success'])

def test_passes_auth_header_upstream(client):
    with patch('app.requests.request', return_value=mock_upstream()) as mock_req:
        client.get(f'/proxy?url={FEED_URL}', headers=auth_header())
    forwarded = mock_req.call_args.kwargs['headers']
    assert 'Authorization' in forwarded


# ── Upstream errors ────────────────────────────────────────────────────────

def test_upstream_connection_error_returns_502(client):
    with patch('app.requests.request',
               side_effect=real_requests.exceptions.ConnectionError('down')):
        r = client.get(f'/proxy?url={FEED_URL}', headers=auth_header())
    assert_contract(r, PROXY['upstream_error'])

def test_upstream_timeout_returns_504(client):
    with patch('app.requests.request',
               side_effect=real_requests.exceptions.Timeout('timed out')):
        r = client.get(f'/proxy?url={FEED_URL}', headers=auth_header())
    assert_contract(r, PROXY['timeout'])

def test_upstream_request_error_returns_502(client):
    with patch('app.requests.request',
               side_effect=real_requests.exceptions.RequestException('generic')):
        r = client.get(f'/proxy?url={FEED_URL}', headers=auth_header())
    assert_contract(r, PROXY['upstream_error'])
