import datetime
import os
import stat
import pytest
import corrections as _corr
from corrections import find_by_podcast, _find
from utils import make_slug


# ── Finding a name's correction ───────────────────────────────────────────────

@pytest.fixture
def shipped(tmp_corrections):
    import json
    tmp_corrections.write_text(json.dumps({'corrections': [
        {'podcast_name': 'Vendran Las Aves', 'search_name': 'Vendrán las aves'},
        {'podcast_name': 'Bioshock 1', 'igdb_id': 152660},
    ]}))
    _corr.load()


def test_a_name_finds_its_correction_by_its_slug(shipped):
    assert find_by_podcast('vendran  las AVES')['search_name'] == 'Vendrán las aves'
    assert find_by_podcast('Bioshock 1')['igdb_id'] == 152660
    # The slug is the identity: an unspaced « Bioshock1 » is another name.
    assert find_by_podcast('Bioshock1') is None
    assert find_by_podcast('Elden Ring') is None


def test_unmatched_slugs_flags_corrections_absent_from_the_feed(shipped):
    from corrections import unmatched_slugs
    assert unmatched_slugs(['bioshock-1', 'vendran-las-aves']) == []
    assert unmatched_slugs(['vendran-las-aves']) == ['bioshock-1']


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
    _corr._BY_SLUG[SLUG_MULTI] = DATED_CORRECTIONS   # through the module: load() replaces it
    yield
    del _corr._BY_SLUG[SLUG_MULTI]


@pytest.mark.parametrize('pub_date, expected', [
    ('2008-10-20', 'Game A'),            # its day: the dated entry, not the fallback
    ('2023-04-28', 'Game B'),
    ('2015-06-15', 'Game Fallback'),     # no day matches
    (None,         'Game Fallback'),     # undated episode
])
def test_a_dated_correction_wins_on_its_day_else_the_undated_one(inject_test_corrections, pub_date, expected):
    assert _find(SLUG_MULTI, pub_date and _pub_ts(pub_date))['search_name'] == expected


# ── corrections.json: schema validation ───────────────────────────────────────


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


def test_write_preserves_the_files_mode(tmp_corrections):
    # The dev container writes this file as root via mkstemp+os.replace, which
    # would otherwise leave it 0600 and root-owned — unreadable to the human who
    # has to `git diff` and commit it, breaking the whole point of the file.
    os.chmod(tmp_corrections, 0o644)
    _corr.upsert('Zelda', igdb_id=1)
    assert stat.S_IMODE(os.stat(tmp_corrections).st_mode) == 0o644
    assert _corr._read_raw() == [{'podcast_name': 'Zelda', 'igdb_id': 1}]


# ── upsert: merge semantics (pin and rename are independent decisions) ─────────

CT, SS = 'Chrono Trigger', 'Shogun Shodown'


@pytest.mark.parametrize('before, upserts, after', [
    # A new pin replaces the old one, at the same scope, whatever the spelling
    # (the last one written).
    ([], [(CT, {'igdb_id': 1}), ('chrono trigger', {'igdb_id': 2})],
     [{'podcast_name': 'chrono trigger', 'igdb_id': 2}]),
    # Renaming keeps the pin; pinning keeps the curator's name.
    ([], [(CT, {'igdb_id': 1}), (CT, {'display_name': 'CT (SNES)'})],
     [{'podcast_name': CT, 'igdb_id': 1, 'display_name': 'CT (SNES)'}]),
    ([{'podcast_name': CT, 'search_name': 'Guardians', 'display_name': 'CT (SNES)'}],
     [(CT, {'igdb_id': 2})],
     [{'podcast_name': CT, 'igdb_id': 2, 'display_name': 'CT (SNES)'}]),
    # An empty name drops the override; a name alone is an entry.
    ([], [(CT, {'igdb_id': 1, 'display_name': 'X'}), (CT, {'display_name': ''})],
     [{'podcast_name': CT, 'igdb_id': 1}]),
    ([], [('Les Sims', {'display_name': 'Les Sims'})],
     [{'podcast_name': 'Les Sims', 'display_name': 'Les Sims'}]),
    # A pin bypasses the search: its search_name would be dead config (and
    # _validate rejects the pair); a rename keeps it.
    ([{'podcast_name': SS, 'search_name': 'Été'}], [(SS, {'igdb_id': 42})],
     [{'podcast_name': SS, 'igdb_id': 42}]),
    ([{'podcast_name': SS, 'search_name': 'Été'}], [(SS, {'display_name': 'Été'})],
     [{'podcast_name': SS, 'search_name': 'Été', 'display_name': 'Été'}]),
])
def test_upsert_merges_into_the_entry_at_its_scope(tmp_corrections, before, upserts, after):
    import json
    tmp_corrections.write_text(json.dumps({'corrections': before}))
    _corr.load()
    for name, fields in upserts:
        _corr.upsert(name, **fields)
    assert _corr.CORRECTIONS == after


def test_upsert_with_nothing_to_write_raises(tmp_corrections):
    with pytest.raises(ValueError, match='nothing to write'):
        _corr.upsert('Chrono Trigger')
