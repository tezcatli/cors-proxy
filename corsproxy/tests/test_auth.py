import datetime
import jwt
import pytest
from config import Config
import db
from contract import assert_contract, AUTH


# ── Helpers ────────────────────────────────────────────────────────────────

def make_invite(client, email='user@example.com'):
    r = client.post('/auth/invite',
                    json={'email': email},
                    headers={'X-Admin-Key': Config.ADMIN_KEY})
    assert_contract(r, AUTH['invite']['success'])
    return r.get_json()['invite_url'].split('?invite=')[1]


def register(client, email='user@example.com', password='password123', invite_token=None):
    if invite_token is None:
        invite_token = make_invite(client, email)
    return client.post('/auth/register',
                       json={'email': email, 'password': password,
                             'invitation_token': invite_token})


def login(client, email='user@example.com', password='password123'):
    return client.post('/auth/login', json={'email': email, 'password': password})


def _insert_reset_token(email, expires_delta_seconds):
    with db.get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        token = 'test-reset-token'
        expires = (db.utcnow() + datetime.timedelta(seconds=expires_delta_seconds)).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user['id'], expires),
        )
    return token


# ── POST /auth/invite ──────────────────────────────────────────────────────

def test_invite_no_key(client):
    r = client.post('/auth/invite', json={'email': 'a@b.com'})
    assert_contract(r, AUTH['invite']['forbidden'])

def test_invite_wrong_key(client):
    r = client.post('/auth/invite', json={'email': 'a@b.com'},
                    headers={'X-Admin-Key': 'wrong'})
    assert_contract(r, AUTH['invite']['forbidden'])

def test_invite_missing_email(client):
    r = client.post('/auth/invite', json={},
                    headers={'X-Admin-Key': Config.ADMIN_KEY})
    assert_contract(r, AUTH['invite']['bad_email'])

def test_invite_success(client):
    r = client.post('/auth/invite', json={'email': 'a@b.com'},
                    headers={'X-Admin-Key': Config.ADMIN_KEY})
    assert_contract(r, AUTH['invite']['success'])
    assert 'invite=' in r.get_json()['invite_url']


# ── GET /auth/invite-info/<token> ──────────────────────────────────────────

def test_invite_info_valid(client):
    token = make_invite(client, 'info@example.com')
    r = client.get(f'/auth/invite-info/{token}')
    assert_contract(r, AUTH['invite_info']['success'])
    assert r.get_json()['email'] == 'info@example.com'

def test_invite_info_unknown(client):
    r = client.get('/auth/invite-info/no-such-token')
    assert_contract(r, AUTH['invite_info']['not_found'])

def test_invite_info_used(client):
    token = make_invite(client, 'used@example.com')
    register(client, 'used@example.com', invite_token=token)
    r = client.get(f'/auth/invite-info/{token}')
    assert_contract(r, AUTH['invite_info']['used'])


# ── POST /auth/register ────────────────────────────────────────────────────

def test_register_success(client):
    r = register(client)
    assert_contract(r, AUTH['register']['success'])

def test_register_missing_invite_token(client):
    r = client.post('/auth/register',
                    json={'email': 'a@b.com', 'password': 'password123'})
    assert_contract(r, AUTH['register']['invalid_invite'])

def test_register_invalid_invite_token(client):
    r = client.post('/auth/register',
                    json={'email': 'a@b.com', 'password': 'password123',
                          'invitation_token': 'bad-token'})
    assert_contract(r, AUTH['register']['invalid_invite'])

def test_register_email_mismatch(client):
    token = make_invite(client, 'real@example.com')
    r = client.post('/auth/register',
                    json={'email': 'other@example.com', 'password': 'password123',
                          'invitation_token': token})
    assert_contract(r, AUTH['register']['invalid_invite'])

def test_register_invite_already_used(client):
    token = make_invite(client, 'once@example.com')
    register(client, 'once@example.com', invite_token=token)
    r = client.post('/auth/register',
                    json={'email': 'once@example.com', 'password': 'newpassword1',
                          'invitation_token': token})
    assert_contract(r, AUTH['register']['invalid_invite'])

def test_register_duplicate_email(client):
    register(client, 'dup@example.com')
    token2 = make_invite(client, 'dup@example.com')
    r = client.post('/auth/register',
                    json={'email': 'dup@example.com', 'password': 'password123',
                          'invitation_token': token2})
    assert_contract(r, AUTH['register']['duplicate_email'])

