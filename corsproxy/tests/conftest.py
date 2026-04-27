import os
import tempfile

# Set env vars before ANY app module is imported so Config computes test values.
os.environ['DEBUG']          = 'false'
os.environ['JWT_SECRET']     = 'test-jwt-secret-long-enough-for-hs256'
os.environ['ADMIN_KEY']      = 'test-admin-key'
os.environ['IGDB_CLIENT_ID']     = 'test-igdb-client-id'
os.environ['IGDB_CLIENT_SECRET'] = 'test-igdb-client-secret'
os.environ['RESET_BASE_URL'] = 'http://testserver'
os.environ['SMTP_HOST']      = ''

import db as _db
_db.DB_PATH = os.path.join(tempfile.mkdtemp(), 'test.db')

import datetime
import jwt
import pytest
from app import create_app
from config import Config


def auth_header(email='user@example.com'):
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    token = jwt.encode(
        {'sub': '1', 'email': email, 'iat': now,
         'exp': now + datetime.timedelta(hours=1)},
        Config.JWT_SECRET, algorithm='HS256',
    )
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='session')
def app():
    application = create_app()
    application.config['TESTING'] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db():
    yield
    with _db.get_db() as conn:
        conn.executescript("""
            DELETE FROM igdb_cache;
            DELETE FROM games_cache;
            DELETE FROM reset_tokens;
            DELETE FROM invitations;
            DELETE FROM users;
        """)
