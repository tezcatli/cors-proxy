"""The rules of `critiques.select`, one by one; `test_reference.py` replays the
curator's judgments on real readings."""
from models import Chapter, Episode, GameMention
from podcasts import PODCAST_BY_ID

import critiques

SOJ, FDG, TC = (PODCAST_BY_ID[i] for i in ('silence-on-joue', 'fin-du-game', 'triple-click'))


def section(game, kind, start, minutes):
    return {'title': game or 'x', 'game': game, 'kind': kind, 'ad': False,
            'start': start, 'end': start + minutes * 60, 'opinion': None}


def episode(*title_games, read=(), chapters=()):
    games = [GameMention(n, None, 0) for n in title_games] + [GameMention(n, None, 0, read=True) for n in read]
    ep = Episode(title='t', slug='g', audio_url=None, pub_ts=None, image_url=None, description='',
                 chapters=list(chapters), games=games, podcast_id='silence-on-joue')
    ep.proposed = [m for m in games if not m.read]
    return ep


def names(tests):
    return [t.name for t in tests]


def test_a_game_the_reading_found_is_a_test_from_five_minutes_on():
    sections = [section('Long', 'review', 0, 6), section('Short', 'review', 400, 3)]
    assert names(critiques.select(SOJ, episode(read=['Long', 'Short']), sections)) == ['Long']


def test_a_palmares_entry_is_no_test_even_long():
    sections = [section('Ranked', 'ranking', 0, 10), section('Both', 'ranking', 600, 2), section('Both', 'review', 900, 6)]
    assert names(critiques.select(SOJ, episode(read=['Ranked', 'Both']), sections)) == ['Both']


def test_the_title_s_game_is_one_when_found_unless_heard_only_in_the_news():
    sections = [section('Nine Lives', 'news', 0, 7), section('Red Steel 2', 'review', 420, 9)]
    assert names(critiques.select(SOJ, episode('Red Steel 2', 'Nine Lives', 'Le 500e épisode'), sections)) == [
        'Red Steel 2']   # a title that names no game the reading finds is no test


def test_names_are_one_game_by_their_catalog_page_not_their_words():
    sections = [section('Wolfenstein: The Old Blood', 'review', 0, 20), section('Broken Sword 5', 'review', 1200, 14),
                section('Broken Age', 'review', 2100, 20)]
    pages = {'Wolfenstein': 1, 'Wolfenstein: The Old Blood': 1, 'Broken Sword 5': 2, 'Broken Age': 3}
    tests = critiques.select(SOJ, episode('Wolfenstein', 'Broken Age'), sections, page=pages.get)
    assert sorted(names(tests)) == ['Broken Age', 'Broken Sword 5', 'Wolfenstein']


def test_without_an_answer_the_words_decide_but_a_sequel_is_another_game():
    sections = [section('Pokémon X et Pokémon Y', 'review', 0, 20), section('Assassin’s Creed II', 'review', 1200, 10)]
    tests = critiques.select(SOJ, episode('Pokémon X & Y', 'Assassin’s Creed'), sections)
    assert names(tests) == ['Pokémon X & Y', 'Assassin’s Creed II']


def test_a_game_is_never_two_pages():
    sections = [section('Tomb Raider', 'review', 0, 20), section('Tomb Raider II', 'review', 1200, 16)]
    pages = {"L'histoire de Tomb Raider": None, 'Tomb Raider': 1, 'Tomb Raider II': 2}
    tests = critiques.select(SOJ, episode("L'histoire de Tomb Raider"), sections, page=pages.get)
    assert sorted(names(tests)) == ["L'histoire de Tomb Raider", 'Tomb Raider II']


def test_for_the_llm_read_shows_every_game_is_the_reading_s():
    sections = [section('Short', 'review', 0, 2)]
    assert critiques.select(TC, episode('Short'), sections) == []


def test_a_one_game_show_holds_the_title_s_game_over_the_whole_episode():
    ep = episode('Dragon Age: Origins', read=['Dragon Age II'], chapters=[Chapter('0:25', 25, 'Intro')])
    sections = [section('Dragon Age: Origins', 'review', 236, 30), section('Dragon Age II', 'review', 6311, 6)]
    [t] = critiques.select(FDG, ep, sections)
    assert (t.name, t.timestamp_seconds) == ('Dragon Age: Origins', 25)


def test_a_test_starts_at_its_critique_not_a_teaser():
    sections = [section('TLOU2', 'impressions', 0, 2), section(None, None, 120, 1),
                section('TLOU2', 'review', 162, 31), section('Other', 'review', 2045, 6)]
    [t, _] = critiques.select(SOJ, episode(read=['TLOU2', 'Other']), sections)
    assert t.timestamp_seconds == 162


def test_a_test_lasts_over_the_sections_on_its_game_after_its_critique_ads_aside():
    ad = {**section(None, None, 2022, 2), 'ad': True}
    sections = [section('TLOU2', 'impressions', 0, 2), section(None, None, 120, 1),
                section('TLOU2', 'review', 162, 31), ad, section('TLOU2', 'discussion', 2142, 5),
                section('Other', 'review', 2442, 6), section('TLOU2', 'news', 2802, 1)]
    [t, o] = critiques.select(SOJ, episode(read=['TLOU2', 'Other']), sections)
    assert (t.timestamp_seconds, t.duration_seconds) == (162, 2142 + 300 - 162)
    assert o.duration_seconds == 360


def test_a_one_game_show_s_test_lasts_to_the_end_of_the_reading():
    ep = episode('Astrobot', chapters=[Chapter('0:25', 25, 'Intro')])
    [t] = critiques.select(FDG, ep, [section('Astrobot', 'review', 236, 30)])
    assert t.duration_seconds == 236 + 1800 - 25


def test_a_palmares_format_is_known_by_its_title():
    assert critiques.palmares(TC, 'Triple Click Picks: The Games You Should Play (2026 Edition)')
    assert critiques.palmares(SOJ, "S19E19 - Les «Silences d'or» 2025")
    assert not critiques.palmares(PODCAST_BY_ID['the-besties'], 'Mina the Hollower Is GOTY Quality')


def test_sequels_are_other_games():
    assert critiques.same('Astrobot', 'Astro Bot') and not critiques.same('Gears of War 2', 'Gears of War')
