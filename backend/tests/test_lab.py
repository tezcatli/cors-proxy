"""The lab: the pipeline's view of an episode, and the curator's judgments."""
import json

import pytest

import lab
from conftest import admin_header, auth_header
from contract import assert_contract, CONTRACT

GAMES = CONTRACT['games']
from test_ingest import _ingest_all, besties, keys   # noqa: F401  (fixtures)


@pytest.fixture
def judgments(tmp_path, monkeypatch):
    path = tmp_path / 'judgments.json'
    path.write_text(json.dumps({'judgments': []}), encoding='utf-8')
    monkeypatch.setattr(lab, '_PATH', path)
    return path


def _view(client, slug='bes-control'):
    return client.get(f'/games/lab/episode?slug={slug}', headers=admin_header())


def test_an_episode_shows_what_the_pipeline_attaches_and_what_it_only_reads(
        client, keys, besties, judgments):
    _ingest_all()
    r = _view(client)
    assert_contract(r, GAMES['lab_episode']['success'])
    rows = {g['game']: g for g in r.get_json()['games']}
    assert rows['Control Resonant']['attached'] and rows['Control Resonant']['kind'] == 'review'
    assert rows['Control Resonant']['minutes'] == 27.0
    assert rows['Control Resonant']['source'] == 'lecture'
    assert not rows['A Normal Golf Game']['attached']            # read, a mention: not attached
    assert [g['game'] for g in r.get_json()['games']][:2] == ['Control Resonant', 'Gears of War: E-DAY']


def test_a_judgment_is_recorded_then_withdrawn(client, keys, besties, judgments):
    _ingest_all()
    body = {'episode': 'bes-control', 'game': 'A Normal Golf Game', 'verdict': 'évoqué'}
    r = client.put('/games/lab/judgments', json=body, headers=admin_header())
    assert_contract(r, GAMES['lab_judgments']['success'])
    assert {g['game']: g['judgment'] for g in r.get_json()['games']}['A Normal Golf Game'] == 'évoqué'
    saved = json.loads(judgments.read_text())['judgments']
    assert [(j['episode'], j['game'], j['verdict'], j['podcast']) for j in saved] == [
        ('bes-control', 'A Normal Golf Game', 'évoqué', 'the-besties')]
    client.put('/games/lab/judgments', json={**body, 'verdict': None}, headers=admin_header())
    assert json.loads(judgments.read_text())['judgments'] == []


def test_an_unknown_verdict_is_refused(client, keys, besties, judgments):
    _ingest_all()
    r = client.put('/games/lab/judgments', headers=admin_header(),
                   json={'episode': 'bes-control', 'game': 'X', 'verdict': 'bof'})
    assert r.status_code == 400


def test_the_lab_is_not_there_outside_dev(client, keys, besties, monkeypatch):
    _ingest_all()
    monkeypatch.setattr(lab, 'enabled', lambda: False)
    assert _view(client).status_code == 404


def test_the_lab_is_for_admins(client, keys, besties, judgments):
    _ingest_all()
    assert client.get('/games/lab/episode?slug=bes-control', headers=auth_header()).status_code == 403
