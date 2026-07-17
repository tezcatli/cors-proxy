import datetime
import os
import stat
import pytest
from corrections import find_by_podcast, _find, _BY_SLUG
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
    # The feed writes it unspaced; a spaced "make way" must NOT match, since
    # make_slug maps the two to different slugs (makeway / make-way).
    c = find_by_podcast('MakeWay')
    assert c is not None
    assert c.get('search_name') is None
    assert c['igdb_id'] == 258230
    assert find_by_podcast('make way') is None


def test_unmatched_slugs_flags_corrections_absent_from_the_feed():
    from corrections import unmatched_slugs
    assert 'makeway' not in unmatched_slugs(['makeway', 'artic-eggs'])
    assert 'makeway' in unmatched_slugs(['artic-eggs'])


# ── _find (slug-level lookup) ─────────────────────────────────────────────────

def test_find_by_slug_match():
    c = _find(make_slug('artic eggs'), None)
    assert c is not None
    assert c['search_name'] == 'Arctic Eggs'

def test_find_by_slug_no_match():
    assert _find('completely-unknown-game', None) is None

def test_find_by_slug_same_as_find_by_podcast():
    assert _find(make_slug('shogun shodown'), None) == find_by_podcast('shogun shodown')


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


# ── corrections.json: schema validation ───────────────────────────────────────

import corrections as _corr


def _valid(**over):
    e = {'podcast_name': 'X', 'search_name': 'Y'}
    e.update(over)
    return e


@pytest.mark.parametrize('entry,expect', [
    ({'search_name': 'Y'},                              'podcast_name is required'),
    (_valid(igdb_id=1),                                 'mutually exclusive'),
    (_valid(search_name=None, igdb_id='nope'),          'must be an integer'),
    ({'podcast_name': 'X'},                             'does nothing'),
    (_valid(nonsense=1),                                'unknown field'),
    (_valid(hint_date='not-a-date'),                    'bad hint_date'),
])
def test_validate_rejects_incoherent_entries(entry, expect):
    entry = {k: v for k, v in entry.items() if v is not None}
    with pytest.raises(ValueError, match=expect):
        _corr._validate(entry, 0)


def test_validate_accepts_a_pin_and_a_search():
    _corr._validate({'podcast_name': 'X', 'igdb_id': 5}, 0)
    _corr._validate({'podcast_name': 'X', 'search_name': 'Y'}, 0)
    _corr._validate({'podcast_name': 'X', 'igdb_id': 5, 'podcast_id': 'fin-du-game'}, 0)


def test_the_shipped_corrections_file_is_valid():
    # The file is the source of truth and ships in the image; a malformed commit
    # must fail here, not at boot in prod.
    _corr.load()
    assert len(_corr.CORRECTIONS) > 0


def test_load_rejects_two_entries_for_the_same_name_and_scope(tmp_corrections):
    import json
    tmp_corrections.write_text(json.dumps({'corrections': [
        {'podcast_name': 'Zelda',  'search_name': 'A'},
        {'podcast_name': 'zelda ', 'search_name': 'B'},   # same slug, same scope
    ]}))
    with pytest.raises(ValueError, match='duplicate'):
        _corr.load()


def test_same_name_at_different_scopes_is_not_a_duplicate(tmp_corrections):
    import json
    tmp_corrections.write_text(json.dumps({'corrections': [
        {'podcast_name': 'Zelda', 'search_name': 'A'},
        {'podcast_name': 'Zelda', 'search_name': 'B', 'podcast_id': 'fin-du-game'},
        {'podcast_name': 'Zelda', 'search_name': 'C', 'hint_date': '2024-01-15'},
    ]}))
    _corr.load()
    assert _corr.find_by_podcast('Zelda')['search_name'] == 'A'
    assert _corr.find_by_podcast('Zelda', None, 'fin-du-game')['search_name'] == 'B'
    assert _corr.find_by_podcast('Zelda', _pub_ts('2024-01-15'))['search_name'] == 'C'


# ── corrections.json: writing ─────────────────────────────────────────────────

