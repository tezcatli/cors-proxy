"""Corrections through the API (`games.py` admin routes): pinning, renaming, removing, read-only prod."""
from unittest.mock import patch

import pytest

import catalog_state as state
import feeds
import serializers
from utils import make_slug
from contract import assert_contract
from conftest import admin_header, set_cache
from rss import parse_feed as _parse_feed, assign_url_slugs as _assign_url_slugs
from podcasts import PODCAST_BY_ID
from questions import question_for
from catalog_fixtures import GAMES, _FDG_RSS, _SOJ_RSS, _TWO_EPISODES_SAME_NAME, _entry, _seed


def test_igdb_search_requires_a_query(client):
    r = client.get('/games/igdb-search', headers=admin_header())
    assert_contract(r, GAMES['igdb_search']['bad_request'])


def test_igdb_search_returns_results(client):
    rows = [{'id': 1, 'name': 'Chrono Trigger', 'slug': 'chrono-trigger',
             'released': '1995', 'coverImageId': 'co1'}]
    with patch('games.search_games', return_value=rows):
        r = client.get('/games/igdb-search?q=chrono', headers=admin_header())
    assert_contract(r, GAMES['igdb_search']['success'])
    assert r.get_json()['results'] == rows


@pytest.mark.parametrize('body', [
    {'igdbId': 1, 'podcastId': 'nope'},       # an unknown podcast
    {},                                        # neither a pin nor a name
    {'igdbId': 'nope'},                        # a pin that isn't an id
])
def test_a_correction_that_says_nothing_valid_is_refused(client, tmp_corrections, body):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.put('/games/corrections', headers=admin_header(),
                   json={'nameSlug': make_slug('Silent Hill 2'), **body})
    assert_contract(r, GAMES['corrections']['bad_request'])


def test_correction_rejects_an_unknown_game(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.put('/games/corrections', headers=admin_header(),
                   json={'nameSlug': 'no-such-game', 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['not_found'])


def test_correction_write_pins_purges_and_reresolves(client, tmp_corrections):
    import json as _json
    from igdb import IgdbResult
    ns = make_slug('Silent Hill 2')
    # Start from a wrong resolution, as the FDG date-window bug produced.
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 9, 'astrobotanica', 'Astrobotanica'),
    })
    fixed = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2',
                       data={'released': '2001'}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=fixed), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['success'])
    body = r.get_json()
    assert body['slug'] == 'silent-hill-2'
    assert body['igdb']['released'] == '2001'
    assert body['corrected'] is True
    # The stale 'astrobotanica' cache row is gone…
    assert state.entries()[f'{ns}-original'].igdb_slug == 'silent-hill-2'
    # …and the pin landed in the git-tracked file, keyed on the feed's wording.
    written = _json.loads(tmp_corrections.read_text())['corrections']
    assert written == [{'podcast_name': 'Silent Hill 2', 'igdb_id': 1}]


def test_correction_scoped_to_one_podcast_leaves_the_other_alone(client, tmp_corrections):
    from igdb import IgdbResult
    ns  = make_slug('Chrono Trigger')
    soj = _parse_feed(_SOJ_RSS, extractor=PODCAST_BY_ID['silence-on-joue'].extractor,
                      podcast_id='silence-on-joue')
    fdg = _parse_feed(_FDG_RSS, extractor=PODCAST_BY_ID['fin-du-game'].extractor,
                      podcast_id='fin-du-game')
    episodes = soj + fdg
    _assign_url_slugs(episodes)
    episode_index, game_index = feeds.build_indexes(episodes)
    state.episodes = episodes
    state.episode_index   = episode_index
    state.game_index      = game_index
    set_cache({
        f'{ns}-soj1': _entry(f'{ns}-soj1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
        f'{ns}-fdg1': _entry(f'{ns}-fdg1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
    })
    state.data_version += 1

    fixed = IgdbResult(id=1, name='Chrono Trigger', slug='chrono-trigger',
                       data={'released': '1995'}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=fixed), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1, 'podcastId': 'fin-du-game'})
    assert r.status_code == 200
    # Only the FDG appearance moved; the SOJ one keeps its own resolution — the
    # split the per-appearance grouping exists to allow.
    assert state.entries()[f'{ns}-fdg1'].igdb_slug == 'chrono-trigger'
    assert state.entries()[f'{ns}-soj1'].igdb_slug == 'chrono-trigger--3'
    assert [e['slug'] for e in r.get_json()['episodes']] == ['fdg1']


def test_delete_correction_reverts_to_the_name_search(client, tmp_corrections):
    import corrections
    from igdb import IgdbResult
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})
    corrections.upsert('Silent Hill 2', igdb_id=1)

    searched = IgdbResult(id=7, name='Silent Hill 2', slug='silent-hill-2',
                          data={'released': '2001'}, is_child=False)
    with patch('resolver.fetch_by_name', return_value=searched) as by_name, \
         patch('resolver.fetch_by_id') as by_id, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.delete('/games/corrections', headers=admin_header(),
                          json={'nameSlug': ns})
    assert r.status_code == 200
    by_id.assert_not_called()      # no longer pinned
    assert by_name.called
    assert corrections.CORRECTIONS == []


