"""The question an appearance asks: what makes two appearances one question, and
what a correction changes."""
import pytest

import corrections
import catalog_state as state
from igdb import window_around
from models import Episode, GameMention, PodcastGame
from questions import question_for
from utils import make_slug

_2024_MAR, _2024_NOV, _2025_JAN = 1_710_000_000, 1_731_000_000, 1_736_000_000


def _ask(name, pub_ts=_2024_MAR, podcast_id='silence-on-joue'):
    episode = Episode(title='t', slug=f'g{pub_ts}', audio_url=None, pub_ts=pub_ts,
                      image_url=None, description=None, chapters=[], games=[],
                      podcast_id=podcast_id)
    return question_for(PodcastGame(make_slug(name), name), episode)


@pytest.fixture(autouse=True)
def no_corrections(tmp_corrections):
    yield


def test_a_news_show_asks_one_question_per_name_and_year():
    assert _ask('Hades II', _2024_MAR).key == _ask('Hades II', _2024_NOV).key
    assert _ask('Hades II', _2024_MAR).key != _ask('Hades II', _2025_JAN).key
    assert _ask('Hades II').key != _ask('Hades II', podcast_id='fin-du-game').key


def test_its_evidence_is_dated_by_the_episode():
    # A review of a new release: the game came out shortly before the episode,
    # however many older namesakes IGDB lists.
    question = _ask('Hades II', _2024_NOV)
    assert (question.aired, question.window) == (_2024_NOV, window_around(_2024_NOV))


def test_a_question_is_judged_as_of_its_first_airing():
    from feeds import build_indexes
    episodes = [Episode(title='«Hades II»', slug=f'g{ts}', audio_url=None, pub_ts=ts,
                        image_url=None, description=None, chapters=[],
                        games=[GameMention('Hades II', None, 0)], podcast_id='silence-on-joue')
                for ts in (_2024_NOV, _2024_MAR)]
    _, state.game_index = build_indexes(episodes)
    (question,) = state.asked().values()
    assert question.aired == _2024_MAR


def test_a_retrospective_show_asks_one_undated_question_whatever_the_year():
    old = _ask('Chrono Trigger', _2024_MAR, 'fin-du-game')
    assert old == _ask('Chrono Trigger', _2025_JAN, 'fin-du-game')
    assert (old.window, old.aired) == (None, None)


def test_a_pin_is_the_question_and_its_answer():
    corrections.upsert('Chrono Trigger', igdb_id=42)
    question = _ask('Chrono Trigger')
    assert (question.kind, question.key, question.pin) == ('pin', 'pin|42', 42)


def test_a_curated_search_is_its_own_question(tmp_corrections):
    tmp_corrections.write_text('{"corrections": [{"podcast_name": "Hades 2", '
                               '"search_name": "Hades II"}]}', encoding='utf-8')
    corrections.load()
    question = _ask('Hades 2')
    assert (question.kind, question.query) == ('search', 'Hades II')
    assert question.key == 'search|hades-ii|2024'


def test_a_curated_day_narrows_the_window(tmp_corrections):
    tmp_corrections.write_text('{"corrections": [{"podcast_name": "Silent Hill 2", '
                               '"search_name": "Silent Hill 2", "hint_date": "2024-10-08"}]}',
                               encoding='utf-8')
    corrections.load()
    question = _ask('Silent Hill 2', 1_728_345_600 + 3600)    # published that day
    assert question.key == 'search|silent-hill-2|2024-10-08'
    assert question.window == window_around(1_728_345_600)


def test_a_display_name_changes_no_question():
    before = _ask('Chrono Trigger')
    corrections.upsert('Chrono Trigger', display_name='Chrono Trigger (SNES)')
    assert _ask('Chrono Trigger') == before
