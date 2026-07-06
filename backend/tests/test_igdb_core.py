"""Unit tests for igdb.py core logic — no live API (mock `igdb._post`)."""
import datetime
from unittest.mock import patch

import requests

import igdb
from igdb import (
    _to_game_data, _rank_results, _resolve_canonical, _build_result, fetch_by_name,
)


class _Resp:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data if data is not None else []
    def json(self):
        return self._data
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _game(**over):
    g = {'id': 1, 'name': 'Test Game'}
    g.update(over)
    return g


# ── _to_game_data: metacritic gating ───────────────────────────────────────────

def test_metacritic_requires_three_ratings():
    assert _to_game_data(_game(aggregated_rating=84.6, aggregated_rating_count=5))['metacritic'] == 85
    assert _to_game_data(_game(aggregated_rating=84.6, aggregated_rating_count=2))['metacritic'] is None
    assert _to_game_data(_game())['metacritic'] is None


# ── _to_game_data: ESRB under both schemas ─────────────────────────────────────

def test_esrb_legacy_schema():
    assert _to_game_data(_game(age_ratings=[{'category': 1, 'rating': 11}]))['esrb'] == 'M'

def test_esrb_new_schema():
    assert _to_game_data(_game(age_ratings=[{'organization': 1, 'rating_category': 6}]))['esrb'] == 'M'

def test_esrb_skips_non_esrb_org():
    # A PEGI entry (category/org 2) then an ESRB Teen entry — should pick the ESRB one.
    g = _game(age_ratings=[{'category': 2, 'rating': 5}, {'organization': 1, 'rating_category': 5}])
    assert _to_game_data(g)['esrb'] == 'T'

def test_esrb_absent():
    assert _to_game_data(_game())['esrb'] is None


# ── _to_game_data: Steam URL under both schemas ────────────────────────────────

def test_steam_url_new_type_field():
    d = _to_game_data(_game(websites=[{'type': 13, 'url': 'https://store.steampowered.com/app/1'}]))
    assert d['steamUrl'].endswith('/app/1')

def test_steam_url_legacy_category_field():
    d = _to_game_data(_game(websites=[{'category': 13, 'url': 'https://store.steampowered.com/app/2'}]))
    assert d['steamUrl'].endswith('/app/2')

def test_steam_url_ignores_other_sites():
    assert _to_game_data(_game(websites=[{'type': 1, 'url': 'https://official.example'}]))['steamUrl'] is None


# ── _to_game_data: genres / platforms / companies / year ───────────────────────

def test_genres_capped_and_platforms_labelled():
    g = _game(
        genres=[{'name': 'Action'}, {'name': 'RPG'}, {'name': 'Indie'}, {'name': 'Extra'}],
        platforms=[
            {'name': 'PlayStation 5',          'abbreviation': 'PS5'},
            {'name': 'PC (Microsoft Windows)', 'abbreviation': 'PC'},
            {'name': 'Xbox Series X|S',        'abbreviation': 'Series X|S'},
        ],
    )
    d = _to_game_data(g)
    assert d['genres'] == ['Action', 'RPG', 'Indie']            # capped at 3
    # abbreviation label + brand-family key for the frontend icon
    assert d['platforms'] == [
        {'label': 'PS5',        'family': 'playstation'},
        {'label': 'PC',         'family': 'pc'},
        {'label': 'Series X|S', 'family': 'xbox'},
    ]

def test_developer_publisher_and_year():
    g = _game(
        first_release_date=int(datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc).timestamp()),
        involved_companies=[
            {'company': {'name': 'DevCo'}, 'developer': True,  'publisher': False},
            {'company': {'name': 'PubCo'}, 'developer': False, 'publisher': True},
        ],
    )
    d = _to_game_data(g)
    assert d['released'] == '2020'
    assert d['developer'] == 'DevCo' and d['publisher'] == 'PubCo'


# ── _rank_results ──────────────────────────────────────────────────────────────

def test_rank_results_exact_match_first():
    results = [{'name': 'Zelda II'}, {'name': 'The Legend of Zelda'}, {'name': 'Zelda'}]
    assert _rank_results(results, 'Zelda')[0]['name'] == 'Zelda'


# ── _resolve_canonical / _build_result ─────────────────────────────────────────

def test_canonical_redirects_to_version_parent():
    g = {'id': 2, 'name': 'Game GOTY', 'version_parent': {'id': 1, 'name': 'Game'}}
    assert _resolve_canonical(g)['id'] == 1

def test_canonical_redirects_dlc_to_parent():
    g = {'id': 2, 'name': 'DLC', 'category': 1, 'parent_game': {'id': 1, 'name': 'Base'}}
    assert _resolve_canonical(g)['id'] == 1

