import datetime
import pytest
from corrections import find_by_podcast, find_by_slug, _find, _BY_SLUG
from utils import make_slug


# ── find_by_podcast ────────────────────────────────────────────────────────────

def test_find_by_podcast_known_name():
    c = find_by_podcast('Artic Eggs')
    assert c is not None
    assert c['search_name'] == 'Arctic Eggs'

def test_find_by_podcast_case_insensitive():
    c = find_by_podcast('artic eggs')
    assert c is not None

def test_find_by_podcast_no_match():
    assert find_by_podcast('Elden Ring') is None

def test_find_by_podcast_with_igdb_id():
    c = find_by_podcast('top spin 2k25')
    assert c is not None
    assert c['igdb_id'] == 282959

def test_find_by_podcast_search_name_overrides():
    c = find_by_podcast('shogun shodown')
    assert c is not None
    assert c['search_name'] == 'Shogun Showdown'

def test_find_by_podcast_search_name_none_when_not_needed():
    c = find_by_podcast('make way')
    assert c is not None
    assert c['search_name'] is None


# ── find_by_slug ───────────────────────────────────────────────────────────────

def test_find_by_slug_match():
    c = find_by_slug(make_slug('artic eggs'))
    assert c is not None
    assert c['search_name'] == 'Arctic Eggs'

def test_find_by_slug_no_match():
    assert find_by_slug('completely-unknown-game') is None

def test_find_by_slug_same_as_find_by_podcast():
    assert find_by_slug(make_slug('shogun shodown')) == find_by_podcast('shogun shodown')


# ── hint_date exact-date matching ─────────────────────────────────────────────

def _pub_ts(date_str):
    return int(datetime.datetime.fromisoformat(date_str)
               .replace(tzinfo=datetime.timezone.utc).timestamp())

DATED_CORRECTIONS = [
    {
        'podcast_name': '__test_multi__',
        'search_name':  'Game A',
        'hint_date':    '2008-10-20',
    },
    {
        'podcast_name': '__test_multi__',
        'search_name':  'Game B',
        'hint_date':    '2023-04-28',
    },
    {
        'podcast_name': '__test_multi__',
        'search_name':  'Game Fallback',
    },
]

SLUG_MULTI = make_slug('__test_multi__')


@pytest.fixture(autouse=False)
def inject_test_corrections():
    _BY_SLUG[SLUG_MULTI] = DATED_CORRECTIONS
    yield
    del _BY_SLUG[SLUG_MULTI]


def test_hint_date_exact_match(inject_test_corrections):
    c = _find(SLUG_MULTI, _pub_ts('2008-10-20'))
    assert c['search_name'] == 'Game A'

def test_hint_date_second_entry_match(inject_test_corrections):
    c = _find(SLUG_MULTI, _pub_ts('2023-04-28'))
    assert c['search_name'] == 'Game B'

def test_hint_date_no_match_falls_back_to_undated(inject_test_corrections):
    c = _find(SLUG_MULTI, _pub_ts('2015-06-15'))
    assert c['search_name'] == 'Game Fallback'

def test_hint_date_none_pub_ts_falls_back_to_undated(inject_test_corrections):
    c = _find(SLUG_MULTI, None)
    assert c['search_name'] == 'Game Fallback'

def test_hint_date_prefers_dated_over_undated(inject_test_corrections):
    c = _find(SLUG_MULTI, _pub_ts('2008-10-20'))
    assert c['search_name'] == 'Game A'   # not 'Game Fallback'


# ── display_name override ──────────────────────────────────────────────────────

DISPLAY_CORRECTIONS = [
    {
        'podcast_name': '__test_display__',
        'igdb_id':      99999,
        'display_name': 'My Custom Name',
    },
]

SLUG_DISPLAY = make_slug('__test_display__')


@pytest.fixture(autouse=False)
def inject_display_correction():
    _BY_SLUG[SLUG_DISPLAY] = DISPLAY_CORRECTIONS
    yield
    del _BY_SLUG[SLUG_DISPLAY]


def test_correction_display_name_field(inject_display_correction):
    c = _find(SLUG_DISPLAY, None)
    assert c is not None
    assert c['display_name'] == 'My Custom Name'
