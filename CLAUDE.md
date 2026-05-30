# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Silence on Joue** companion app — a PWA that parses the SOJ podcast RSS feed, groups episodes by video game title, and lets users browse/play them. Access is invite-only via JWT auth.

## Stack

| Layer | Tech |
|---|---|
| Backend | Flask (Python), SQLite, Gunicorn (prod) |
| Frontend | Vue 3 + Pinia + Vue Router, Vite, Tailwind + DaisyUI |
| Reverse proxy | Nginx (prod only) |
| Runtime | Docker Compose for all environments |

## Commands

### Development

```bash
# Start the full dev stack (Flask hot-reload + Vite dev server)
docker compose -f docker-compose.dev.yml up --build
# Frontend: http://localhost:5000/silence  API: http://localhost:5000
```

In dev, Flask (`DEBUG=true`) proxies `/silence/` asset requests to the Vite dev server at `http://frontend:5173`, while still serving API routes itself. This ensures CSS and JS changes are served immediately from Vite rather than from stale built output.

### Testing

```bash
./test-backend.sh          # pytest inside Docker
./test-frontend.sh         # vitest unit tests inside Docker
./test-integration.sh      # vitest integration tests (spins up backend-server)
```

Run a single backend test:
```bash
docker compose -f docker-compose.test.yml run --rm backend-test pytest tests/test_auth.py::test_login_success
```

Run frontend unit tests locally (no Docker):
```bash
cd frontend && npm test
# single file:
cd frontend && npx vitest run tests/auth.test.js
```

### Production

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

### User management

```bash
# Invite a user (reads $ADMIN_KEY and $RESET_BASE_URL from env)
python invite.py alice@example.com
```

## Architecture

### Request flow

```
Browser → Nginx (443) → /silence/*       → static files (built Vue SPA)
                      → /silence/auth/*  → backend:8000 (Flask)
                      → /silence/games/* → backend:8000 (Flask)
```

In dev, Flask handles everything directly on port 5000 (no Nginx).

### Backend (`backend/`)

