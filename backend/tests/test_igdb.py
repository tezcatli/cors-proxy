# /igdb/game HTTP endpoint removed — IGDB data is now served exclusively through
# GET /games/igdb (DB read) and warmed in the background by games.py.
# Internal function tests (fetch_by_name, _normalize, etc.) to be added as
# direct unit tests in a future test_igdb_core.py.