def test_canonical_keeps_remake_and_remaster():
    for cat in (8, 9):  # remake, remaster — intentional standalone titles
        g = {'id': 2, 'name': 'Remake', 'category': cat, 'parent_game': {'id': 1, 'name': 'Original'}}
        assert _resolve_canonical(g)['id'] == 2

def test_canonical_uses_game_type_when_category_absent():
    g = {'id': 2, 'name': 'Remaster', 'game_type': {'id': 9}, 'parent_game': {'id': 1, 'name': 'Original'}}
    assert _resolve_canonical(g)['id'] == 2

def test_build_result_is_child_flag():
    child = _build_result({'id': 2, 'name': 'DLC', 'category': 1, 'parent_game': {'id': 1, 'name': 'Base'}})
    assert child.id == 1 and child.is_child is True
    own = _build_result({'id': 3, 'name': 'Standalone'})
    assert own.id == 3 and own.is_child is False

def test_build_result_canonical_false_skips_redirect():
    # A pinned id must NOT be redirected to its parent (e.g. a remake IGDB models
    # as a "port" of an earlier version — the 7th Guest Remake → 7th Guest VR case).
    game = {'id': 394668, 'name': 'The 7th Guest Remake', 'slug': 'the-7th-guest-remake',
            'game_type': {'id': 11}, 'parent_game': {'id': 251565, 'name': 'The 7th Guest VR'}}
    # Default still redirects via parent_game (game_type 11 = port).
    assert _build_result(game).name == 'The 7th Guest VR'
    # canonical=False keeps the exact game.
    exact = _build_result(game, canonical=False)
    assert exact.id == 394668 and exact.name == 'The 7th Guest Remake' and exact.is_child is False


# ── fetch_by_name: date-window selection ───────────────────────────────────────

def test_fetch_by_name_prefers_in_window_result():
    pub = int(datetime.datetime(2020, 6, 1, tzinfo=datetime.timezone.utc).timestamp())
    in_win  = {'id': 1, 'name': 'Match', 'first_release_date': pub}
    out_win = {'id': 2, 'name': 'Match', 'first_release_date': pub - 5 * 365 * 24 * 3600}
    with patch('igdb._post', return_value=[out_win, in_win]):
        assert fetch_by_name('Match', pub).id == 1

def test_fetch_by_name_retries_without_date_window():
    pub = int(datetime.datetime(2020, 6, 1, tzinfo=datetime.timezone.utc).timestamp())
    old = {'id': 9, 'name': 'Retro', 'first_release_date': pub - 10 * 365 * 24 * 3600}

    def fake_post(body):
        # dated queries (containing the date filter) find nothing; the no-date retry finds it
        return [] if 'first_release_date >=' in body else [old]

    with patch('igdb._post', side_effect=fake_post):
        assert fetch_by_name('Retro', pub).id == 9

def test_fetch_by_name_none_when_no_results():
    with patch('igdb._post', return_value=[]):
        assert fetch_by_name('Nothing', None) is None


# ── _post retry/backoff ────────────────────────────────────────────────────────

def test_post_retries_on_5xx_then_succeeds():
    responses = [_Resp(503), _Resp(200, [{'id': 1, 'name': 'X'}])]
    calls = {'n': 0}
    def fake_session_post(*a, **k):
        r = responses[calls['n']]; calls['n'] += 1; return r
    with patch.object(igdb._session, 'post', side_effect=fake_session_post), \
         patch('igdb._get_token', return_value='tok'), \
         patch.object(igdb._rate_limiter, 'wait'), \
         patch('igdb.time.sleep'):
        out = igdb._post('fields *;')
    assert out == [{'id': 1, 'name': 'X'}]
    assert calls['n'] == 2   # one retry

def test_fields_generated_set_is_intact():
    # The generated _FIELDS must keep the full field set (bare + both expansions).
    fields = [f.strip() for f in igdb._FIELDS.replace('fields ', '', 1).rstrip('; ').split(',')]
    assert igdb._FIELDS.startswith('fields ') and igdb._FIELDS.endswith('; ')
    assert len(fields) == len(set(fields)) == 101  # 33 bare + 34 parent + 34 version
    for f in ('websites.type', 'age_ratings.rating_category'):
        assert f in fields
    for p in ('parent_game', 'version_parent'):
        assert f'{p}.id' in fields and f'{p}.{f}' in fields


def test_post_raises_after_exhausting_retries():
    def always_503(*a, **k):
        return _Resp(503)
    with patch.object(igdb._session, 'post', side_effect=always_503), \
         patch('igdb._get_token', return_value='tok'), \
         patch.object(igdb._rate_limiter, 'wait'), \
         patch('igdb.time.sleep'):
        try:
            igdb._post('fields *;')
            assert False, 'expected an error'
        except requests.HTTPError:
            pass
