import json
from types import SimpleNamespace

import pytest

import judgments

EP = SimpleNamespace(slug='g1', title='Control Resonant Rewards Your Patience', podcast_id='the-besties')


@pytest.fixture(autouse=True)
def tmp_file(tmp_path, monkeypatch):
    path = tmp_path / 'judgments.json'
    path.write_text(json.dumps({'judgments': []}), encoding='utf-8')
    monkeypatch.setattr(judgments, 'PATH', path)
    return path


def test_a_judgment_is_recorded_then_replaced_then_withdrawn(tmp_file):
    judgments.judge(EP, 'A Normal Golf Game', 'évoqué', None)
    judgments.judge(EP, 'A Normal Golf Game', 'absent', None)
    assert [(j['game'], j['verdict']) for j in judgments.load()] == [('A Normal Golf Game', 'absent')]
    judgments.judge(EP, 'A Normal Golf Game', None, None)
    assert judgments.load() == []


def test_judgments_are_kept_sorted_for_a_reviewable_diff(tmp_file):
    judgments.judge(EP, 'Gears of War: E-DAY', 'consacré', 'gears-of-war-e-day')
    judgments.judge(EP, 'Control Resonant', 'consacré', 'control-resonant')
    assert [j['game'] for j in judgments.load()] == ['Control Resonant', 'Gears of War: E-DAY']
    assert judgments.for_episode('g1')['Control Resonant']['igdbSlug'] == 'control-resonant'


def test_an_unknown_verdict_is_refused():
    with pytest.raises(ValueError):
        judgments.judge(EP, 'X', 'bof', None)
