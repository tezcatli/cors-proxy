"""The curator's judgments, replayed: the acceptance test of the catalog's rules
(`critiques.py`), defined in the lab (`lab/`) and ported.

`fixtures/reference.json` (`lab/export_reference.py`) holds the 102 judged
episodes — what the catalog build is given (title, the games the title proposes,
the episode's own chapters, its reading's sections, the catalog page each
name's answer is on) and the judgments: which
games are tests, which aren't. Through the app's own steps they must give no
false test, at least 90 % of the tests, and exactly the tests of the chain that
was measured — a change of rules is made in the lab, and changes this file.
"""
import json
import pathlib
from unittest.mock import patch

import pytest

import critiques
import feeds
from models import Chapter, Episode, GameMention
from podcasts import PODCAST_BY_ID
from rss import is_game_catalog_excluded

_DATA = json.loads((pathlib.Path(__file__).parent / 'fixtures' / 'reference.json').read_text())['episodes']


def _tests(e: dict) -> list[GameMention]:
    """The episode's tests, through the catalog build's steps."""
    ep = Episode(title=e['title'], slug=e['guid'], audio_url=None, pub_ts=e['pub_ts'], image_url=None,
                 description='',
                 chapters=[Chapter(c['timestamp'], c['seconds'], c['title'], c['game']) for c in e['chapters']],
                 games=[GameMention(m['name'], m['timestamp'], m['seconds']) for m in e['proposed']],
                 podcast_id=e['podcast'])
    readings = {e['guid']: [dict(s, opinion=None) for s in e['sections']]} if e['sections'] else {}
    episodes = feeds._apply_llm_games([ep], readings)
    with patch('feeds._page', lambda name, episode: e['pages'].get(name)):
        feeds._apply_readings(episodes, readings)
    if not episodes or is_game_catalog_excluded(ep.title) or critiques.palmares(PODCAST_BY_ID[ep.podcast_id],
                                                                              ep.title):
        return []
    return episodes[0].games


@pytest.fixture(scope='module')
def results():
    return [(e, _tests(e)) for e in _DATA]


def test_the_rules_give_exactly_the_measured_chain(results):
    for e, tests in results:
        got = sorted((t.name, t.timestamp_seconds) for t in tests)
        assert got == sorted((t['game'], t['start']) for t in e['chain']), e['title']


def test_no_game_judged_not_a_test_is_listed(results):
    false = [(e['title'], t.name) for e, tests in results for t in tests
             if any(critiques.same(t.name, n) for n in e['not_tests'])
             and not any(critiques.same(t.name, n) for n in e['tests'])]
    assert false == []


def test_nine_tests_in_ten_are_found(results):
    expected = [(n, tests) for e, tests in results for n in e['tests']]
    found = sum(any(critiques.same(n, t.name) for t in tests) for n, tests in expected)
    # Names only: a few tests judged under another spelling (« Sonic 4 » for
    # « Sonic the Hedgehog 4 ») count as missed here — the lab matches them by
    # their IGDB entry too.
    assert found / len(expected) >= 0.9, f'{found} / {len(expected)}'
