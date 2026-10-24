"""The LLM module and the LLM-assisted resolution. The model is always mocked:
`_llm_answers` stands in for OpenRouter, one JSON answer per call."""
import json
from unittest.mock import MagicMock, patch

import pytest

import catalog_state as state
import llm
import resolver
from config import Config
from igdb import IgdbResult


@pytest.fixture
def llm_on(monkeypatch, tmp_corrections):
    # tmp_corrections: the shipped corrections.json already pins some of these
    # names, and a correction outranks the LLM.
    monkeypatch.setattr(Config, 'OPENROUTER_API_KEY', 'test-key')


def _llm_answers(*answers):
    """A mock for `llm.http.post` returning these JSON objects in turn."""
    def reply(answer):
        r = MagicMock()
        r.raise_for_status.return_value = None
        r.json.return_value = {'choices': [{'message': {'content': json.dumps(answer)}}]}
        return r
    return patch('llm.http.post', side_effect=[reply(a) for a in answers])


# ── llm.ask ───────────────────────────────────────────────────────────────────

def test_off_without_a_key():
    with patch('llm.http.post') as post:
        assert llm.ask('t', 1, 'sys', {'x': 1}) is None
    post.assert_not_called()


def test_an_answer_is_asked_once_then_cached(llm_on):
    with _llm_answers({'ok': True}) as post:
        assert llm.ask('t', 1, 'sys', {'x': 1}) == {'ok': True}
        assert llm.ask('t', 1, 'sys', {'x': 1}) == {'ok': True}
    assert post.call_count == 1


def test_a_new_prompt_version_asks_again(llm_on):
    with _llm_answers({'v': 1}, {'v': 2}):
        llm.ask('t', 1, 'sys', {'x': 1})
        assert llm.ask('t', 2, 'sys', {'x': 1}) == {'v': 2}


def test_a_failure_is_not_cached(llm_on):
    with patch('llm.http.post', side_effect=OSError('down')):
        assert llm.ask('t', 1, 'sys', {'x': 1}) is None
    with _llm_answers({'ok': True}):
        assert llm.ask('t', 1, 'sys', {'x': 1}) == {'ok': True}


def test_the_model_only_chooses_among_the_candidates(llm_on):
    cands = [{'id': 1, 'name': 'A', 'year': '2020'}]
    with _llm_answers({'id': 999}):
        assert llm.pick_candidate('a', {}, cands) is None      # made-up id: distrusted
    with _llm_answers({'id': None}):
        assert llm.pick_candidate('b', {}, cands) is False     # "none of them"


# ── Resolution ────────────────────────────────────────────────────────────────

_PLUCKY = IgdbResult(id=42, name='The Plucky Squire', slug='the-plucky-squire',
                     data={'coverImageId': 'c', 'released': '2024', 'releaseDate': '2024-09-17'},
                     is_child=False)
_TS_2023 = 1_700_000_000


def _hit(igdb_id, name, year, other_names=()):
    """One `search_games` result, as IGDB's free-text search returns it."""
    return {'id': igdb_id, 'name': name, 'released': year, 'releaseDate': f'{year}-06-01',
            'alternativeNames': list(other_names)}


def _question(name='Le Vaillant Petit Page', pub_ts=_TS_2023, podcast_id='silence-on-joue'):
    from models import Episode, PodcastGame
    from questions import question_for
    from utils import make_slug
    episode = Episode(title='t', slug='g', audio_url=None, pub_ts=pub_ts, image_url=None,
                      description=None, chapters=[], games=[], podcast_id=podcast_id)
    return question_for(PodcastGame(make_slug(name), name), episode)


def _resolve(question=None, **kw):
    """Answer « Le Vaillant Petit Page » (a French title IGDB's search misses) with
    the scrapers off; returns the stored answer joined with its game."""
    from models import IgdbEntry
    question = question or _question()
    with patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve(question, **kw)
    answer = state.resolutions[question.key]
    return IgdbEntry(answer, state.games.get(answer.igdb_id))


