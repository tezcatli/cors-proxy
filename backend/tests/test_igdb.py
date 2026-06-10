# IGDB has no public HTTP endpoint — its data is served inline by GET /games and
# GET /games/<slug>, and warmed in the background by games.py. Direct unit tests
# for the IGDB client internals (fetch_by_name, ranking, normalisation, etc.)
# live in test_igdb_core.py.
