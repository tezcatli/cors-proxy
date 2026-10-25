"""`contracts/api.json`, read by the tests: one place for every response's shape.

An entry has a `status` and may say, of the body:
  fields  the keys it has. A key may be a path: `games[].igdb` is the `igdb` of
          every item of `games`, `[].slug` the `slug` of every item of a list body.
  only    {path: keys}: the object at `path` has exactly these keys.
  absent  paths that must not be there (`[].chapters`: no item has `chapters`).
A null on the way (an unresolved game's `igdb`) holds nothing below it.
"""
import json
from pathlib import Path

_path = Path(__file__).resolve().parents[2] / 'contracts' / 'api.json'
CONTRACT = json.loads(_path.read_text())
AUTH  = CONTRACT['auth']


def _at(value, path: str):
    """The values at `path` in `value`: every item of a `[]`, None skipped."""
    values = [value]
    for part in filter(None, path.replace('[]', '.[]').split('.')):
        if part == '[]':
            values = [item for v in values for item in v]
        else:
            values = [v[part] for v in values]
        values = [v for v in values if v is not None]
    return values


def _split(path: str) -> tuple[str, str]:
    parent, _, key = path.rpartition('.')
    return parent, key


def assert_contract(response, entry):
    assert response.status_code == entry['status'], \
        f"Expected HTTP {entry['status']}, got {response.status_code}"
    body = response.get_json()
    for field in entry.get('fields', []):
        parent, key = _split(field)
        for obj in _at(body, parent):
            assert key in obj, f"Missing '{field}' in response: {obj}"
    for path, keys in entry.get('only', {}).items():
        for obj in _at(body, path):
            assert set(obj) == set(keys), f"'{path}' should hold {sorted(keys)}, holds {sorted(obj)}"
    for field in entry.get('absent', []):
        parent, key = _split(field)
        for obj in _at(body, parent):
            assert key not in obj, f"'{field}' should not be in the response: {obj}"