def _pending(entry):
    return resolver.resolution_pending(entry.resolution)


def test_the_llm_resolves_a_translated_name(llm_on):
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': 42}), \
         patch('resolver.search_games', side_effect=lambda q: [
             _hit(42, 'The Plucky Squire', '2024')] if 'Plucky' in q else []), \
         patch('resolver.fetch_by_id', return_value=_PLUCKY) as by_id, \
         patch('resolver.fetch_by_name', return_value=None):
        entry = _resolve()
    by_id.assert_called_once_with(42)        # canonical, like the name search
    assert (entry.igdb_id, entry.resolution.method) == (42, 'llm')
    # What it was decided on is kept with the answer.
    assert (entry.resolution.titles, entry.resolution.candidates) == (['The Plucky Squire'], [42])


def test_a_game_newer_than_the_model_is_resolved_from_the_evidence(llm_on):
    # The model doesn't know « Silent Hill f » and reads it as a game it knows; that
    # reading only adds candidates — IGDB's match in the episode's window is offered
    # all the same, and the model judges it on its name and year.
    sh_f = IgdbResult(id=7, name='Silent Hill f', slug='silent-hill-f',
                      data={'released': '2025', 'releaseDate': '2025-09-25'}, is_child=False)
    with _llm_answers({'titles': ['Silent Hill']}, {'id': 7}) as post, \
         patch('resolver.search_games', side_effect=lambda q: [
             _hit(1, 'Silent Hill', '1999')] if q == 'Silent Hill' else []), \
         patch('resolver.fetch_by_name', return_value=sh_f):
        entry = _resolve(_question('Silent Hill f', 1_760_000_000))
    offered = json.loads(post.call_args_list[1].kwargs['json']['messages'][1]['content'])
    # Judged on dates: the episode's, and each candidate's release.
    assert offered['episode_date'] == '2025-10-09'
    assert {c['id']: c['released'] for c in offered['candidates']} == {1: '1999-06-01',
                                                                       7: '2025-09-25'}
    assert (entry.igdb_id, entry.resolution.method) == (7, 'llm')


def test_an_empty_reading_is_no_verdict(llm_on):
    # « Nothing to suggest » used to mean « not a game »: the name is still searched.
    with _llm_answers({'titles': []}, {'id': 42}) as post, \
         patch('resolver.search_games', return_value=[_hit(42, 'The Plucky Squire', '2024')]), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    assert post.call_count == 2
    assert entry.igdb_id == 42


def test_no_candidate_leaves_the_question_open_without_asking(llm_on):
    with _llm_answers({'titles': []}) as post, \
         patch('resolver.search_games', return_value=[]), \
         patch('resolver.fetch_by_name', return_value=None):
        entry = _resolve()
    assert post.call_count == 1                 # the reading; nothing to judge
    assert (entry.igdb_id, entry.resolution.method, entry.resolution.candidates) == (None, 'llm', [])
    assert not _pending(entry)


def test_an_answered_question_is_not_asked_again_after_a_new_prompt(llm_on, monkeypatch):
    with _llm_answers({'titles': []}, {'id': 42}), \
         patch('resolver.search_games', return_value=[_hit(42, 'The Plucky Squire', '2024')]), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    monkeypatch.setattr(llm, '_TITLES_V', llm._TITLES_V + 1)
    monkeypatch.setattr(llm, '_PICK_V', llm._PICK_V + 1)
    assert not _pending(entry)


