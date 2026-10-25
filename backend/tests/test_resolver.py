"""Answering the questions (`resolver.py`) and the IGDB cache (`catalog_state.py`): pins, the sweep, the TTL, pruning."""
from dataclasses import replace
from unittest.mock import patch

import catalog_state as state
import feeds
import games
import resolver
from db import utcnow
from utils import make_slug
from conftest import auth_header, cache_entry, set_cache
from rss import parse_feed as _parse_feed
from questions import question_for
from catalog_fixtures import _EXPIRED, _NOW, _TWO_EPISODES_SAME_NAME, _ask, _entry, _fresh_entry, _igdb_hit, _seed, _single_soj_game, mock_rss_response


def test_count_pending_respects_ttl():
    """TTL-expired-but-cached appearances are counted as pending; freshly cached
    ones are not. Guards the datetime compare."""
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/e.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    episodes = _parse_feed(rss)
    _, game_index = feeds.build_indexes(episodes)
    state.game_index = game_index
    slugs = [a.podcast_slug for g in game_index.values() for a in g.appearances]
    assert slugs

    def cache_with(cached_at):
        return {s: cache_entry(s, 1, 'zelda', 'Zelda', {'metacritic': 90}, False, cached_at) for s in slugs}

    set_cache(cache_with(utcnow().isoformat()))
    assert resolver.count_pending() == 0                # fresh → nothing pending

    set_cache(cache_with('2000-01-01T00:00:00'))
    assert resolver.count_pending() == len(slugs)       # TTL-expired → all pending


def test_refresh_resolves_new_games_without_the_scrapers(client):
    # Someone pulling to refresh after an episode came out should get the new
    # games' names and covers in that response; the slow scrapers wait.
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.fetch_by_name', side_effect=lambda n, ts: _igdb_hit(n)), \
         patch('resolver.metacritic.fetch_metascore') as mc, \
         patch('resolver.hltb.fetch_time_to_beat') as hl, \
         patch('resolver.schedule_resolve'):
        r = client.post('/games/refresh', headers=auth_header())
    mc.assert_not_called()
    hl.assert_not_called()
    zelda = next(g for g in r.get_json()['games'] if g['name'] == 'Zelda')
    assert zelda['igdb'] == {'metacritic': None, 'coverImageId': 'abc'}
    # Not enriched yet → still pending, so the background sweep finishes the job.
    assert all(not g.enriched for g in state.games.values())
    assert resolver.count_pending() == len(state.resolutions)


def test_refresh_leaves_new_games_to_the_sweep_once_the_budget_is_spent(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.fetch_by_name') as by_name, \
         patch('resolver.schedule_resolve') as sweep, \
         patch('resolver.REFRESH_BUDGET_S', 0):
        client.post('/games/refresh', headers=auth_header())
    by_name.assert_not_called()
    sweep.assert_called_once_with()


def test_unenriched_flag_survives_a_restart():
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Zelda')):
        resolver.resolve(_ask('Zelda'), enrich=False)
    state.load_igdb_cache_from_db()
    assert state.games[7].enriched is False


def test_a_pin_is_fetched_as_is_neither_searched_nor_judged(tmp_corrections, monkeypatch):
    from config import Config
    from igdb import IgdbResult
    import corrections
    monkeypatch.setattr(Config, 'OPENROUTER_API_KEY', 'test-key')     # the LLM is on…
    corrections.upsert('Chrono Trigger', igdb_id=4242)
    result = IgdbResult(id=4242, name='Chrono Trigger', slug='chrono-trigger',
                        data={'metacritic': 92}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=result) as by_id, \
         patch('resolver.fetch_by_name') as by_name, \
         patch('llm.http.post') as llm_post, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve(_ask('Chrono Trigger', podcast_id='fin-du-game'))
    by_name.assert_not_called()
    llm_post.assert_not_called()                                         # …and outranked
    # canonical=False: a human's pin must not be redirected to a parent game.
    assert by_id.call_args == ((4242,), {'canonical': False})
    answer = state.resolutions['pin|4242']
    assert (answer.igdb_id, answer.method, state.games[4242].igdb_slug) == (4242, 'pin', 'chrono-trigger')


def test_a_shipped_correction_asks_a_new_question_and_its_removal_the_old_one(tmp_corrections):
    import corrections
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: _fresh_entry(appearance)})
    assert resolver.count_pending() == 0
    corrections.upsert('Chrono Trigger', igdb_id=4242)               # ship a pin
    assert question_for(game, appearance.episode).key == 'pin|4242'
    assert resolver.count_pending() == 1                             # unanswered
    set_cache({appearance.podcast_slug: _fresh_entry(appearance)})   # the sweep answers it
    corrections.remove('Chrono Trigger')                             # ship its removal
    assert question_for(game, appearance.episode).kind == 'name'
    assert resolver.count_pending() == 1


