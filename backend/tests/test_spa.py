import pathlib
import pytest
from app import create_app


@pytest.fixture
def spa_client(tmp_path, monkeypatch):
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html><body id="app"></body></html>')
    assets = dist / 'assets'
    assets.mkdir()
    (assets / 'main.js').write_text('const app = 1')

    monkeypatch.setattr('config.Config.DEBUG', True)
    app = create_app()
    app.config['TESTING'] = True
    app.static_folder = str(dist)

    return app.test_client()


def test_root_serves_index(spa_client):
    r = spa_client.get('/')
    assert r.status_code == 200
    assert b'id="app"' in r.data


def test_deep_link_falls_back_to_index(spa_client):
    r = spa_client.get('/game/zelda')
    assert r.status_code == 200
    assert b'id="app"' in r.data


def test_real_asset_served_directly(spa_client):
    r = spa_client.get('/assets/main.js')
    assert r.status_code == 200
    assert b'const app = 1' in r.data


@pytest.mark.parametrize('path', ['/auth/login', '/games/', '/healthz'])
def test_api_routes_are_not_swallowed_by_the_spa_catch_all(spa_client, path):
    """The SPA is a root catch-all, so a routing regression would answer API
    calls with index.html — a 200 of the wrong thing, which is far worse to
    debug than a clean error. Whatever these return, it must not be the SPA."""
    r = spa_client.get(path)
    assert b'id="app"' not in r.data