def test_an_open_question_is_judged_again_only_on_new_evidence(llm_on, monkeypatch):
    from dataclasses import replace
    expired = '2000-01-01T00:00:00'
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': None}), \
         patch('resolver.search_games', return_value=[_hit(9, 'Plucky Puzzle', '2021')]), \
         patch('resolver.fetch_by_name', return_value=None):
        entry = _resolve()
    assert entry.igdb_id is None and not _pending(entry)
    key = entry.resolution.question
    state.resolutions[key] = replace(entry.resolution, decided_at=expired)
    assert resolver.resolution_pending(state.resolutions[key])   # open, past the TTL

    # Same evidence, even under a new prompt: same verdict, no call.
    monkeypatch.setattr(llm, '_PICK_V', llm._PICK_V + 1)
    with patch('llm.http.post') as post, \
         patch('resolver.search_games', return_value=[_hit(9, 'Plucky Puzzle', '2021')]), \
         patch('resolver.fetch_by_name', return_value=None):
        entry = _resolve()
    post.assert_not_called()                                # the reading is kept too
    state.resolutions[key] = replace(entry.resolution, decided_at=expired)

    # IGDB has added the game since: judged again.
    with _llm_answers({'id': 42}) as post, \
         patch('resolver.search_games', return_value=[_hit(9, 'Plucky Puzzle', '2021'),
                                                      _hit(42, 'The Plucky Squire', '2024')]), \
         patch('resolver.fetch_by_name', return_value=None), \
         patch('resolver.fetch_by_id', return_value=_PLUCKY):
        entry = _resolve()
    assert post.call_count == 1
    assert entry.igdb_id == 42


def test_without_the_llm_the_name_search_still_resolves(llm_on):
    with patch('llm.http.post', side_effect=OSError('down')), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    assert (entry.igdb_id, entry.resolution.method) == (42, 'search')


def test_the_quick_refresh_pass_skips_the_llm(llm_on):
    with patch('llm.http.post') as post, patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve(enrich=False, use_llm=False)
    post.assert_not_called()
    assert entry.resolution.method == 'search'


def test_a_search_result_goes_back_to_the_llm_after_its_backoff(llm_on):
    with patch('llm.http.post', side_effect=OSError('down')), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    # Served meanwhile, but provisional: the LLM is asked again — not every sweep.
    assert (entry.igdb_id, entry.resolution.method) == (42, 'search')
    assert (entry.resolution.attempts, entry.resolution.last_error) == (1, 'LLM unavailable')
    assert not _pending(entry)
    assert _pending(_retry_due(entry))


def _retry_due(entry):
    from dataclasses import replace
    from models import IgdbEntry
    return IgdbEntry(replace(entry.resolution, retry_at='2000-01-01T00:00:00'), entry.game)


def test_a_search_result_is_settled_once_the_llm_is_off(llm_on, monkeypatch):
    with patch('resolver.fetch_by_name', return_value=_PLUCKY):
        monkeypatch.setattr(Config, 'OPENROUTER_API_KEY', '')
        entry = _resolve()
    assert entry.resolution.retry_at is None
    assert not _pending(entry)               # the search is all there is


def test_an_llm_that_keeps_failing_is_asked_less_and_less_often(llm_on):
    import datetime
    from db import utcnow
    delays = []
    for _ in range(3):
        with patch('llm.http.post', side_effect=OSError('down')), \
             patch('resolver.fetch_by_name', return_value=_PLUCKY):
            entry = _resolve()
        delays.append(datetime.datetime.fromisoformat(entry.resolution.retry_at) - utcnow())
    assert entry.resolution.attempts == 3
    assert delays[0] < delays[1] < delays[2]


def test_the_llm_answering_clears_the_failures(llm_on):
    with patch('llm.http.post', side_effect=OSError('down')), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        _resolve()
    with _llm_answers({'titles': []}, {'id': 42}), \
         patch('resolver.search_games', return_value=[]), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    assert (entry.resolution.attempts, entry.resolution.retry_at) == (0, None)


def test_legacy_answers_are_settled(llm_on):
    from dataclasses import replace
    from models import IgdbEntry
    with _llm_answers({'titles': []}, {'id': 42}), \
         patch('resolver.search_games', return_value=[]), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    legacy = IgdbEntry(replace(entry.resolution, method=None, titles=None, candidates=None),
                       entry.game)
    assert not _pending(legacy)     # pre-LLM answer: kept as is