def test_prune_drops_unasked_questions_then_unused_games():
    from models import Resolution
    game, appearance = _single_soj_game()
    asked_key = question_for(game, appearance.episode).key
    for key, igdb_id in ((asked_key, 1), ('name|silence-on-joue|2020|gone', 2)):
        state.store_resolution(Resolution(key, igdb_id, False, _NOW))
    for igdb_id in (1, 2, 3):
        state.store_game(cache_entry('x', igdb_id, f'g{igdb_id}', f'G{igdb_id}').game)

    state.prune_igdb_cache()

    assert set(state.resolutions) == {asked_key}
    assert set(state.games) == {1}                   # 2 lost its last answer; 3 had none
    state.load_igdb_cache_from_db()                  # …and the DB agrees
    assert (set(state.resolutions), set(state.games)) == ({asked_key}, {1})


def test_prune_keeps_everything_when_the_feed_parsed_empty():
    # A transient empty parse must not wipe the cache.
    state.store_resolution(cache_entry('a', 1, 'a', 'A').resolution)
    state.store_game(cache_entry('a', 1, 'a', 'A').game)
    state.game_index = {}
    state.prune_igdb_cache()
    assert (set(state.resolutions), set(state.games)) == ({'a'}, {1})


def _sweep(cached, by_id=None):
    """Run the background sweep over Chrono Trigger's appearance with `cached`
    (a function of the appearance) in the cache; returns the two IGDB mocks."""
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: cached(appearance)})
    with patch('resolver.fetch_by_id', return_value=by_id) as by_id_mock, \
         patch('resolver.fetch_by_name', return_value=_igdb_hit('Chrono Trigger')) as by_name, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.schedule_resolve()
    return by_id_mock, by_name, question_for(game, appearance.episode).key


def test_an_expired_game_is_renewed_by_id_not_searched_again(tmp_corrections):
    # Asking again could land on a same-name game IGDB added since, undoing an
    # answer that was right; the known id can't.
    from igdb import IgdbResult
    expired_child = lambda a: cache_entry(   # noqa: E731
        a.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger', {'metacritic': 90},
        is_child=True, at=_EXPIRED, method='search')
    by_id, by_name, key = _sweep(expired_child, IgdbResult(
        id=1, name='Chrono Trigger', slug='chrono-trigger', data={'metacritic': 93},
        is_child=False))
    by_id.assert_called_once_with(1, canonical=False)
    by_name.assert_not_called()
    assert state.games[1].data['metacritic'] == 93
    assert state.resolutions[key].is_child   # still ranks as the DLC/version it was resolved from


