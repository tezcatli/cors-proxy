import sys
from types import SimpleNamespace

sys.path.insert(0, '/backend')

import scope
from measure import outcomes, summary


def sec(game, minutes):
    return {'game': game, 'ad': False, 'start': 0, 'end': minutes * 60}


def test_a_test_is_five_minutes_long_unless_the_title_names_it():
    ep = SimpleNamespace(podcast_id='silence-on-joue', proposed=[SimpleNamespace(name='Sonic 4', read=False)])
    ok = scope.in_scope(ep, [sec('Sonic 4', 1), sec('Hack 95', 2), sec('Kirby Air Riders', 25)])
    assert (ok('Sonic 4'), ok('Hack 95'), ok('Kirby Air Riders'), ok('Unheard')) == (True, False, True, False)


def test_a_short_test_is_out_of_scope_neither_expected_nor_wrong():
    rows = [{'game': 'Hack 95', 'shown': None, 'spec': {'test': True, 'igdb': None}}]
    [c] = outcomes(rows, lambda g: False)
    assert c['outcome'] == 'hors champ' and summary([c])['expected'] == 0


def test_a_test_added_by_hand_is_always_expected():
    rows = [{'game': 'Metal Gear Solid 4', 'shown': None, 'spec': {'test': True, 'igdb': None, 'added': True}}]
    assert [c['outcome'] for c in outcomes(rows, lambda g: False)] == ['manquant']
