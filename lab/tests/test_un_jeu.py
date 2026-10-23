import sys
from types import SimpleNamespace

sys.path.insert(0, '/backend')

from variants import current, un_jeu

DAO = {'id': 76, 'name': 'Dragon Age: Origins'}


def mention(name, read=False):
    return SimpleNamespace(name=name, read=read)


def a_test(game, igdb=None):
    return {'game': game, 'start': 236, 'end': 6170, 'minutes': 97, 'verdict': 'positive', 'igdb': igdb}


CHAPTERS = [{'start': 0, 'end': 210, 'title': 'Intro'}, {'start': 210, 'end': 7336, 'title': 'Le jeu'}]


def episode(podcast, *names):
    return SimpleNamespace(podcast_id=podcast, proposed=[mention(n) for n in names], games=[])


def test_a_one_game_show_proposes_the_title_s_game_only(monkeypatch):
    monkeypatch.setattr(current, 'run', lambda ep: {'chapters': CHAPTERS, 'tests': [
        a_test('Dragon Age: Origins', DAO), a_test('Dragon Age II'), a_test("Baldur's Gate 3")]})
    [t] = un_jeu.run(episode('fin-du-game', 'Dragon Age: Origins'))['tests']
    assert (t['game'], t['igdb'], t['verdict']) == ('Dragon Age: Origins', DAO, 'positive')
    assert (t['start'], t['end'], t['minutes']) == (0, 7336, 122)   # the whole episode


def test_unconfirmed_it_is_the_whole_episode_without_an_entry(monkeypatch):
    monkeypatch.setattr(current, 'run', lambda ep: {'chapters': CHAPTERS, 'tests': []})
    [t] = un_jeu.run(episode('fin-du-game', 'Dredge'))['tests']
    assert (t['game'], t['start'], t['end'], t['igdb']) == ('Dredge', 0, 7336, None)


def test_other_shows_are_as_current(monkeypatch):
    out = {'chapters': CHAPTERS, 'tests': [a_test('Splatoon 3'), a_test('Tinykin')]}
    monkeypatch.setattr(current, 'run', lambda ep: out)
    assert un_jeu.run(episode('silence-on-joue', 'Splatoon 3')) == out


from variants import sans_palmares


def section(game, kind):
    return {'game': game, 'kind': kind, 'ad': False}


def test_a_game_only_in_a_ranking_is_no_test(monkeypatch):
    out = {'chapters': CHAPTERS, 'tests': [a_test('Hades II'), a_test('Blue Prince')]}
    monkeypatch.setattr(un_jeu, 'run', lambda ep: out)
    monkeypatch.setattr(current, '_reading', lambda ep: [
        section('Hades II', 'ranking'), section('Blue Prince', 'ranking'), section('Blue Prince', 'review')])
    assert [t['game'] for t in sans_palmares.run(episode('silence-on-joue'))['tests']] == ['Blue Prince']


from variants import sans_bande_annonce


def test_a_trailer_episode_holds_no_test(monkeypatch):
    monkeypatch.setattr(sans_palmares, 'run', lambda ep: {'chapters': CHAPTERS, 'tests': [a_test('Les Sims')]})
    trailer = SimpleNamespace(podcast_id='silence-on-joue', title='Sur quel jeu avez-vous le plus triché ? - Bande-annonce S20E07')
    review = SimpleNamespace(podcast_id='silence-on-joue', title='S19E04 - «Baby Steps»')
    assert sans_bande_annonce.run(trailer)['tests'] == []
    assert [t['game'] for t in sans_bande_annonce.run(review)['tests']] == ['Les Sims']
