import pytest
from corrections import find_by_podcast, find_by_slug
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