def test_a_correction_outranks_the_llm(llm_on):
    import corrections
    corrections.upsert('Le Vaillant Petit Page', igdb_id=42)
    with patch('llm.http.post') as post, \
         patch('resolver.fetch_by_id', return_value=_PLUCKY):
        entry = _resolve()
    post.assert_not_called()
    assert (entry.igdb_id, entry.resolution.method) == (42, 'pin')


# ── Shows whose games the LLM reads ───────────────────────────────────────────

import feeds                                    # noqa: E402
from podcasts import PODCAST_BY_ID              # noqa: E402

_TC_RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Triple Play: Saros</title><guid>tc-saros</guid>
    <enclosure url="https://example.com/1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Thu, 07 May 2026 09:00:00 +0000</pubDate>
    <description>&lt;p&gt;We review &lt;b&gt;Saros&lt;/b&gt;, Housemarque's follow-up to Returnal.&lt;/p&gt;</description></item>
  <item><title>Why Are There So Many Remakes? [Mailbag]</title><guid>tc-mail</guid>
    <enclosure url="https://example.com/2.mp3" type="audio/mpeg" length="0" />
    <pubDate>Thu, 30 Apr 2026 09:00:00 +0000</pubDate><description>Your questions.</description></item>
  <item><title>Beanscast: The Odyssey [TEASER]</title><guid>tc-beans</guid>
    <enclosure url="https://example.com/3.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 27 Apr 2026 09:00:00 +0000</pubDate><description>A film podcast.</description></item>