- **`app.py`** — Flask app factory. Registers the auth and games blueprints, an unauthenticated `GET /healthz` liveness probe, and (in `DEBUG=true`) the SPA/Vite-proxy static routes. Auth is skipped entirely when `DEBUG=true`. (The repo dir is still named `cors-proxy` for historical reasons — there is no longer a generic CORS-proxy endpoint.)
- **`auth.py`** — Blueprint at `/auth`: invite-token-based registration, login, password reset. All tokens (invite, reset, JWT) are random `secrets.token_urlsafe` strings stored in SQLite.
- **`models.py`** — Dataclasses shared across the backend: `Chapter`, `GameMention`, `Episode`, `GameAppearance`, `PodcastGame`, `IgdbEntry`. No logic.
- **`rss.py`** — Pure RSS feed parsing (no I/O, no state). Public API: `parse_feed(xml_bytes) -> list[Episode]`, `extract_game_names(title)`, `extract_legacy_names(title)`.
- **`games.py`** — Blueprint at `/games`. Four in-memory structures rebuilt at startup; **no DB reads per request**. A background thread resolves game names against IGDB and writes to `igdb_cache`. Key endpoints: `GET /games` (slim catalog, `igdb` field contains only `{ metacritic }`), `GET /games/igdb?slug=A&slug=B` (full igdb for a list of slugs), `GET /games/<slug>` (full igdb + episodes), `GET /games/episode?slug=<episode-slug>` (single episode with IGDB-resolved chapter annotations), `POST /games/refresh`, `POST /games/<slug>/igdb-refresh`.
- **`igdb.py`** — Internal IGDB helpers only (no public HTTP route). Looks up game metadata from IGDB API (Twitch OAuth) via a persistent `requests.Session`. Rate-limited to 4 req/s. `_resolve_canonical` resolves DLCs/versions to their parent game using inline nested fields in the query (no extra API call). `IgdbResult` includes an `is_child` flag set when the result was redirected to a parent.
- **`corrections.py`** — Static table mapping podcast game names to the right IGDB search term or ID. Each entry may include `hint_date` (exact episode pub_ts day match), `display_name` (display override), and `igdb_id` (bypass name search). Multiple entries per name are differentiated by `hint_date`; undated entries are fallbacks. `display_name` is applied at response time in `games.py`, not stored in the DB.
- **`db.py`** — SQLite at `backend/data/users.db`. WAL mode. Four tables: `users`, `invitations`, `reset_tokens`, `igdb_cache`. `igdb_cache` is keyed by **podcast_slug** (`make_slug(podcast_name) + '-' + YYYYMMDD`), one row per (game name, episode date) pair. Columns: `igdb_id`, `igdb_slug` (IGDB's own slug, used for URL routing), `name` (canonical IGDB name), `igdb_data` (JSON blob), `is_child` (1 if resolved to a parent game). Loaded into memory at startup; only written when new IGDB resolutions arrive.
- **`config.py`** — All config from env vars; `Config.DEBUG` gates auth bypass and static file serving.

### Frontend (`frontend/`)

- **`src/lib/games.js`** — Thin API client for the `/games/*` endpoints. Five functions: `fetchCatalog()`, `fetchGameDetail(slug)`, `refreshCatalog()`, `refreshGameIgdb(slug)`, `fetchIgdb(slugs)`. All use `igdb_slug` as the identifier. No XML parsing — all feed processing happens on the backend.
- **`src/lib/igdbCdn.js`** — One-liner helper that builds IGDB image CDN URLs (`igdbUrl(imageId, template)`).
- **`src/lib/auth.js`** — JWT stored in `localStorage` under key `soj-auth-token`. `apiFetch()` attaches `Authorization: Bearer` header to every request and throws on non-2xx.
- **`src/stores/games.js`** — Central Pinia store. Loads `all` games from the slim catalog, exposes `filtered(query)` with sort (alpha / date / metacritic). `queueIgdb(slug)` debounces card-visible events (50 ms) into a single `fetchIgdb` call, patching store entries with full igdb as the user scrolls.
- **`src/stores/player.js`** — Audio player state.
- **`src/router.js`** — History-mode router at base `/silence/`. The `beforeEach` guard forwards `?reset=` and `?invite=` query params to `/login`, and redirects unauthenticated users to `/login`.

### In-memory state (`games.py`)

Four structures, all rebuilt from RSS + DB at startup. No per-request DB reads.

```
_cached_episodes   list[Episode]            source of truth; owns all Episode objects
_episode_index     dict[slug, Episode]      episode.slug → same Episode objects
_game_index        dict[name_slug, PodcastGame]   one entry per unique game name
_igdb_cache        dict[podcast_slug, IgdbEntry]  loaded from DB at startup
```

`_igdb_cache` is written whenever `_resolve_one()` completes (background thread or explicit refresh). All other structures are read-only from the perspective of HTTP handlers.

**Single-worker constraint:** because this state lives in process memory (and SSE subscribers and the rate limiter are likewise in-process), prod must run gunicorn with `--workers 1` (see `backend/Dockerfile.prod`). Scaling to multiple workers silently breaks the cache, SSE fan-out, and rate limiting — move that state to shared storage (e.g. redis) first.

### Slug model

Three slug types coexist:

- **episode_slug** — `make_slug(episode.title)`. Key in `_episode_index`. Used by `GET /games/episode?slug=`.
- **name_slug** — `make_slug(game_name)`. Key in `_game_index`. One `PodcastGame` per unique game name.
- **podcast_slug** — `make_slug(game_name) + '-' + YYYYMMDD`. Primary key of `igdb_cache` (DB and memory). One `IgdbEntry` per (game name, episode date) pair. Stored on `GameAppearance` for IGDB lookup.
- **igdb_slug** — IGDB's own URL slug (e.g. `indiana-jones-and-the-great-circle`). Stored in `IgdbEntry.igdb_slug`. Used for URL routing (`/games/<igdb_slug>`).

`make_slug` normalizes any run of non-alphanumeric chars to a single dash. IGDB slugs can contain `--` (e.g. `resident-evil-2--1`) which `make_slug` would destroy, so igdb_slug lookups always use the raw IGDB value, not `make_slug(slug)`.

### Shared contract

`contracts/api.json` declares expected HTTP status codes and response fields for every endpoint. Both the Python tests (`tests/contract.py`) and the JS integration tests (`tests/contract.js`) validate against this file — keep it in sync when adding or changing endpoints.

### Service worker

`frontend/sw.js` is registered by `main.js` at `/silence/sw.js` with scope `/silence/`. Cache invalidation on deploy is handled by the build-hash keyed cache name (the Vite `stampServiceWorker` plugin in `vite.config.js` replaces `__CACHE_VERSION__` with a hash of output bundles). The SW uses `skipWaiting()` + `clients.claim()` so the new version takes over immediately; `main.js` listens for `controllerchange` and reloads open tabs.

### Secrets

`backend_secrets.env` is git-ignored. Required keys: `JWT_SECRET`, `ADMIN_KEY`, `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET`, `RESET_BASE_URL`. SMTP keys are optional (links are logged to stdout when omitted). See `SETUP.md` for the full reference.
