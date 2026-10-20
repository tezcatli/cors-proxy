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
                     data={'coverImageId': 'c'}, is_child=False)
_SLUG   = 'le-vaillant-petit-page-ep1'


def _resolve(**kw):
    """Resolve « Le Vaillant Petit Page » (a French title IGDB's search misses)
    with the scrapers off; returns the cached entry."""
    with patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve_one(_SLUG, 'Le Vaillant Petit Page', 1_700_000_000,
                             'silence-on-joue', **kw)
    return state.entry(_SLUG)


def test_the_llm_resolves_a_translated_name(llm_on):
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': 42}), \
         patch('resolver.search_games', side_effect=lambda q: [
             {'id': 42, 'name': 'The Plucky Squire', 'released': '2024'}] if 'Plucky' in q else []), \
         patch('resolver.fetch_by_id', return_value=_PLUCKY) as by_id, \
         patch('resolver.fetch_by_name', return_value=None):
        entry = _resolve()
    by_id.assert_called_once_with(42)        # canonical, like the name search
    assert (entry.igdb_id, entry.resolution.method) == (42, 'llm')


def test_a_name_the_llm_rules_out_is_a_settled_miss(llm_on):
    with _llm_answers({'titles': []}), patch('resolver.fetch_by_name') as by_name:
        entry = _resolve()
    by_name.assert_not_called()
    assert (entry.igdb_id, entry.resolution.method) == (None, 'llm')


def test_a_title_igdbs_free_text_search_misses_goes_through_the_name_search(llm_on):
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': 42}), \
         patch('resolver.search_games', return_value=[]), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY), \
         patch('resolver.fetch_by_id') as by_id:
        entry = _resolve()
    by_id.assert_not_called()
    assert (entry.igdb_id, entry.resolution.method) == (42, 'llm')


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


def _pending(entry):
    game = MagicMock(); game.name = 'Le Vaillant Petit Page'
    app  = MagicMock(podcast_slug=_SLUG)
    app.episode.pub_ts, app.episode.podcast_id = 1_700_000_000, 'silence-on-joue'
    return resolver.appearance_pending(game, app, {_SLUG: entry})


def test_a_search_result_stays_pending_while_the_llm_is_on(llm_on, monkeypatch):
    with patch('llm.http.post', side_effect=OSError('down')), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    assert _pending(entry)
    monkeypatch.setattr(Config, 'OPENROUTER_API_KEY', '')
    assert not _pending(entry)               # LLM off: the search is all there is


def test_llm_and_legacy_rows_are_settled(llm_on):
    from dataclasses import replace
    from models import IgdbEntry
    with _llm_answers({'titles': []}):
        entry = _resolve()
    assert not _pending(entry)
    legacy = IgdbEntry(replace(entry.resolution, method=None), entry.game)
    assert not _pending(legacy)   # pre-LLM row: left to the dev audit


def test_a_provisional_search_result_goes_to_the_llm(llm_on):
    with patch('llm.http.post', side_effect=OSError('down')), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        _resolve()
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': 42}), \
         patch('resolver.search_games', return_value=[
             {'id': 42, 'name': 'The Plucky Squire', 'released': '2024'}]), \
         patch('resolver.fetch_by_name', return_value=None), \
         patch('resolver.fetch_by_id', return_value=_PLUCKY) as by_id:
        entry = _resolve()
    by_id.assert_called_once_with(42)        # canonical, like the name search
    assert entry.resolution.method == 'llm'


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
        assert feeds.ask_llm_for_new_episodes() == 2
    assert post.call_count == 2                       # the teaser is never asked about
    assert [(e.slug, [g.name for g in e.games]) for e in state.episodes] == [('tc-saros', ['Saros'])]
    sent = [json.loads(c.kwargs['json']['messages'][1]['content']) for c in post.call_args_list]
    saros = next(x for x in sent if x['title'] == 'Triple Play: Saros')
    assert saros['description'] == "We review Saros , Housemarque's follow-up to Returnal."


def test_read_episodes_are_not_asked_about_again(llm_on, tc_feed):
    _refresh_tc()
    with _llm_by_title(_TC_ANSWERS):
        feeds.ask_llm_for_new_episodes()
    with patch('llm.http.post') as post:
        assert feeds.ask_llm_for_new_episodes() == 0
    post.assert_not_called()


def test_without_the_llm_an_llm_read_show_contributes_nothing(tc_feed):
    _refresh_tc()
    with patch('llm.http.post') as post:
        assert feeds.ask_llm_for_new_episodes() == 0
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
        feeds.ask_llm_for_new_episodes()
    monkeypatch.setattr(llm, '_REVIEWED_V', llm._REVIEWED_V + 1)
    feeds.rebuild()
    assert [e.slug for e in state.episodes] == ['tc-saros']   # the old answer stands in
    answers = {**_TC_ANSWERS, 'Triple Play: Saros': {'reviewed': ['Saros', 'Returnal']}}
    with _llm_by_title(answers) as post:
        assert feeds.ask_llm_for_new_episodes() == 2          # yet both are asked again
    assert post.call_count == 2
    assert [g.name for g in state.episodes[0].games] == ['Saros', 'Returnal']


def test_a_name_the_llm_already_read_skips_the_titles_question(llm_on):
    with _llm_answers({'id': 42}) as post, \
         patch('resolver.search_games', return_value=[
             {'id': 42, 'name': 'Saros', 'released': '2026'}]) as search, \
         patch('resolver.fetch_by_id', return_value=_PLUCKY), \
         patch('resolver.fetch_by_name', return_value=None), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve_one('saros-tc1', 'Saros', 1_778_000_000, 'triple-click')
    assert post.call_count == 1                 # only the pick
    search.assert_called_once_with('Saros')
    assert state.entry('saros-tc1').resolution.method == 'llm'


def test_the_name_searchs_match_is_offered_beside_the_free_text_results(llm_on):
    # IGDB's search lists only DLCs and seasons for some base games.
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': 42}) as post, \
         patch('resolver.search_games', return_value=[
             {'id': 9, 'name': 'The Plucky Squire - Season 2', 'released': '2025'}]), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY), \
         patch('resolver.fetch_by_id') as by_id:
        entry = _resolve()
    offered = json.loads(post.call_args_list[1].kwargs['json']['messages'][1]['content'])
    assert {c['id'] for c in offered['candidates']} == {9, 42}
    by_id.assert_not_called()
    assert entry.igdb_id == 42
