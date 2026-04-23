import os
import tempfile

# Set env vars before ANY app module is imported so Config computes test values.
os.environ['DEBUG']          = 'false'
os.environ['JWT_SECRET']     = 'test-jwt-secret-long-enough-for-hs256'
os.environ['ADMIN_KEY']      = 'test-admin-key'
os.environ['RAWG_KEY']       = 'test-rawg-key'
os.environ['RESET_BASE_URL'] = 'http://testserver'
os.environ['SMTP_HOST']      = ''

import db as _db
_db.DB_PATH = os.path.join(tempfile.mkdtemp(), 'test.db')

import pytest
from app import create_app


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
            DELETE FROM rawg_cache;
            DELETE FROM reset_tokens;
            DELETE FROM invitations;
            DELETE FROM users;
        """)
