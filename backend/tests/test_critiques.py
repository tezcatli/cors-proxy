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


def test_the_title_s_game_stands_unless_heard_only_in_the_news():
    sections = [section('Nine Lives', 'news', 0, 7), section('Red Steel 2', 'review', 420, 9)]
    assert names(critiques.select(SOJ, episode('Red Steel 2', 'Nine Lives', 'Sonic 4'), sections)) == [
        'Red Steel 2', 'Sonic 4']   # Sonic 4: no section, silence is no veto


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


def test_a_palmares_format_is_known_by_its_title():
    assert critiques.palmares(TC, 'Triple Click Picks: The Games You Should Play (2026 Edition)')
    assert critiques.palmares(SOJ, "S19E19 - Les «Silences d'or» 2025")
    assert not critiques.palmares(PODCAST_BY_ID['the-besties'], 'Mina the Hollower Is GOTY Quality')


def test_sequels_are_other_games():
    assert critiques.same('Astrobot', 'Astro Bot') and not critiques.same('Gears of War 2', 'Gears of War')
