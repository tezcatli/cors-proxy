import sys
sys.path.insert(0, '/backend')

from candidates import group


def test_one_game_named_differently_is_one_candidate():
    out = group([('Tinykin', 'titre'), ('Tinikin', 'chapitre'), ('Astrobot', 'titre'),
                 ('Astro Bot', 'lecture'), ('Splatoon 3', 'titre')])
    assert [(c['game'], c['sources']) for c in out] == [
        ('Tinykin', ['titre', 'chapitre']), ('Astrobot', ['titre', 'lecture']), ('Splatoon 3', ['titre'])]


def test_different_games_stay_apart():
    out = group([('Gears of War 2', 'titre'), ('Gears of War', 'lecture'), ('Hades', 'lecture'), ('Hades II', 'lecture')])
    assert [c['game'] for c in out] == ['Gears of War 2', 'Gears of War', 'Hades', 'Hades II']


from candidates import _game_chapters


def test_marked_chapters_are_trusted_unmarked_ones_filtered_by_name():
    marked = [{'title': 'Introduction', 'game': None}, {'title': 'Splatoon 3', 'game': 'Splatoon 3'}]
    assert [c['title'] for c in _game_chapters(marked)] == ['Splatoon 3']
    unmarked = [{'title': t, 'game': None} for t in
                ('Intro', 'Les news', 'Le com des coms', 'Super Mario RPG', 'La minute culturelle',
                 'Et quand vous ne jouez pas, vous faites quoi ?', 'Karmazoo')]
    assert [c['title'] for c in _game_chapters(unmarked)] == ['Super Mario RPG', 'Karmazoo']
