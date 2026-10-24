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
os.environ['TESTING']        = 'true'

import db as _db
_db.DB_PATH = os.path.join(tempfile.mkdtemp(), 'test.db')

import datetime
import jwt
import pytest
from unittest.mock import patch
from app import create_app
from config import Config
import catalog_state as _state
import worker as _worker
_worker.inline = True      # jobs run at once, in the test's thread
import feeds as _feeds
import games as _games
from podcasts import PODCAST_BY_ID as _PODCAST_BY_ID


def cache_entry(key, igdb_id, igdb_slug, name, data=None, is_child=False,
                at='2999-01-01T00:00:00', enriched=True, method=None):
    """An IgdbEntry: an answer, joined with its game when it has one. `at` stamps
    both (the answer's and its game's freshness). `key` is replaced by the real
    question key in `set_cache`."""
    from models import IgdbEntry, IgdbGame, Resolution
    game = (IgdbGame(igdb_id, igdb_slug, name, data or {}, at, enriched)
            if igdb_id is not None else None)
    return IgdbEntry(Resolution(key, igdb_id, is_child, at, method), game)


def set_cache(entries):
    """Load `{podcast_slug: IgdbEntry}` into the two IGDB stores: each entry
    answers the question its appearance asks, so the catalog must be loaded."""
    import dataclasses
    from questions import question_for
    asking = {a.podcast_slug: question_for(g, a.episode).key
              for g in _state.game_index.values() for a in g.appearances}
    _state.resolutions = {asking[slug]: dataclasses.replace(e.resolution, question=asking[slug])
                          for slug, e in entries.items()}
    _state.games       = {e.game.igdb_id: e.game for e in entries.values() if e.game}


def auth_header(email='user@example.com'):
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    token = jwt.encode(
        {'sub': '1', 'email': email, 'iat': now,
         'exp': now + datetime.timedelta(hours=1)},
        Config.JWT_SECRET, algorithm='HS256',
    )
    return {'Authorization': f'Bearer {token}'}


def admin_header(email='admin@example.com'):
    """Header for the same fixture user, promoted to admin. `require_admin` reads
    the flag from the DB (not the token), so the promotion has to be persisted."""
    with _db.get_db() as conn:
        conn.execute('UPDATE users SET is_admin = 1 WHERE id = 1')
    return auth_header(email)


@pytest.fixture(scope='session')
def app():
    application = create_app(testing=True)
    application.config['TESTING'] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def single_podcast():
    """Default tests to a single-feed registry so the blanket `http.get` mock
    (one static response) isn't fetched once per registered podcast. Multi-feed
    tests opt in by re-patching `feeds.PODCASTS` within the test."""
    saved = _feeds.PODCASTS
    _feeds.PODCASTS = [_PODCAST_BY_ID['silence-on-joue']]
    yield
    _feeds.PODCASTS = saved
    _feeds._feed_meta     = {}
    _feeds._feed_episodes = {}


@pytest.fixture
def tmp_corrections(tmp_path, monkeypatch):
    """Point corrections.json at an empty temp file, so tests that exercise the
    write path can't touch the repo's real (git-tracked) corrections."""
    import json as _json
    import corrections as _corr
    path = tmp_path / 'corrections.json'
    path.write_text(_json.dumps({'corrections': []}), encoding='utf-8')
    monkeypatch.setattr(_corr, '_PATH', path)
    _corr.load()
    yield path
    monkeypatch.undo()
    _corr.load()          # restore the real file into memory for other tests


@pytest.fixture(autouse=True)
def no_unsearched_evidence():
    """IGDB's other names and release dates (`resolver._unsearched`) find nothing
    unless a test says otherwise: the search mocks stand alone."""
    with patch('resolver.alternative_name_ids', return_value=set()), \
         patch('resolver.releases', return_value=[]):
        yield


@pytest.fixture(autouse=True)
def clean_db():
    # Seed the user that auth_header()'s token (sub='1') refers to, so the
    # require_auth user-existence check passes for authenticated tests.
    with _db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (1, '__auth_fixture__@test', 'x')"
        )
    yield
    with _db.get_db() as conn:
        conn.executescript("""
            DELETE FROM resolutions;
            DELETE FROM igdb_games;
            DELETE FROM llm_cache;
            DELETE FROM transcripts;
            DELETE FROM reset_tokens;
            DELETE FROM invitations;
            DELETE FROM users;
        """)
    _state.episodes      = []
    _state.episode_index = {}
    _state.game_index    = {}
    _state.resolutions   = {}
    _state.games         = {}
    _state.cached_at     = None
    # Response caches are keyed by a version that is monotonic across the whole
    # pytest session, so they must be dropped alongside the state they derive from.
    _games._catalog_cache   = None
    _games._feed_cache      = None