def test_upsert_replaces_the_entry_at_the_same_scope(tmp_corrections):
    _corr.upsert('Chrono Trigger', igdb_id=1)
    _corr.upsert('Chrono Trigger', igdb_id=2)
    assert _corr.CORRECTIONS == [{'podcast_name': 'Chrono Trigger', 'igdb_id': 2}]


def test_upsert_keeps_a_curated_display_name(tmp_corrections):
    import json
    tmp_corrections.write_text(json.dumps({'corrections': [
        {'podcast_name': 'Les gardiens de la galaxie', 'search_name': 'Guardians',
         'display_name': 'Les gardiens de la galaxie'},
    ]}))
    _corr.load()
    # Pinning an id is about resolution; it must not silently drop the curator's title.
    _corr.upsert('Les gardiens de la galaxie', igdb_id=19560)
    assert _corr.CORRECTIONS == [{'podcast_name': 'Les gardiens de la galaxie',
                                  'igdb_id': 19560,
                                  'display_name': 'Les gardiens de la galaxie'}]


def test_upsert_is_keyed_on_the_slug_not_the_spelling(tmp_corrections):
    _corr.upsert('Chrono Trigger', igdb_id=1)
    _corr.upsert('chrono trigger', igdb_id=2)      # same slug → one entry, not two
    assert len(_corr.CORRECTIONS) == 1
    assert _corr.CORRECTIONS[0]['igdb_id'] == 2


def test_remove_reports_whether_anything_went(tmp_corrections):
    _corr.upsert('Chrono Trigger', igdb_id=1)
    assert _corr.remove('Chrono Trigger') is True
    assert _corr.CORRECTIONS == []
    assert _corr.remove('Chrono Trigger') is False


def test_remove_respects_scope(tmp_corrections):
    _corr.upsert('Chrono Trigger', igdb_id=1)
    _corr.upsert('Chrono Trigger', 'fin-du-game', igdb_id=2)
    assert _corr.remove('Chrono Trigger', 'fin-du-game') is True
    assert _corr.CORRECTIONS == [{'podcast_name': 'Chrono Trigger', 'igdb_id': 1}]


def test_written_file_is_sorted_and_reviewable(tmp_corrections):
    _corr.upsert('Zelda', igdb_id=1)
    _corr.upsert('Astro Bot', igdb_id=2)
    _corr.upsert('Myst', igdb_id=3)
    names = [c['podcast_name'] for c in _corr.CORRECTIONS]
    assert names == ['Astro Bot', 'Myst', 'Zelda']      # stable diff, not append order
    assert tmp_corrections.read_text().endswith('}\n')  # trailing newline


def test_write_leaves_no_temp_files_behind(tmp_corrections):
    _corr.upsert('Zelda', igdb_id=1)
    assert [p.name for p in tmp_corrections.parent.iterdir()] == ['corrections.json']


def test_is_writable_true_when_the_file_can_be_written(tmp_corrections):
    assert _corr.is_writable() is True


@pytest.mark.skipif(os.geteuid() == 0,
                    reason='root bypasses permission bits, so a read-only file '
                           'still reports writable (the test container runs as root)')
def test_is_writable_false_on_a_read_only_file(tmp_corrections):
    # Stands in for prod, where corrections.json ships in the root-owned image
    # layer and the app runs as `appuser`.
    os.chmod(tmp_corrections, 0o444)
    try:
        assert _corr.is_writable() is False
    finally:
        os.chmod(tmp_corrections, 0o644)


def test_write_preserves_the_files_mode(tmp_corrections):
    # The dev container writes this file as root via mkstemp+os.replace, which
    # would otherwise leave it 0600 and root-owned — unreadable to the human who
    # has to `git diff` and commit it, breaking the whole point of the file.
    os.chmod(tmp_corrections, 0o644)
    _corr.upsert('Zelda', igdb_id=1)
    assert stat.S_IMODE(os.stat(tmp_corrections).st_mode) == 0o644
    assert _corr._read_raw() == [{'podcast_name': 'Zelda', 'igdb_id': 1}]


# ── upsert: merge semantics (pin and rename are independent decisions) ─────────

