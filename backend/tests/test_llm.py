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
                             'silence-on-joue', episode_title='«Le Vaillant Petit Page»', **kw)
    return state.igdb_cache[_SLUG]


def test_the_llm_resolves_a_translated_name(llm_on):
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': 42}), \
         patch('resolver.search_games', side_effect=lambda q: [
             {'id': 42, 'name': 'The Plucky Squire', 'released': '2024'}] if 'Plucky' in q else []), \
         patch('resolver.fetch_by_id', return_value=_PLUCKY) as by_id, \
         patch('resolver.fetch_by_name') as by_name:
        entry = _resolve()
    by_id.assert_called_once_with(42)        # canonical, like the name search
    by_name.assert_not_called()
    assert (entry.igdb_id, entry.method) == (42, 'llm')


def test_a_name_the_llm_rules_out_is_a_settled_miss(llm_on):
    with _llm_answers({'titles': []}), patch('resolver.fetch_by_name') as by_name:
        entry = _resolve()
    by_name.assert_not_called()
    assert (entry.igdb_id, entry.method) == (None, 'llm')


def test_without_the_llm_the_name_search_still_resolves(llm_on):
    with patch('llm.http.post', side_effect=OSError('down')), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    assert (entry.igdb_id, entry.method) == (42, 'search')


def test_the_quick_refresh_pass_skips_the_llm(llm_on):
    with patch('llm.http.post') as post, patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve(enrich=False, use_llm=False)
    post.assert_not_called()
    assert entry.method == 'search'


def _pending(entry):
    game = MagicMock(); game.name = 'Le Vaillant Petit Page'
    app  = MagicMock(podcast_slug=_SLUG)
    app.episode.pub_ts, app.episode.podcast_id = 1_700_000_000, 'silence-on-joue'
    cache = {_SLUG: entry}
    return resolver.appearance_pending(game, app, cache, resolver.fresh_slugs(cache.items()))


def test_a_search_result_stays_pending_while_the_llm_is_on(llm_on, monkeypatch):
    with patch('llm.http.post', side_effect=OSError('down')), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        entry = _resolve()
    assert _pending(entry)
    monkeypatch.setattr(Config, 'OPENROUTER_API_KEY', '')
    assert not _pending(entry)               # LLM off: the search is all there is


def test_llm_and_legacy_rows_are_settled(llm_on):
    from dataclasses import replace
    with _llm_answers({'titles': []}):
        entry = _resolve()
    assert not _pending(entry)
    assert not _pending(replace(entry, method=None))   # pre-LLM row: left to the dev audit


def test_a_provisional_search_result_goes_to_the_llm_not_a_renewal(llm_on):
    with patch('llm.http.post', side_effect=OSError('down')), \
         patch('resolver.fetch_by_name', return_value=_PLUCKY):
        _resolve()
    with _llm_answers({'titles': ['The Plucky Squire']}, {'id': 42}), \
         patch('resolver.search_games', return_value=[
             {'id': 42, 'name': 'The Plucky Squire', 'released': '2024'}]), \
         patch('resolver.fetch_by_id', return_value=_PLUCKY) as by_id:
        entry = _resolve()
    by_id.assert_called_once_with(42)        # not the renewal's (42, canonical=False)
    assert entry.method == 'llm'


def test_a_correction_outranks_the_llm(llm_on):
    import corrections
    corrections.upsert('Le Vaillant Petit Page', igdb_id=42)
    with patch('llm.http.post') as post, \
         patch('resolver.fetch_by_id', return_value=_PLUCKY):
        entry = _resolve()
    post.assert_not_called()
    assert (entry.igdb_id, entry.method) == (42, 'pin')