def test_register_weak_password(client):
    token = make_invite(client, 'weak@example.com')
    r = client.post('/auth/register',
                    json={'email': 'weak@example.com', 'password': 'short',
                          'invitation_token': token})
    assert_contract(r, AUTH['register']['weak_password'])


# ── POST /auth/login ───────────────────────────────────────────────────────

def test_login_success(client):
    register(client, 'login@example.com', 'mypassword')
    r = login(client, 'login@example.com', 'mypassword')
    assert_contract(r, AUTH['login']['success'])
    payload = jwt.decode(r.get_json()['access_token'], Config.JWT_SECRET, algorithms=['HS256'])
    assert payload['email'] == 'login@example.com'

def test_login_wrong_password(client):
    register(client, 'lp@example.com', 'correctpass')
    r = login(client, 'lp@example.com', 'wrongpass')
    assert_contract(r, AUTH['login']['bad_credentials'])

def test_login_unknown_email(client):
    r = login(client, 'nobody@example.com')
    assert_contract(r, AUTH['login']['bad_credentials'])

def test_login_missing_fields(client):
    r = client.post('/auth/login', json={'email': 'a@b.com'})
    assert_contract(r, AUTH['login']['missing_fields'])

def test_login_case_insensitive_email(client):
    register(client, 'Case@Example.com', 'password123')
    r = login(client, 'case@example.com', 'password123')
    assert_contract(r, AUTH['login']['success'])


# ── POST /auth/reset-request ───────────────────────────────────────────────

def test_reset_request_unknown_email_returns_204(client):
    r = client.post('/auth/reset-request', json={'email': 'unknown@example.com'})
    assert_contract(r, AUTH['reset_request']['success'])

def test_reset_request_creates_token(client):
    register(client, 'reset@example.com')
    r = client.post('/auth/reset-request', json={'email': 'reset@example.com'})
    assert_contract(r, AUTH['reset_request']['success'])
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT token FROM reset_tokens "
            "WHERE user_id = (SELECT id FROM users WHERE email = 'reset@example.com')"
        ).fetchone()
    assert row is not None


# ── POST /auth/reset-confirm ───────────────────────────────────────────────

def test_reset_confirm_success(client):
    register(client, 'confirm@example.com', 'oldpassword')
    token = _insert_reset_token('confirm@example.com', 3600)
    r = client.post('/auth/reset-confirm',
                    json={'token': token, 'new_password': 'newpassword1'})
    assert_contract(r, AUTH['reset_confirm']['success'])
    assert_contract(login(client, 'confirm@example.com', 'newpassword1'), AUTH['login']['success'])

def test_reset_confirm_old_password_rejected(client):
    register(client, 'changed@example.com', 'oldpassword')
    token = _insert_reset_token('changed@example.com', 3600)
    client.post('/auth/reset-confirm',
                json={'token': token, 'new_password': 'newpassword1'})
    r = login(client, 'changed@example.com', 'oldpassword')
    assert_contract(r, AUTH['login']['bad_credentials'])

def test_reset_confirm_invalid_token(client):
    r = client.post('/auth/reset-confirm',
                    json={'token': 'bad-token', 'new_password': 'newpassword1'})
    assert_contract(r, AUTH['reset_confirm']['invalid_token'])

def test_reset_confirm_expired_token(client):
    register(client, 'expired@example.com', 'oldpassword')
    token = _insert_reset_token('expired@example.com', -1)
    r = client.post('/auth/reset-confirm',
                    json={'token': token, 'new_password': 'newpassword1'})
    assert_contract(r, AUTH['reset_confirm']['expired_token'])

def test_reset_confirm_weak_password(client):
    register(client, 'weakreset@example.com', 'oldpassword')
    token = _insert_reset_token('weakreset@example.com', 3600)
    r = client.post('/auth/reset-confirm',
                    json={'token': token, 'new_password': 'short'})
    assert_contract(r, AUTH['reset_confirm']['weak_password'])

def test_reset_confirm_token_consumed(client):
    register(client, 'consumed@example.com', 'oldpassword')
    token = _insert_reset_token('consumed@example.com', 3600)
    client.post('/auth/reset-confirm',
                json={'token': token, 'new_password': 'newpassword1'})
    r = client.post('/auth/reset-confirm',
                    json={'token': token, 'new_password': 'anotherpass1'})
    assert_contract(r, AUTH['reset_confirm']['invalid_token'])
