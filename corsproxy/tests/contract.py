import json
from pathlib import Path

_path = Path(__file__).resolve().parents[2] / 'contracts' / 'api.json'
CONTRACT = json.loads(_path.read_text())
AUTH  = CONTRACT['auth']
IGDB  = CONTRACT['igdb']


def assert_contract(response, entry):
    assert response.status_code == entry['status'], \
        f"Expected HTTP {entry['status']}, got {response.status_code}"
    for field in entry.get('fields', []):
        body = response.get_json()
        assert field in body, f"Missing '{field}' in response: {body}"