def test_a_game_igdb_dropped_is_asked_again(tmp_corrections):
    expired = lambda a: cache_entry(   # noqa: E731
        a.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger', at=_EXPIRED)
    by_id, by_name, key = _sweep(expired, by_id=None)
    by_id.assert_called_once_with(1, canonical=False)
    assert key not in state.resolutions and 1 not in state.games
    assert resolver.count_pending() == 1          # the next sweep asks it again


def test_an_open_question_is_looked_at_again_once_expired(tmp_corrections):
    miss = lambda at: lambda a: cache_entry(a.podcast_slug, None, None, None, at=at)  # noqa: E731
    by_id, by_name, _ = _sweep(miss(utcnow().isoformat()))
    by_name.assert_not_called()
    by_id, by_name, key = _sweep(miss(_EXPIRED))
    by_id.assert_not_called()
    by_name.assert_called_once()
    assert state.resolutions[key].igdb_id == 7


def test_a_shipped_search_correction_searches_its_query(tmp_corrections):
    import corrections
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: _fresh_entry(appearance)})   # answered…
    tmp_corrections.write_text('{"corrections": [{"podcast_name": "Chrono Trigger", '
                               '"search_name": "Chrono Trigger SNES"}]}', encoding='utf-8')
    corrections.load()                                                 # …then a fix ships
    question = question_for(game, appearance.episode)
    assert question.key.startswith('search|chrono-trigger-snes|')
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Chrono Trigger')) as by_name, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.schedule_resolve()
    assert by_name.call_args.args == ('Chrono Trigger SNES', question.window)
    assert state.resolutions[question.key].method == 'pin'      # a curator's search
    state.prune_igdb_cache()
    assert set(state.resolutions) == {question.key}             # the old question is gone


def test_a_settled_appearance_on_a_fresh_game_costs_nothing(tmp_corrections):
    by_id, by_name, _ = _sweep(_fresh_entry)
    by_id.assert_not_called()
    by_name.assert_not_called()


def test_an_igdb_error_is_retried_after_a_backoff_not_every_sweep(tmp_corrections):
    game, appearance = _single_soj_game()
    question = question_for(game, appearance.episode)
    with patch('resolver.fetch_by_name', side_effect=OSError('IGDB down')):
        resolver.resolve(question)
    failed = state.resolutions[question.key]
    assert (failed.igdb_id, failed.attempts, failed.last_error) == (None, 1, 'IGDB down')
    assert failed.retry_at > utcnow().isoformat()
    assert resolver.count_pending() == 0                   # waiting out its backoff

    state.resolutions[question.key] = replace(failed, retry_at=_EXPIRED)
    assert resolver.count_pending() == 1                   # due again
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Chrono Trigger')), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve(question)
    settled = state.resolutions[question.key]
    assert (settled.igdb_id, settled.attempts, settled.retry_at) == (7, 0, None)


def test_a_failed_retry_keeps_serving_the_previous_answer(tmp_corrections):
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: _fresh_entry(appearance)})
    with patch('resolver.fetch_by_name', side_effect=OSError('IGDB down')):
        resolver.resolve(question_for(game, appearance.episode))
    entry = state.entries()[appearance.podcast_slug]
    assert (entry.igdb_slug, entry.resolution.attempts) == ('chrono-trigger', 1)


def test_a_game_is_scraped_once_for_all_its_episodes():
    # Metacritic and HowLongToBeat take ~1–10 s a game: a second question landing
    # on the same game (another year's episodes) reuses its figures.
    ts_2024, ts_2025 = 1_705_000_000, 1_736_000_000
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Zelda')), \
         patch('resolver.metacritic.fetch_metascore', return_value=91) as mc, \
         patch('resolver.hltb.fetch_time_to_beat', return_value=40) as hl:
        resolver.resolve(_ask('Zelda', ts_2024), use_llm=False)
        resolver.resolve(_ask('Zelda', ts_2025), use_llm=False)
    assert len(state.resolutions) == 2
    assert mc.call_count == hl.call_count == 1
    assert state.games[7].enriched
    assert (state.games[7].data['metacritic'], state.games[7].data['timeToBeatHours']) == (91, 40)


def test_a_purge_fetches_the_games_data_again(client):
    # The one way to get a fresh Metacritic score before the TTL: the admin's
    # purge (per podcast, POST /games/podcasts/<id>/igdb-refresh).
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 1, 'silent-hill-2', 'Silent Hill 2',
                               metacritic=80),
    })
    from igdb import IgdbResult
    same = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2', data={}, is_child=False)
    with patch('resolver.fetch_by_name', return_value=same), \
         patch('resolver.metacritic.fetch_metascore', return_value=89) as mc, \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        members = [(g, a) for g in state.game_index.values() for a in g.appearances]
        games._purge_with_games(members, state.entries())
        resolver.resolve_members(members)
    mc.assert_called_once()
    assert state.games[1].data['metacritic'] == 89