</channel></rss>"""


@pytest.fixture
def tc_feed():
    with patch.object(feeds, 'PODCASTS', [PODCAST_BY_ID['triple-click']]):
        yield


def _llm_by_title(answers: dict):
    """A mock for `llm.http.post` answering by episode title: order-free, since
    episodes are read in parallel."""
    def reply(*_a, json=None, **_kw):
        title = __import__('json').loads(json['messages'][1]['content'])['title']
        r = MagicMock()
        r.raise_for_status.return_value = None
        r.json.return_value = {'choices': [{'message': {'content':
                                            __import__('json').dumps(answers[title])}}]}
        return r
    return patch('llm.http.post', side_effect=reply)


_TC_ANSWERS = {'Triple Play: Saros': {'reviewed': ['Saros']},
               'Why Are There So Many Remakes? [Mailbag]': {'reviewed': []}}


def _refresh_tc():
    r = MagicMock(status_code=200, content=_TC_RSS, headers={})
    r.raise_for_status.return_value = None
    with patch('feeds.http.get', return_value=r):
        feeds.refresh_feed()


def test_an_unread_episode_stays_out_until_the_llm_reads_it(llm_on, tc_feed):
    _refresh_tc()
    assert state.episodes == []
    with _llm_by_title(_TC_ANSWERS) as post:
        assert feeds.read_new_episodes() == 2
    assert post.call_count == 2                       # the teaser is never asked about
    assert [(e.slug, [g.name for g in e.games]) for e in state.episodes] == [('tc-saros', ['Saros'])]
    sent = [json.loads(c.kwargs['json']['messages'][1]['content']) for c in post.call_args_list]
    saros = next(x for x in sent if x['title'] == 'Triple Play: Saros')
    assert saros['description'] == "We review Saros , Housemarque's follow-up to Returnal."


def test_read_episodes_are_not_asked_about_again(llm_on, tc_feed):
    _refresh_tc()
    with _llm_by_title(_TC_ANSWERS):
        feeds.read_new_episodes()
    with patch('llm.http.post') as post:
        assert feeds.read_new_episodes() == 0
    post.assert_not_called()


def test_without_the_llm_an_llm_read_show_contributes_nothing(tc_feed):
    _refresh_tc()
    with patch('llm.http.post') as post:
        assert feeds.read_new_episodes() == 0
    post.assert_not_called()
    assert state.episodes == []


def test_an_llm_read_game_points_at_its_chapter():
    from models import Chapter, Episode
    from rss import _extract_chapters
    chapters = _extract_chapters('03:00 - Gears of War: Judgment\n29:30 -- Luigi\'s Mansion: Dark Moon')
    assert [c.title for c in chapters] == ['Gears of War: Judgment', "Luigi's Mansion: Dark Moon"]
    ep = Episode(title='The Besties Podcast 50', slug='bes-50', audio_url='', pub_ts=None,
                 image_url=None, description='', chapters=chapters, games=[],
                 podcast_id='the-besties')
    with patch.object(feeds, 'PODCASTS', [PODCAST_BY_ID['the-besties']]), \
         patch('feeds.llm.reviewed_games',
               return_value=["Luigi's Mansion: Dark Moon", 'Gears of War: Judgment', 'Halo 4']):
        feeds._apply_llm_games([ep])
    assert [(g.name, g.timestamp_seconds) for g in ep.games] == [
        ("Luigi's Mansion: Dark Moon", 1770), ('Gears of War: Judgment', 180), ('Halo 4', 0)]


def test_a_prompt_change_keeps_the_episodes_until_the_new_answers_come_in(llm_on, tc_feed, monkeypatch):
    _refresh_tc()
    with _llm_by_title(_TC_ANSWERS):
        feeds.read_new_episodes()
    monkeypatch.setattr(llm, '_REVIEWED_V', llm._REVIEWED_V + 1)
    feeds.rebuild()
    assert [e.slug for e in state.episodes] == ['tc-saros']   # the old answer stands in
    answers = {**_TC_ANSWERS, 'Triple Play: Saros': {'reviewed': ['Saros', 'Returnal']}}
    with _llm_by_title(answers) as post:
        assert feeds.read_new_episodes() == 2          # yet both are asked again
    assert post.call_count == 2
    assert [g.name for g in state.episodes[0].games] == ['Saros', 'Returnal']


def test_a_name_the_llm_already_read_skips_the_titles_question(llm_on):
    with _llm_answers({'id': 42}) as post, \
         patch('resolver.search_games', return_value=[_hit(42, 'Saros', '2026')]) as search, \
         patch('resolver.fetch_by_id', return_value=_PLUCKY), \
         patch('resolver.fetch_by_name', return_value=None):
        entry = _resolve(_question('Saros', 1_778_000_000, 'triple-click'))
    assert post.call_count == 1                 # only the pick
    search.assert_called_once_with('Saros')
    assert entry.resolution.method == 'llm'


def test_the_name_searchs_match_is_offered_beside_the_free_text_results(llm_on):
    # IGDB's search lists only DLCs and seasons for some base games.
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': 42}) as post, \
         patch('resolver.search_games', return_value=[
             _hit(9, 'The Plucky Squire - Season 2', '2025')]), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY), \
         patch('resolver.fetch_by_id') as by_id:
        entry = _resolve()
    offered = json.loads(post.call_args_list[1].kwargs['json']['messages'][1]['content'])
    assert {c['id'] for c in offered['candidates']} == {9, 42}
    by_id.assert_not_called()
    assert entry.igdb_id == 42


# ── What IGDB's search misses ─────────────────────────────────────────────────

_TS_2025_03 = 1_742_700_000          # 2025-03-23: a window from 2024-03 to 2025-09


def _release(igdb_id, name, *days, other_names=(), game_type=0):
    """One `igdb.releases` row: its release dates as ISO days."""
    import datetime as dt
    return {'id': igdb_id, 'name': name, 'gameType': game_type, 'otherNames': list(other_names),
            'dates': sorted(int(dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp())
                            for d in days)}


def _offered(post):
    return {c['id']: c for c in json.loads(post.call_args_list[-1].kwargs['json']['messages'][1]['content'])['candidates']}


def test_a_game_the_name_is_an_other_name_of_is_offered(llm_on):
    # IGDB's search doesn't look at other names: « Rhythm Paradise Groove » is
    # only one of Rhythm Heaven Groove's.
    groove = _release(337031, 'Rhythm Heaven Groove', '2025-03-01', other_names=['Rhythm Paradise Groove'])
    with _llm_answers({'titles': []}, {'id': 337031}) as post, \
         patch('resolver.search_games', return_value=[]), \
         patch('resolver.fetch_by_name', return_value=None), \
         patch('resolver.alternative_name_ids', return_value={337031}), \
         patch('resolver.releases', return_value=[groove]), \
         patch('resolver.fetch_by_id', return_value=IgdbResult(337031, 'Rhythm Heaven Groove', 'rhg', {}, False)):
        entry = _resolve(_question('Rhythm Paradise Groove', _TS_2025_03))
    assert _offered(post)[337031]['released'] == '2025-03-01'
    assert entry.igdb_id == 337031


def test_an_old_namesake_stays_out(llm_on):
    # « Jump » on a 2009 show isn't David Bowie's 1994 CD-ROM, which bears the
    # name as an other name.
    with _llm_answers({'titles': []}) as post, \
         patch('resolver.search_games', return_value=[]), \
         patch('resolver.fetch_by_name', return_value=None), \
         patch('resolver.alternative_name_ids', return_value={77}), \
         patch('resolver.releases', return_value=[_release(77, 'Jump: The David Bowie CD-ROM', '1994-05-01')]):
        entry = _resolve(_question('Jump', _TS_2025_03))
    assert post.call_count == 1                 # the titles only: no candidate to judge
    assert entry.igdb_id is None


def test_the_catalogs_answer_for_a_name_spelled_alike_is_offered(llm_on, monkeypatch):
    # The Besties' « Ball x Pit » is resolved; « BALLxPIT » is the same name.
    from models import PodcastGame, Resolution
    key = 'name|the-besties|2025|ball-x-pit'
    monkeypatch.setattr(state, 'resolutions', {key: Resolution(key, 346035, False, '2999-01-01T00:00:00', 'llm')})
    monkeypatch.setattr(state, 'game_index', {'ball-x-pit': PodcastGame('ball-x-pit', 'Ball x Pit')})
    with _llm_answers({'titles': []}, {'id': 346035}) as post, \
         patch('resolver.search_games', return_value=[]), \
         patch('resolver.fetch_by_name', return_value=None), \
         patch('resolver.releases', side_effect=lambda ids: [_release(i, 'Ball x Pit', '2025-01-15') for i in ids]), \
         patch('resolver.fetch_by_id', return_value=IgdbResult(346035, 'Ball x Pit', 'ball-x-pit', {}, False)):
        entry = _resolve(_question('BALLxPIT', _TS_2025_03))
    assert set(_offered(post)) == {346035}
    assert entry.igdb_id == 346035


def test_a_candidate_is_dated_by_its_first_release_early_access_included(llm_on):
    # IGDB's first_release_date is 33 Immortals' 1.0, a year after the episode;
    # its early access came out five days before. The rest is the search's.
    hit = {**_hit(252828, '33 Immortals', '2026', ['33I']), 'releaseDate': '2026-06-10'}
    with _llm_answers({'titles': []}, {'id': 252828}) as post, \
         patch('resolver.search_games', return_value=[hit]), \
         patch('resolver.fetch_by_name', return_value=None), \
         patch('resolver.releases', return_value=[_release(252828, '33 Immortals', '2025-03-18', '2026-06-10',
                                                           other_names=['many', 'more', 'names'])]), \
         patch('resolver.fetch_by_id', return_value=IgdbResult(252828, '33 Immortals', '33-immortals', {}, False)):
        _resolve(_question('33 Immortals', _TS_2025_03))
    assert _offered(post)[252828] == {'id': 252828, 'name': '33 Immortals', 'otherNames': ['33I'],
                                      'released': '2025-03-18'}
