import datetime
import jwt
import pytest
from config import Config
import db
from contract import assert_contract, AUTH
from conftest import auth_header, admin_header


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


def test_reset_confirm_race_between_select_and_delete(client, monkeypatch):
    # A concurrent request can consume the token between the initial SELECT and
    # the DELETE...RETURNING — that must be a 400, not a 500 on a None row.
    from contextlib import contextmanager
    register(client, 'race@example.com', 'oldpassword')
    token = _insert_reset_token('race@example.com', 3600)
    real_get_db = db.get_db
    calls = []

    @contextmanager
    def racy_get_db():
        calls.append(1)
        if len(calls) == 2:   # entering the DELETE block: token already consumed
            with real_get_db() as conn:
                conn.execute("DELETE FROM reset_tokens WHERE token = ?", (token,))
        with real_get_db() as conn:
            yield conn

    monkeypatch.setattr('auth.get_db', racy_get_db)
    r = client.post('/auth/reset-confirm',
                    json={'token': token, 'new_password': 'newpassword1'})
    assert_contract(r, AUTH['reset_confirm']['invalid_token'])


# ── POST /auth/refresh ────────────────────────────────────────────────────────

def test_refresh_success(client):
    register(client, 'refresh@example.com')
    r = login(client, 'refresh@example.com')
    token = r.get_json()['access_token']
    r2 = client.post('/auth/refresh',
                     headers={'Authorization': f'Bearer {token}'})
    assert_contract(r2, AUTH['refresh']['success'])
    payload = jwt.decode(r2.get_json()['access_token'], Config.JWT_SECRET, algorithms=['HS256'])
    assert payload['email'] == 'refresh@example.com'

def test_refresh_requires_auth(client):
    r = client.post('/auth/refresh')
    assert_contract(r, AUTH['refresh']['unauthorized'])

def test_refresh_stream_token_rejected(client):
    r = client.post('/auth/refresh',
                    headers={'Authorization': f'Bearer {_stream_token()}'})
    assert_contract(r, AUTH['refresh']['unauthorized'])

def test_refresh_deleted_user_rejected(client):
    with db.get_db() as conn:
        conn.execute('DELETE FROM users WHERE id = 1')
    r = client.post('/auth/refresh', headers=auth_header())
    assert_contract(r, AUTH['refresh']['unauthorized'])


# ── Stream token + scope (S3) / user-existence revocation (S6) ──────────────

def _stream_token(uid=1):
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    return jwt.encode(
        {'sub': str(uid), 'scope': 'stream', 'iat': now,
         'exp': now + datetime.timedelta(hours=1)},
        Config.JWT_SECRET, algorithm='HS256',
    )


def test_stream_token_endpoint_returns_stream_scoped_token(client):
    r = client.get('/auth/stream-token', headers=auth_header())
    assert r.status_code == 200
    claims = jwt.decode(r.get_json()['token'], Config.JWT_SECRET, algorithms=['HS256'])
    assert claims['scope'] == 'stream'

def test_stream_token_requires_auth(client):
    assert client.get('/auth/stream-token').status_code == 401

def test_stream_scoped_token_rejected_on_data_endpoint(client):
    r = client.get('/games', headers={'Authorization': f'Bearer {_stream_token()}'})
    assert r.status_code == 401

def test_resolution_stream_accepts_stream_token_in_query(client):
    r = client.get(f'/games/resolution-stream?token={_stream_token()}')
    assert r.status_code == 200

def test_resolution_stream_rejects_full_jwt_in_query(client):
    full = auth_header()['Authorization'].split(' ', 1)[1]
    r = client.get(f'/games/resolution-stream?token={full}')
    assert r.status_code == 401

def test_token_for_deleted_user_is_rejected(client):
    with db.get_db() as conn:
        conn.execute('DELETE FROM users WHERE id = 1')
    r = client.get('/games', headers=auth_header())
    assert r.status_code == 401