def test_upsert_rename_keeps_the_pin(tmp_corrections):
    _corr.upsert('Chrono Trigger', igdb_id=1)
    _corr.upsert('Chrono Trigger', display_name='Chrono Trigger (SNES)')
    assert _corr.CORRECTIONS == [{'podcast_name': 'Chrono Trigger', 'igdb_id': 1,
                                  'display_name': 'Chrono Trigger (SNES)'}]


def test_upsert_pin_keeps_the_display_name(tmp_corrections):
    _corr.upsert('Chrono Trigger', display_name='Chrono Trigger (SNES)')
    _corr.upsert('Chrono Trigger', igdb_id=2)
    assert _corr.CORRECTIONS == [{'podcast_name': 'Chrono Trigger',
                                  'display_name': 'Chrono Trigger (SNES)', 'igdb_id': 2}]


def test_upsert_empty_display_name_clears_the_override(tmp_corrections):
    _corr.upsert('Chrono Trigger', igdb_id=1, display_name='X')
    _corr.upsert('Chrono Trigger', display_name='')
    assert _corr.CORRECTIONS == [{'podcast_name': 'Chrono Trigger', 'igdb_id': 1}]


def test_upsert_display_name_only_is_a_valid_entry(tmp_corrections):
    # display_name alone is meaningful: rename a game the search already gets right.
    _corr.upsert('Les Sims', display_name='Les Sims')
    assert _corr.CORRECTIONS == [{'podcast_name': 'Les Sims', 'display_name': 'Les Sims'}]


def test_upsert_pin_drops_a_stale_search_name(tmp_corrections):
    import json
    tmp_corrections.write_text(json.dumps({'corrections': [
        {'podcast_name': 'Shogun Shodown', 'search_name': 'Shogun Showdown'},
    ]}))
    _corr.load()
    # A pin bypasses the search, so the search_name would be dead config —
    # _validate rejects the pair, so it must be dropped rather than kept.
    _corr.upsert('Shogun Shodown', igdb_id=42)
    assert _corr.CORRECTIONS == [{'podcast_name': 'Shogun Shodown', 'igdb_id': 42}]


def test_upsert_rename_preserves_a_search_name(tmp_corrections):
    import json
    tmp_corrections.write_text(json.dumps({'corrections': [
        {'podcast_name': 'Shogun Shodown', 'search_name': 'Shogun Showdown'},
    ]}))
    _corr.load()
    _corr.upsert('Shogun Shodown', display_name='Shogun Showdown')
    assert _corr.CORRECTIONS == [{'podcast_name': 'Shogun Shodown',
                                  'search_name': 'Shogun Showdown',
                                  'display_name': 'Shogun Showdown'}]


def test_upsert_with_nothing_to_write_raises(tmp_corrections):
    with pytest.raises(ValueError, match='nothing to write'):
        _corr.upsert('Chrono Trigger')


# ── Fingerprint (drives re-resolution when corrections.json ships) ─────────────

def test_fingerprint_none_and_empty_are_blank():
    assert _corr.fingerprint(None) == ''
    assert _corr.fingerprint({}) == ''


def test_fingerprint_display_only_is_blank():
    # A rename resolves identically to no correction, so it must not re-resolve.
    assert _corr.fingerprint({'podcast_name': 'X', 'display_name': 'Y'}) == ''


def test_fingerprint_display_name_does_not_change_the_signature():
    pin = {'podcast_name': 'X', 'igdb_id': 42}
    assert _corr.fingerprint(pin) == _corr.fingerprint({**pin, 'display_name': 'Y'})


def test_fingerprint_distinguishes_resolution_affecting_fields():
    sigs = {
        _corr.fingerprint({'igdb_id': 1}),
        _corr.fingerprint({'igdb_id': 2}),
        _corr.fingerprint({'search_name': 'Zelda'}),
        _corr.fingerprint({'search_name': 'Zelda', 'hint_date': '2024-01-01'}),
    }
    assert len(sigs) == 4          # all distinct
    assert '' not in sigs


def test_fingerprint_is_stable_regardless_of_key_order():
    a = _corr.fingerprint({'igdb_id': 1, 'hint_date': '2024-01-01'})
    b = _corr.fingerprint({'hint_date': '2024-01-01', 'igdb_id': 1})
    assert a == b
