import sys
sys.path.insert(0, '/backend')

from measure import outcomes, summary

A = {'id': 1, 'name': 'A'}
B = {'id': 2, 'name': 'B'}


def row(game, shown=None, test=None, igdb=None):
    return {'game': game, 'shown': None if shown is False else {'start': 0, 'igdb': shown},
            'spec': None if test is None else {'test': test, 'igdb': igdb}}


def test_every_kind_of_case():
    rows = [row('right', A, True, A), row('other entry', A, True, B), row('none in igdb', None, True, 'absent'),
            row('not a test', A, False), row('missing', False, True, A), row('new', A),
            row('undecided', A, True), row('rightly left out', False, False)]
    assert [(c['game'], c['outcome']) for c in outcomes(rows)] == [
        ('right', 'juste'), ('other entry', 'mauvaise fiche'), ('none in igdb', 'juste'), ('not a test', 'faux'),
        ('missing', 'manquant'), ('new', 'à juger'), ('undecided', 'fiche indécise')]


def test_the_criterion_needs_no_false_test_no_wrong_entry_and_ninety_percent_found():
    ok = [{'outcome': 'juste'}] * 9 + [{'outcome': 'manquant'}]
    assert summary(ok)['met'] and summary(ok)['found'] == 0.9
    assert not summary(ok + [{'outcome': 'manquant'}])['met']
    assert not summary(ok + [{'outcome': 'faux'}])['met']
    assert not summary(ok + [{'outcome': 'mauvaise fiche'}])['met']


def test_a_known_limit_is_counted_apart_and_holds_nothing_back():
    rows = [{'game': 'Dark Souls', 'shown': {'start': 0, 'igdb': A}, 'spec': {'test': True, 'igdb': B, 'limit': 'why'}}]
    [c] = outcomes(rows)
    assert c['outcome'] == 'limite connue' and summary([c])['met']
