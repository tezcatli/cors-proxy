import json
from types import SimpleNamespace

import pytest

import spec

CR = {'id': 1, 'name': 'Control Resonant'}
EP = SimpleNamespace(slug='g1', title='Control Resonant Rewards Your Patience', podcast_id='the-besties')


@pytest.fixture(autouse=True)
def tmp_file(tmp_path, monkeypatch):
    path = tmp_path / 'spec.json'
    path.write_text(json.dumps({'games': []}), encoding='utf-8')
    monkeypatch.setattr(spec, 'PATH', path)


def test_whether_it_is_a_test_is_recorded_and_a_missing_one_where_it_was_added():
    spec.update(EP, 'Control Resonant', test=True)
    spec.update(EP, 'Some Indie', added=True, test=True, start=1800)
    assert {g['game']: (g['test'], g['added'], g.get('start')) for g in spec.load()} == {
        'Control Resonant': (True, False, None), 'Some Indie': (True, True, 1800)}
    spec.remove(EP, 'Some Indie')
    assert [g['game'] for g in spec.load()] == ['Control Resonant']


@pytest.mark.parametrize('fields', [{'test': 'bof'}, {'test': 1}, {'igdb': 'nope'}, {'igdb': {'name': 'no id'}}])
def test_nonsense_is_refused(fields):
    with pytest.raises(ValueError):
        spec.update(EP, 'X', **fields)


def test_validating_accepts_what_is_not_judged_on_its_proposed_entry_and_keeps_what_is():
    spec.update(EP, 'Gears of War: E-Day', test=False)
    spec.update(EP, 'Hades', igdb='absent')
    spec.validate(EP, {'Control Resonant': CR, 'Gears of War: E-Day': None, 'Hades': CR}, 'current')
    assert {g['game']: (g['test'], g['igdb']) for g in spec.load()} == {
        'Control Resonant': (True, CR), 'Gears of War: E-Day': (False, None), 'Hades': (True, 'absent')}
    assert spec.validated('g1')['variant'] == 'current'


def test_a_spec_without_episodes_still_reads(tmp_file):
    assert spec.validated('g1') is None and spec.load() == []


def test_a_test_added_by_hand_can_be_renamed_but_not_onto_another():
    spec.update(EP, 'Les gros machins', added=True, test=True)
    spec.update(EP, 'Hades', test=True)
    spec.rename(EP, 'Les gros machins', 'Hollow Knight')
    assert sorted(g['game'] for g in spec.load()) == ['Hades', 'Hollow Knight']
    with pytest.raises(ValueError):
        spec.rename(EP, 'Hollow Knight', 'Hades')
