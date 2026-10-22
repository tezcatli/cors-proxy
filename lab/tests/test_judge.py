import sys
sys.path.insert(0, '/backend')

from judge import rows, same


def test_one_game_named_differently_is_one_game():
    assert same('Tinykin', 'Tinikin') and same('Astrobot', 'Astro Bot')


def test_sequels_stay_apart():
    assert not same('Gears of War 2', 'Gears of War') and not same('Hades', 'Hades II')


def test_a_judgment_is_found_again_under_another_spelling_and_kept_when_not_referenced():
    tests = [{'game': 'Tinikin'}, {'game': 'Splatoon 3'}]
    judged = {'Tinykin': {'test': True}, 'GTA VI': {'test': False}}
    assert [(r['game'], r['shown'] is not None, (r['spec'] or {}).get('test')) for r in rows(tests, judged)] == [
        ('Tinykin', True, True), ('Splatoon 3', True, None), ('GTA VI', False, False)]


from judge import status, timeline

CHAPTERS = [{'start': 0, 'end': 600, 'title': 'Intro'}, {'start': 600, 'end': 1800, 'title': 'Splatoon 3'},
            {'start': 1800, 'end': None, 'title': 'Conclusion'}]


def test_a_test_lies_in_the_chapter_it_starts_in_and_one_without_start_comes_first():
    rows = [{'game': 'Splatoon 3', 'shown': {'start': 640}, 'spec': None},
            {'game': 'Tinykin', 'shown': {'start': None}, 'spec': None},
            {'game': 'Added', 'shown': None, 'spec': {'test': True, 'start': 1800}}]
    groups = timeline(CHAPTERS, rows)
    assert [(g['title'], [r['game'] for r in g['rows']]) for g in groups] == [
        (None, ['Tinykin']), ('Intro', []), ('Splatoon 3', ['Splatoon 3']), ('Conclusion', ['Added'])]


def test_an_episode_is_to_review_when_a_variant_references_a_test_nobody_judged():
    judged = [{'game': 'A', 'shown': {'start': 0}, 'spec': {'test': False}}]
    new = judged + [{'game': 'B', 'shown': {'start': 0}, 'spec': None}]
    assert (status(judged, False), status(judged, True), status(new, True)) == ('à juger', 'validé', 'à revoir')


def test_a_test_starting_seconds_before_its_chapter_lies_in_it():
    chapters = [{'start': 3460, 'end': 3758, 'title': 'Take Time'},
                {'start': 3758, 'end': 5592, 'title': 'Marvel Cosmic Invasion'},
                {'start': 5592, 'end': 5971, 'title': 'La minute culturelle'}]
    rows = [{'game': 'Marvel Cosmic Invasion', 'shown': {'start': 3735, 'end': 5584}, 'spec': None}]
    assert [(g['title'], [r['game'] for r in g['rows']], g['within']) for g in timeline(chapters, rows)] == [
        ('Take Time', [], []), ('Marvel Cosmic Invasion', ['Marvel Cosmic Invasion'], []), ('La minute culturelle', [], [])]


def test_a_test_over_the_whole_episode_lies_in_the_first_chapter_and_the_others_follow():
    rows = [{'game': 'Astro Bot', 'shown': {'start': 25, 'end': 5091}, 'spec': None}]
    chapters = [{'start': 25, 'end': 145, 'title': 'Présentation'}, {'start': 145, 'end': 1477, 'title': 'Genèse'},
                {'start': 1477, 'end': 5064, 'title': 'Critique'}, {'start': 5064, 'end': 5091, 'title': 'Merci'}]
    assert [(g['title'], len(g['rows']), g['within']) for g in timeline(chapters, rows)] == [
        ('Présentation', 1, []), ('Genèse', 0, ['Astro Bot']), ('Critique', 0, ['Astro Bot']), ('Merci', 0, ['Astro Bot'])]
