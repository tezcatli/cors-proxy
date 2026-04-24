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
    r = spa_client.get('/silence/')
    assert r.status_code == 200
    assert b'id="app"' in r.data


def test_deep_link_falls_back_to_index(spa_client):
    r = spa_client.get('/silence/game/zelda')
    assert r.status_code == 200
    assert b'id="app"' in r.data


def test_nested_unknown_path_falls_back_to_index(spa_client):
    r = spa_client.get('/silence/some/deep/path')
    assert r.status_code == 200
    assert b'id="app"' in r.data


def test_real_asset_served_directly(spa_client):
    r = spa_client.get('/silence/assets/main.js')
    assert r.status_code == 200
    assert b'const app = 1' in r.data


def test_silence_without_slash_redirects(spa_client):
    r = spa_client.get('/silence')
    assert r.status_code in (301, 302)
    assert r.headers['Location'].endswith('/silence/')