def test_delete_correction_that_does_not_exist_404s(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.delete('/games/corrections', headers=admin_header(),
                      json={'nameSlug': make_slug('Silent Hill 2')})
    assert_contract(r, GAMES['corrections']['not_found'])


def test_corrections_write_is_refused_when_the_file_is_read_only(client, tmp_corrections):
    # Stands in for prod, where corrections.json ships in the read-only image layer.
    _seed(_TWO_EPISODES_SAME_NAME, {})
    with patch('corrections.is_writable', return_value=False):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': make_slug('Silent Hill 2'), 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['read_only'])
    assert 'dev' in r.get_json()['error']


def test_podcast_igdb_refresh_purges_only_that_podcast(client):
    ns  = make_slug('Chrono Trigger')
    soj = _parse_feed(_SOJ_RSS, extractor=PODCAST_BY_ID['silence-on-joue'].extractor,
                      podcast_id='silence-on-joue')
    fdg = _parse_feed(_FDG_RSS, extractor=PODCAST_BY_ID['fin-du-game'].extractor,
                      podcast_id='fin-du-game')
    _, game_index = feeds.build_indexes(soj + fdg)
    state.game_index = game_index
    set_cache({
        f'{ns}-soj1': _entry(f'{ns}-soj1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
        f'{ns}-fdg1': _entry(f'{ns}-fdg1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
    })
    with patch('resolver.schedule_resolve') as sched:
        r = client.post('/games/podcasts/fin-du-game/igdb-refresh',
                        headers=admin_header())
    assert_contract(r, GAMES['podcast_igdb_refresh']['success'])
    assert r.get_json()['purged'] == 1
    soj_q, fdg_q = (question_for(game_index[ns], a.episode).key
                    for a in sorted(game_index[ns].appearances,
                                    key=lambda a: a.episode.podcast_id != 'silence-on-joue'))
    assert fdg_q not in state.resolutions            # purged
    assert soj_q in state.resolutions                # untouched
    sched.assert_called_once()


def test_podcast_igdb_refresh_unknown_podcast_404s(client):
    r = client.post('/games/podcasts/nope/igdb-refresh', headers=admin_header())
    assert_contract(r, GAMES['podcast_igdb_refresh']['not_found'])


def test_resolution_stats_shape(client):
    # The console's content is a dev tool's: only its shape is held.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {f'{ns}-remake': _entry(f'{ns}-remake', 9, 'astrobotanica', 'Astrobotanica')})
    assert_contract(client.get('/games/resolution-stats', headers=admin_header()),
                    GAMES['resolution_stats']['success'])


def test_detail_reports_whether_a_correction_applies_at_its_scope(client, tmp_corrections):
    # A correction scoped to a podcast this entry has no episodes from must not
    # light up the "remove the correction" affordance.
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})          # seeded as silence-on-joue
    assert serializers.load_game(ns)['corrected'] is False
    corrections.upsert('Silent Hill 2', 'fin-du-game', igdb_id=1)
    assert serializers.load_game(ns)['corrected'] is False
    corrections.upsert('Silent Hill 2', igdb_id=1)
    assert serializers.load_game(ns)['corrected'] is True


def test_stats_reports_read_only_deployments(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    with patch('corrections.is_writable', return_value=False):
        body = client.get('/games/resolution-stats', headers=admin_header()).get_json()
    assert body['writable'] is False


def test_catalog_applies_a_podcast_scoped_display_name(tmp_corrections):
    # group_display_name must look the correction up at the appearance's own
    # podcast scope, or a podcast_id-scoped rename would show in the admin
    # console (which passes podcast_id) but never in the catalog.
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 2, 'silent-hill-2-remake', 'Silent Hill 2 Remake'),
    })
    corrections.upsert('Silent Hill 2', 'silence-on-joue',
                       display_name='Silent Hill 2 (renommé)')
    names = {g['slug']: g['name'] for g in serializers.build_catalog()}
    assert names['silent-hill-2-remake'] == 'Silent Hill 2 (renommé)'


def test_renaming_does_not_re_resolve(client, tmp_corrections):
    # display_name is applied at response time, so a rename must not burn a round
    # of IGDB + Metacritic + HLTB calls to arrive at the same entry.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2', 'Silent Hill 2'),
    })
    before = state.data_version
    with patch('resolver.fetch_by_id') as by_id, patch('resolver.fetch_by_name') as by_name:
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'displayName': 'Silent Hill 2 (2001)'})
    assert_contract(r, GAMES['corrections']['success'])
    by_id.assert_not_called()
    by_name.assert_not_called()
    # The cached resolution survives…
    assert state.entries()[f'{ns}-original'].igdb_slug == 'silent-hill-2'
    # …but the derived caches are invalidated so the new name is served.
    assert state.data_version > before
    assert r.get_json()['name'] == 'Silent Hill 2 (2001)'


def test_a_correction_moving_onto_a_cached_game_reuses_its_data(client, tmp_corrections):
    # Pinning re-decides which game this is; that game's data is already here.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 9, 'astrobotanica', 'Astrobotanica'),
        f'{ns}-remake':   _entry(f'{ns}-remake', 1, 'silent-hill-2', 'Silent Hill 2',
                                 metacritic=89),
    })
    from igdb import IgdbResult
    pinned = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2',
                        data={}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=pinned), \
         patch('resolver.metacritic.fetch_metascore') as mc:
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1})
    mc.assert_not_called()
    assert r.get_json()['igdb']['metacritic'] == 89
    assert state.entries()[f'{ns}-original'].igdb_slug == 'silent-hill-2'
