"""
Corrections for games whose podcast name doesn't find the right IGDB entry.

**`corrections.json` is the single source of truth.** It is git-tracked, so a fix
is reviewed in a PR, survives a database wipe, and applies to every deployment.
This module only loads, validates and looks it up — plus writes it back for the
admin dashboard, which is a *dev-time* curation tool: in prod the file lives in
the read-only image layer (see `is_writable`), and corrections are curated
locally and committed.

Each entry requires:
  podcast_name  — the raw name extracted from the RSS. Matched on make_slug(),
                  so it must match the feed's exact wording ("MakeWay", not
                  "make way") or it silently matches nothing — `unmatched_slugs`
                  reports those at each feed re-parse.

Exactly one resolution strategy:
  igdb_id       — pin this IGDB id; bypasses the name search entirely
  search_name   — search IGDB with this instead of podcast_name
  (both is rejected: a pinned id short-circuits the search, so the search_name
  would be dead config.)

Optional scopes — an entry applies only where every scope it declares matches,
and the most specific matching entry wins:
  hint_date     — ISO date (YYYY-MM-DD). Applies only to an episode published on
                  that UTC day, and is passed to IGDB as the search date hint.
  podcast_id    — applies only to that podcast (e.g. the two shows covering
                  different games under one name).

Optional display:
  display_name  — override the shown name. Applied at response time in games.py,
                  independent of how the game resolved, so it composes with a pin.
"""
import datetime
import json
import os
import pathlib
import stat
import tempfile
import threading

from utils import make_slug

_PATH = pathlib.Path(__file__).parent / 'corrections.json'

_SCOPES  = ('hint_date', 'podcast_id')
_ALLOWED = {'podcast_name', 'search_name', 'igdb_id', 'display_name', *_SCOPES}

_lock: threading.Lock = threading.Lock()

CORRECTIONS: list[dict] = []
_BY_SLUG:    dict[str, list[dict]] = {}


# ── Load & validate ───────────────────────────────────────────────────────────

def _key(entry: dict) -> tuple:
    """An entry's identity: what it resolves for, at what scope. Keyed on the
    *slug*, not the raw name, so write-identity matches how lookup finds it — two
    spellings that slugify the same are one entry, and can't both land in the file
    to shadow each other by position."""
    return (make_slug(entry['podcast_name']), entry.get('hint_date') or '',
            entry.get('podcast_id') or '')


def _validate(entry: dict, index: int) -> None:
    """Reject an entry that can't mean what it says. The file is reviewed and
    test-covered, so failing loudly here beats silently ignoring a curator's
    intent at 3am six months later."""
    where = f'corrections.json[{index}]'
    if not isinstance(entry, dict):
        raise ValueError(f'{where}: entry must be an object')
    unknown = set(entry) - _ALLOWED
    if unknown:
        raise ValueError(f'{where}: unknown field(s) {sorted(unknown)}')
    if not entry.get('podcast_name'):
        raise ValueError(f'{where}: podcast_name is required')
    name = entry['podcast_name']
    if entry.get('igdb_id') and entry.get('search_name'):
        raise ValueError(
            f'{where} ({name!r}): igdb_id and search_name are mutually exclusive — '
            'a pinned id bypasses the search, so the search_name would never be read')
    if not entry.get('igdb_id') and not entry.get('search_name') and not entry.get('display_name'):
        raise ValueError(f'{where} ({name!r}): entry does nothing — needs igdb_id, '
                         'search_name or display_name')
    if entry.get('igdb_id') is not None and not isinstance(entry['igdb_id'], int):
        raise ValueError(f'{where} ({name!r}): igdb_id must be an integer')
    if entry.get('hint_date'):
        try:
            datetime.date.fromisoformat(entry['hint_date'])
        except ValueError as exc:
            raise ValueError(f'{where} ({name!r}): bad hint_date — {exc}') from None


def load() -> None:
    """(Re)read corrections.json into memory. Raises on a malformed file."""
    global CORRECTIONS, _BY_SLUG
    with _PATH.open(encoding='utf-8') as f:
        raw = json.load(f)
    entries = raw.get('corrections', [])
    by_slug: dict[str, list[dict]] = {}
    seen: dict[tuple, str] = {}
    for i, entry in enumerate(entries):
        _validate(entry, i)
        key = _key(entry)
        if key in seen:
            # Two entries for the same name at the same scope: lookup would pick
            # one by file position and silently ignore the other.
            raise ValueError(
                f'corrections.json[{i}] ({entry["podcast_name"]!r}): duplicate of '
                f'{seen[key]!r} — same name and scope, so one would never apply')
        seen[key] = entry['podcast_name']
        parsed = dict(entry)
        hd = entry.get('hint_date')
        parsed['_date'] = datetime.date.fromisoformat(hd) if hd else None
        by_slug.setdefault(make_slug(entry['podcast_name']), []).append(parsed)
    CORRECTIONS, _BY_SLUG = entries, by_slug


load()


# ── Lookup ────────────────────────────────────────────────────────────────────

def _scope_matches(c: dict, pub_ts, podcast_id: str) -> bool:
    """An entry applies when every scope it declares matches. An undeclared scope
    is a wildcard, so a bare entry is the fallback for the name."""
    # `_date` is derived by load(); parse on the fly for a dict that didn't come
    # through it (tests inject entries into _BY_SLUG directly).
    hint = c.get('_date') or (datetime.date.fromisoformat(c['hint_date'])
                              if c.get('hint_date') else None)
    if hint is not None:
        if pub_ts is None:
            return False
        if datetime.datetime.fromtimestamp(pub_ts, datetime.timezone.utc).date() != hint:
            return False
    if c.get('podcast_id') and c['podcast_id'] != podcast_id:
        return False
    return True