# ── Admin console: accounts & invitations ──────────────────────────────────
# `admin_header()` promotes the fixture user (id 1) and returns its Bearer
# header, so it doubles as "the caller" for the self-protection guards.

def _make_user(client, email, password='password123', is_admin=False):
    """Register a second account through the real invite → register flow."""
    r = client.post('/auth/invite',
                    json={'email': email, 'is_admin': is_admin},
                    headers={'X-Admin-Key': Config.ADMIN_KEY})
    token = r.get_json()['invite_url'].split('?invite=')[1]
    register(client, email=email, password=password, invite_token=token)
    with db.get_db() as conn:
        return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()['id']


def _session(uid, email='someone@example.com'):
    """A Bearer header for an arbitrary user id (conftest's `auth_header` is
    hard-wired to the fixture user, sub=1)."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    token = jwt.encode({'sub': str(uid), 'email': email, 'iat': now,
                        'exp': now + datetime.timedelta(hours=1)},
                       Config.JWT_SECRET, algorithm='HS256')
    return {'Authorization': f'Bearer {token}'}


def _is_admin(email):
    with db.get_db() as conn:
        return bool(conn.execute("SELECT is_admin FROM users WHERE email = ?",
                                 (email,)).fetchone()['is_admin'])


# invite: two credentials, one endpoint

def test_invite_accepts_an_admin_session(client):
    r = client.post('/auth/invite', json={'email': 'a@b.com'},
                    headers=admin_header())
    assert_contract(r, AUTH['invite']['success'])

def test_invite_rejects_a_non_admin_session(client):
    r = client.post('/auth/invite', json={'email': 'a@b.com'}, headers=auth_header())
    assert_contract(r, AUTH['invite']['forbidden'])

def test_invited_admin_becomes_an_admin_account(client):
    _make_user(client, 'boss@example.com', is_admin=True)
    assert _is_admin('boss@example.com')
    # …and the SPA sees it: the (cosmetic) claim is set at login.
    claims = jwt.decode(login(client, 'boss@example.com').get_json()['access_token'],
                        Config.JWT_SECRET, algorithms=['HS256'])
    assert claims['admin'] is True

def test_invitation_without_the_flag_creates_an_ordinary_account(client):
    _make_user(client, 'plain@example.com')
    assert not _is_admin('plain@example.com')


# GET /auth/users

def test_list_users_requires_authentication(client):
    assert_contract(client.get('/auth/users'), AUTH['list_users']['unauthorized'])

def test_list_users_requires_admin(client):
    assert_contract(client.get('/auth/users', headers=auth_header()),
                    AUTH['list_users']['forbidden'])

def test_list_users_returns_accounts(client):
    headers = admin_header()
    _make_user(client, 'someone@example.com')
    r = client.get('/auth/users', headers=headers)
    assert_contract(r, AUTH['list_users']['success'])
    emails = {u['email'] for u in r.get_json()['users']}
    assert 'someone@example.com' in emails
    assert all({'id', 'email', 'is_admin', 'created_at'} <= set(u) for u in r.get_json()['users'])


# PATCH /auth/users/<id>

def test_promote_and_demote_another_account(client):
    headers = admin_header()
    uid = _make_user(client, 'other@example.com')

    # Their own session can't reach the console before the promotion…
    assert client.get('/auth/users', headers=_session(uid)).status_code == 403

    r = client.patch(f'/auth/users/{uid}', json={'is_admin': True}, headers=headers)
    assert_contract(r, AUTH['update_user']['success'])
    assert _is_admin('other@example.com')
    # …and immediately after it, with the same token: `require_admin` re-reads
    # the DB rather than trusting the JWT's `admin` claim.
    assert client.get('/auth/users', headers=_session(uid)).status_code == 200

    r = client.patch(f'/auth/users/{uid}', json={'is_admin': False}, headers=headers)
    assert r.get_json()['is_admin'] is False
    assert not _is_admin('other@example.com')
    assert client.get('/auth/users', headers=_session(uid)).status_code == 403

def test_update_user_requires_the_field(client):
    assert_contract(client.patch('/auth/users/1', json={}, headers=admin_header()),
                    AUTH['update_user']['missing_fields'])

def test_update_unknown_user(client):
    assert_contract(client.patch('/auth/users/9999', json={'is_admin': True},
                                 headers=admin_header()),
                    AUTH['update_user']['not_found'])

def test_admin_cannot_demote_themselves(client):
    headers = admin_header()
    assert_contract(client.patch('/auth/users/1', json={'is_admin': False}, headers=headers),
                    AUTH['update_user']['self_demote'])
    assert _is_admin('__auth_fixture__@test')

def test_update_user_requires_admin(client):
    assert_contract(client.patch('/auth/users/1', json={'is_admin': True},
                                 headers=auth_header()),
                    AUTH['update_user']['forbidden'])


# DELETE /auth/users/<id>

def test_delete_account_revokes_its_access(client):
    headers = admin_header()
    uid = _make_user(client, 'gone@example.com')
    assert client.delete(f'/auth/users/{uid}', headers=headers).status_code == 204
    assert login(client, 'gone@example.com').status_code == 401

def test_admin_cannot_delete_themselves(client):
    assert_contract(client.delete('/auth/users/1', headers=admin_header()),
                    AUTH['delete_user']['self_delete'])

def test_delete_unknown_user(client):
    assert_contract(client.delete('/auth/users/9999', headers=admin_header()),
                    AUTH['delete_user']['not_found'])

def test_delete_user_requires_admin(client):
    assert_contract(client.delete('/auth/users/1', headers=auth_header()),
                    AUTH['delete_user']['forbidden'])

def test_the_last_admin_cannot_be_removed(client, monkeypatch):
    """Reachable when the caller isn't identified — i.e. a DEBUG dev session,
    where `require_admin` is bypassed and the self-guard has nobody to compare
    against. It is the only thing standing between dev and an admin-less DB."""
    admin_header()                       # user 1 is now the sole admin
    monkeypatch.setattr(Config, 'DEBUG', True)
    assert_contract(client.delete('/auth/users/1'), AUTH['delete_user']['last_admin'])
    assert_contract(client.patch('/auth/users/1', json={'is_admin': False}),
                    AUTH['update_user']['last_admin'])
    assert _is_admin('__auth_fixture__@test')


# GET/DELETE /auth/invitations

def test_list_invitations_shows_only_pending_ones(client):
    headers = admin_header()
    make_invite(client, 'waiting@example.com')
    _make_user(client, 'used@example.com')          # its invitation is consumed
    r = client.get('/auth/invitations', headers=headers)
    assert_contract(r, AUTH['list_invitations']['success'])
    emails = {i['email'] for i in r.get_json()['invitations']}
    assert emails == {'waiting@example.com'}
    assert 'invite=' in r.get_json()['invitations'][0]['invite_url']

def test_list_invitations_requires_admin(client):
    assert_contract(client.get('/auth/invitations', headers=auth_header()),
                    AUTH['list_invitations']['forbidden'])

def test_revoking_an_invitation_kills_the_registration(client):
    headers = admin_header()
    token = make_invite(client, 'nope@example.com')
    r = client.delete(f'/auth/invitations/{token}', headers=headers)
    assert_contract(r, AUTH['revoke_invitation']['success'])
    assert_contract(register(client, email='nope@example.com', invite_token=token),
                    AUTH['register']['invalid_invite'])
    # Idempotent: revoking again is not an error.
    assert client.delete(f'/auth/invitations/{token}', headers=headers).status_code == 204

def test_revoke_invitation_requires_admin(client):
    assert_contract(client.delete('/auth/invitations/whatever', headers=auth_header()),
                    AUTH['revoke_invitation']['forbidden'])
