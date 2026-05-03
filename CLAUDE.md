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

In dev, Flask (`DEBUG=true`) serves the built frontend from `silence/dist/` at `/silence/`. The Vite dev container watches `silence/` and writes to `dist/` via a volume mount — so `vite build --watch` runs inside the container, not the host.

### Testing

```bash
./test-backend.sh          # pytest inside Docker
./test-frontend.sh         # vitest unit tests inside Docker
./test-integration.sh      # vitest integration tests (spins up corsproxy-server)
```

Run a single backend test:
```bash
docker compose -f docker-compose.test.yml run --rm corsproxy-test pytest tests/test_auth.py::test_login_success
```

Run frontend unit tests locally (no Docker):
```bash
cd silence && npm test
# single file:
cd silence && npx vitest run tests/auth.test.js
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
Browser → Nginx (443) → /silence/* → static files (built Vue SPA)
                      → /auth/*    → corsproxy:8000 (Flask)
                      → /games/*   → corsproxy:8000 (Flask)
                      → /proxy     → corsproxy:8000 (Flask) → upstream URL
```

In dev, Flask handles everything directly on port 5000 (no Nginx).

### Backend (`corsproxy/`)

- **`app.py`** — Flask app factory. The `/proxy?url=` endpoint strips upstream CORS headers and re-adds its own. Auth is skipped entirely when `DEBUG=true`.
- **`auth.py`** — Blueprint at `/auth`: invite-token-based registration, login, password reset. All tokens (invite, reset, JWT) are random `secrets.token_urlsafe` strings stored in SQLite.
- **`games.py`** — Blueprint at `/games`. Fetches and parses the SOJ RSS feed; upserts games and episodes into SQLite; triggers background IGDB warming. Key endpoints: `GET /games` (slim catalog, igdb field contains only `{ metacritic }`), `GET /games/igdb?name=A&name=B` (full igdb for a list of game names, used by the grid's lazy loader), `GET /games/<slug>` (full igdb + episodes), `POST /games/refresh`, `POST /games/<slug>/igdb-refresh`.
- **`igdb.py`** — Internal IGDB helpers only (no public HTTP route). Looks up game cover art + metadata from IGDB API (Twitch OAuth). Results cached 30 days in the `igdb_cache` SQLite table. Rate-limited to 4 req/s with a threading lock. Called by `games.py` during warming.
- **`corrections.py`** — Static correction table mapping podcast game names to the right IGDB search term or ID. Consulted by `games.py` during IGDB warming when the raw podcast name would produce a wrong match.
- **`db.py`** — SQLite at `corsproxy/data/users.db`. Eight tables: `users`, `invitations`, `reset_tokens`, `igdb_cache`, `games_cache`, `games`, `episodes`, `podcast_name_map`. `get_db()` returns a context-manager connection with `row_factory = sqlite3.Row`.
- **`config.py`** — All config from env vars; `Config.DEBUG` gates auth bypass and static file serving.

### Frontend (`silence/`)

- **`src/lib/games.js`** — Thin API client for the `/games/*` endpoints. Five functions: `fetchCatalog()`, `fetchGameDetail(name)`, `refreshCatalog()`, `refreshGameIgdb(name)`, `fetchIgdb(names)`. No XML parsing — all feed processing happens on the backend.
- **`src/lib/igdbCdn.js`** — One-liner helper that builds IGDB image CDN URLs (`igdbUrl(imageId, template)`).
- **`src/lib/auth.js`** — JWT stored in `localStorage` under key `soj-auth-token`. `apiFetch()` attaches `Authorization: Bearer` header to every request and throws on non-2xx.
- **`src/stores/games.js`** — Central Pinia store. Loads `all` games from the slim catalog (`fetchCatalog`), exposes `filtered(query)` with sort (alpha / date / metacritic). `queueIgdb(name)` debounces card-visible events (50 ms) into a single `fetchIgdb` call, patching store entries with full igdb as the user scrolls.
- **`src/stores/player.js`** — Audio player state.
- **`src/router.js`** — History-mode router at base `/silence/`. The `beforeEach` guard forwards `?reset=` and `?invite=` query params to `/login`, and redirects unauthenticated users to `/login`.

### Lazy igdb loading

The grid catalog ships only `igdb: { metacritic }` per game (enough for sorting and score badges). Each `GameCard` mounts an `IntersectionObserver`; when the card enters the viewport and full igdb isn't loaded yet (`coverImageId` absent), it calls `gamesStore.queueIgdb(name)`. The store batches names over a 50 ms window and fires one `GET /games/igdb?name=A&name=B`, then patches the relevant store entries. Opening a game detail also upgrades its store entry to full igdb (via the `GET /games/<slug>` response), so revisiting the same detail within a session skips the igdb fetch.

### Shared contract

`contracts/api.json` declares expected HTTP status codes and response fields for every endpoint. Both the Python tests (`tests/contract.py`) and the JS integration tests (`tests/contract.js`) validate against this file — keep it in sync when adding or changing endpoints.

### Service worker

`silence/sw.js` exists but is intentionally **disabled**: `main.js` unregisters all service workers on every load. Do not re-enable it without addressing cache invalidation on deploy.

### Secrets

`corsproxy_secrets.env` is git-ignored. Required keys: `JWT_SECRET`, `ADMIN_KEY`, `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET`, `RESET_BASE_URL`. SMTP keys are optional (links are logged to stdout when omitted). See `SETUP.md` for the full reference.