def _specificity(c: dict) -> int:
    return sum(1 for s in _SCOPES if c.get(s))


def _find(slug: str, pub_ts, podcast_id: str = ''):
    matching = [c for c in _BY_SLUG.get(slug, [])
                if _scope_matches(c, pub_ts, podcast_id)]
    if not matching:
        return None
    # Most specific wins: a dated, podcast-scoped entry beats a bare fallback.
    return max(matching, key=_specificity)


# Fields that change how an appearance resolves. display_name is deliberately
# excluded: it's applied at response time in games.py, so a rename must not
# trigger a re-resolution.
_SIG_FIELDS = ('igdb_id', 'search_name', 'hint_date')


def fingerprint(correction: dict | None) -> str:
    """Canonical signature of the resolution-affecting part of an entry.

    Stored on each cached IGDB row so a deployed instance can tell that a shipped
    corrections.json now rules differently on an appearance than when it was last
    resolved — and re-resolve exactly those. '' when no correction applies (or a
    display-only entry, which resolves identically to no correction at all)."""
    if not correction:
        return ''
    sig = {k: correction[k] for k in _SIG_FIELDS if correction.get(k)}
    return json.dumps(sig, sort_keys=True) if sig else ''


def find_by_podcast(podcast_name: str, pub_ts=None, podcast_id: str = ''):
    return _find(make_slug(podcast_name), pub_ts, podcast_id)


def unmatched_slugs(known_slugs) -> list[str]:
    """Correction name_slugs that match no game name in the feed.

    A correction is matched by `make_slug(podcast_name)`, so a spelling that
    doesn't match the feed's exact wording (e.g. "make way" vs the feed's
    "MakeWay") silently does nothing. Surfaced at startup so the typo is visible
    instead of looking like an IGDB miss.
    """
    known = set(known_slugs)
    return sorted(slug for slug in _BY_SLUG if slug not in known)


# ── Write (dev-time curation) ─────────────────────────────────────────────────

def is_writable() -> bool:
    """Whether this deployment can curate corrections at all.

    True in dev, where the repo is bind-mounted into the container. False in prod:
    the image layer is root-owned and the app runs as `appuser`, and a write would
    be discarded by the next build anyway. Callers surface this rather than
    letting the admin hit an opaque permission error.
    """
    return os.access(_PATH, os.W_OK)


def _write(entries: list[dict]) -> None:
    """Rewrite corrections.json atomically, sorted for a reviewable diff."""
    entries = sorted(entries, key=_key)
    body    = json.dumps({'corrections': entries}, indent=2, ensure_ascii=False) + '\n'
    try:
        before = os.stat(_PATH)
    except FileNotFoundError:
        before = None
    # Same directory so os.replace is atomic (no cross-device rename), and a
    # crash mid-write can't leave a truncated corrections file behind.
    fd, tmp = tempfile.mkstemp(dir=_PATH.parent, prefix='.corrections-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(body)
        if before is not None:
            # os.replace swaps in the temp file's inode wholesale, and mkstemp made
            # that 0600 owned by whoever is writing. Carry the original's mode and
            # owner over or the dev container (root) leaves corrections.json
            # root:root 0600 — unreadable to the human who has to `git diff` and
            # commit it, which is the point of keeping it in the repo at all.
            os.chmod(tmp, stat.S_IMODE(before.st_mode))
            try:
                os.chown(tmp, before.st_uid, before.st_gid)
            except OSError:
                pass    # not privileged to chown; the mode above still keeps it readable
        os.replace(tmp, _PATH)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise
    load()


_UNSET = object()


def upsert(podcast_name: str, podcast_id: str = '', *,
           igdb_id: int | None = None, display_name=_UNSET) -> dict:
    """Set the pin and/or the display name for a name at one scope.

    A *merge*, not a replace: pinning a game and renaming it are independent
    decisions, so neither may silently discard the other. `display_name=''`
    removes the override; omit it to leave it alone. Returns the written entry.
    Raises OSError if the file is read-only.
    """
    if igdb_id is None and display_name is _UNSET:
        raise ValueError('nothing to write — pass igdb_id and/or display_name')
    entry: dict = {'podcast_name': podcast_name}
    if podcast_id:
        entry['podcast_id'] = podcast_id

    with _lock:
        raw   = _read_raw()
        prior = next((c for c in raw if _key(c) == _key(entry)), None)
        if prior:
            entry = {**prior, **entry}
        if igdb_id is not None:
            entry['igdb_id'] = int(igdb_id)
            # A pin bypasses the search, so a search_name alongside it would be
            # dead config — _validate rejects the pair outright.
            entry.pop('search_name', None)
        if display_name is not _UNSET:
            if display_name:
                entry['display_name'] = display_name
            else:
                entry.pop('display_name', None)
        _validate(entry, -1)
        _write([c for c in raw if _key(c) != _key(entry)] + [entry])
    return entry


def remove(podcast_name: str, podcast_id: str = '') -> bool:
    """Drop the entry at this exact scope. Returns whether one was removed."""
    target = {'podcast_name': podcast_name}
    if podcast_id:
        target['podcast_id'] = podcast_id
    with _lock:
        raw  = _read_raw()
        kept = [c for c in raw if _key(c) != _key(target)]
        if len(kept) == len(raw):
            return False
        _write(kept)
    return True


def _read_raw() -> list[dict]:
    """The file's entries as written (no derived `_date` key)."""
    with _PATH.open(encoding='utf-8') as f:
        return json.load(f).get('corrections', [])
