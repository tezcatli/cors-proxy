import json
from types import SimpleNamespace

import pytest

import spec

EP = SimpleNamespace(slug='g1', title='Control Resonant Rewards Your Patience', podcast_id='the-besties')
CR = {'id': 1, 'name': 'Control Resonant', 'slug': 'control-resonant', 'released': '2026'}


@pytest.fixture(autouse=True)
def tmp_file(tmp_path, monkeypatch):
    path = tmp_path / 'spec.json'
    path.write_text(json.dumps({'games': []}), encoding='utf-8')
    monkeypatch.setattr(spec, 'PATH', path)


def test_a_game_s_level_and_entry_are_decided_separately():
    spec.update(EP, 'Control Resonant', level='consacré')
    spec.update(EP, 'Control Resonant', igdb=CR)
    [g] = spec.load()
    assert (g['level'], g['igdb']['id'], g['added']) == ('consacré', 1, False)


def test_a_game_can_be_absent_from_igdb_or_added_by_hand():
    spec.update(EP, 'Some Indie', added=True, level='évoqué', igdb='absent')
    assert spec.for_episode('g1')['Some Indie']['igdb'] == 'absent'
    spec.remove(EP, 'Some Indie')
    assert spec.load() == []


@pytest.mark.parametrize('fields', [{'level': 'bof'}, {'igdb': 'nope'}, {'igdb': {'name': 'no id'}}])
def test_nonsense_is_refused(fields):
    with pytest.raises(ValueError):
        spec.update(EP, 'X', **fields)
