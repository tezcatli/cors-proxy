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
- **`games.py`** — Blueprint at `/games`. In-memory structures rebuilt at startup; **no DB reads per request**. A background thread resolves game names against IGDB and writes to `igdb_cache` (pruned to live appearances on each feed re-parse). Catalog/feed JSON bodies + ETags are memoised by a monotonic `_data_version`. Key endpoints: `GET /games` (slim catalog, `igdb` field contains only `{ metacritic, coverImageId }`), `GET /games/<slug>` (full igdb + episodes), `GET /games/episodes` (full feed), `GET /games/episode?slug=<episode-slug>` (single episode with IGDB-resolved chapter annotations), `POST /games/refresh`, `POST /games/<slug>/igdb-refresh`, `GET /games/resolution-stream` (SSE).
- **`igdb.py`** — Internal IGDB helpers only (no public HTTP route). Looks up game metadata from IGDB API (Twitch OAuth) via a persistent `requests.Session`. Rate-limited to 4 req/s. `_resolve_canonical` resolves DLCs/versions to their parent game using inline nested fields in the query (no extra API call). `IgdbResult` includes an `is_child` flag set when the result was redirected to a parent. `fetch_time_to_beat(igdb_id)` is the IGDB `/game_time_to_beats` fallback for durée de vie.
- **`metacritic.py`** — Scrapes the real critic Metascore from the public Metacritic game page (JSON-LD `ratingValue`). No API; best-effort + gently rate-limited (~1 req/1.4 s), gated by `Config.METACRITIC_SCRAPE`. Any failure (404, Cloudflare block, parse error) returns `None` and the caller keeps IGDB's aggregate. `_resolve_one()` overrides the cached `metacritic` with this when found.
- **`hltb.py`** — HowLongToBeat main-story completion time via the unofficial `howlongtobeatpy` lib. No official API, so every failure path returns `None`; rate-limited (~1 req/1.2 s). Primary source for `timeToBeatHours`, with `igdb.fetch_time_to_beat` as fallback. The lib is an optional dep — if it isn't installed the import is swallowed and HLTB is skipped (IGDB fallback used).
- **`corrections.py`** — Static table mapping podcast game names to the right IGDB search term or ID. Each entry may include `hint_date` (exact episode pub_ts day match), `display_name` (display override), and `igdb_id` (bypass name search). Multiple entries per name are differentiated by `hint_date`; undated entries are fallbacks. `display_name` is applied at response time in `games.py`, not stored in the DB.
- **`db.py`** — SQLite at `backend/data/users.db`. WAL mode. Four tables: `users`, `invitations`, `reset_tokens`, `igdb_cache`. `igdb_cache` is keyed by **podcast_slug** (`make_slug(podcast_name) + '-' + episode.slug`, the RSS guid), one row per (game name, episode) pair. Columns: `igdb_id`, `igdb_slug` (IGDB's own slug, used for URL routing), `name` (canonical IGDB name), `igdb_data` (JSON blob), `is_child` (1 if resolved to a parent game). Loaded into memory at startup; only written when new IGDB resolutions arrive.
- **`config.py`** — All config from env vars; `Config.DEBUG` gates auth bypass and static file serving, `Config.METACRITIC_SCRAPE` gates the Metacritic scrape.

### Frontend (`frontend/`)

- **`src/lib/games.js`** — Thin API client for the `/games/*` and stream endpoints: `fetchCatalog()`, `fetchGameDetail(slug)`, `refreshCatalog()`, `refreshGameIgdb(slug)`, `fetchEpisodes()`, `fetchEpisodeDetail(episodeSlug)`, and `openResolutionStream()` (fetches a short-lived stream token, then opens the SSE `EventSource`). All use `igdb_slug` as the identifier. No XML parsing — all feed processing happens on the backend.
- **`src/lib/igdbCdn.js`** — One-liner helper that builds IGDB image CDN URLs (`igdbUrl(imageId, template)`).
- **`src/lib/platformIcons.js`** — Maps the backend's `platforms[].family` key (playstation/xbox/nintendo/pc/apple/android) to a monochrome brand-glyph SVG path (simple-icons, CC0) via `platformIconPath(family)`; unknown family → `null` (DetailView falls back to the lucide `Gamepad2` icon).
- **`src/lib/auth.js`** — JWT stored in `localStorage` under key `soj-auth-token`. `apiFetch()` attaches `Authorization: Bearer` header to every request and throws on non-2xx.
- **`src/stores/games.js`** — Central Pinia store. Loads `all` games from the catalog, exposes `filtered(query)` with sort (alpha / date / metacritic). When a user-initiated load reports `pending > 0` it opens an SSE resolution stream (`openResolutionStream`); each `resolved` event patches the matching store entry's `slug`/`igdb` in place (and migrates the player store's slug). A final `done` event reconciles the catalog once **without** re-arming SSE (`load(false)`), so a resolve that leaves `pending > 0` can't spin into a reload loop — background retries are owned by the server's periodic resolver.
- **`src/stores/player.js`** — Audio player state **and** listening-progress tracking. Two `localStorage` keys: `soj-player` (the resumable snapshot `{ current, currentTime }`, restored *paused* by `App.vue` on load — `restore()` sets a `restored` flag that drives the player's resume cue and is cleared on `play()`/`setPaused(false)`) and `soj-progress` (`progressMap`: key `` `${episodeSlug}|${chapterTs}` `` → `{ currentTime, chapterEnd, gameSlug, ts, savedAt }`). Progress is written on a 5 s `currentTime` debounce, on chapter change, on `play()`, and on `close()`; `_pruneProgressMap` (180-day TTL by `savedAt` + newest-500 cap) runs on load and after each write to keep it bounded. Reads: `liveProgress` (computed, the currently-playing target), `getEpisodeProgress(slug, ts)`, `getGameProgress(slug)` (most-recently-saved entry). **Single-worker note does not apply here — this is per-browser client state.**
- **`src/composables/useProgress.js`** — the one live-aware progress reader used by every consumer (`GameCard`, `EpisodeCard`, `EpisodeFeedCard`, `EpisodeView` chapter rows): `episodeProgress(episodeSlug, chapterTs)` and `gameProgress(gameSlug)` each return `{ pct, done }` (`done` at ≥ `PROGRESS_DONE_PCT`), checking the store's `liveProgress` first then the stored map. Views gate the bar on `pct > PROGRESS_MIN_PCT` and switch to the "listened" treatment when `done`. (Thresholds + `progressPct`/`formatTime` live in `lib/utils.js`.)
- **`src/composables/useEpisodePlayer.js`** — `playEp(ep)` builds the player payload and hands it to `playerStore.play()`. On tap it **resumes from saved progress**: it reads `getEpisodeProgress(ep.slug, startTs)` and, when the chapter is partway through (`progressPct` between `PROGRESS_MIN_PCT` and `PROGRESS_DONE_PCT`), seeks to the saved `currentTime` instead of the chapter start; an untouched or finished chapter restarts at `ep.timestampSeconds`. (This is the *tap* resume — distinct from `App.vue`'s reload resume via `soj-player`, which restores paused with the cue.)
- **`src/components/AudioPlayer.vue`** — owns the `<audio>` element and media-event wiring. A single persistent `loadedmetadata` handler (keyed off a module-scoped `_seekTarget` set in the `playVersion` watch) sets duration, seeks, and plays — not a per-play one-shot listener. A `buffering` ref (set on new `src`, on `waiting`; cleared on `playing`/`canplay`) drives a `Loader2` spinner on the play button while audio loads after a tap. Mobile-only collapsed affordances: a tap-to-toggle grab handle (`toggleCollapsed()`, a non-button `<div>` so the bottom-sheet drag still works) and a bottom-edge progress hairline; both are hidden ≥900px where the inline seek bar shows position.
- **`src/router.js`** — History-mode router at base `/silence/`. The `beforeEach` guard forwards `?reset=` and `?invite=` query params to `/login`, and redirects unauthenticated users to `/login`.

### In-memory state (`games.py`)

Core structures, all rebuilt from RSS + DB at startup. No per-request DB reads.

```
_cached_episodes   list[Episode]            source of truth; owns all Episode objects
_episode_index     dict[slug, Episode]      episode.slug AND url_slug → same Episode objects
_game_index        dict[name_slug, PodcastGame]   one entry per unique game name
_igdb_cache        dict[podcast_slug, IgdbEntry]  loaded from DB at startup
```

`_igdb_cache` is written whenever `_resolve_one()` completes (background thread or explicit refresh), and pruned to current appearances on each successful feed re-parse so it stays bounded. All other structures are read-only from the perspective of HTTP handlers.

**Derived response caches.** A monotonic `_data_version` (int) is bumped under `_state_lock` on every feed re-parse, IGDB resolution, and `igdb-refresh` delete. `_catalog_cache`/`_feed_cache` hold the *serialised* JSON body + ETag keyed by it (catalog also keys on `pending`), so repeat reads and 304 revalidations skip re-serialising/re-hashing; `_pending_cache` memoises the pending count per `(version, minute)`.

**IGDB resolution.** `_resolve_one()` resolves one appearance, then enriches it with external sources (real Metacritic score via `metacritic.fetch_metascore`, durée de vie via `hltb.fetch_time_to_beat` → IGDB fallback) before caching, and broadcasts an SSE `resolved` event; `_resolve_pending()` sweeps all not-fresh appearances (never-cached **or** older than `IGDB_TTL_HOURS`) then broadcasts `done`. The catalog `pending` count, the SSE endpoint, and the periodic retry (`_periodic_resolve`, every `RESOLVE_RETRY_MINUTES`) all share the same TTL-aware `_count_pending()` notion; the SSE endpoint starts a resolver when work is pending instead of emitting an instant `done` (otherwise the client would reload-loop).

**Single-worker constraint:** because this state lives in process memory (and SSE subscribers and the rate limiter are likewise in-process), prod must run gunicorn with `--workers 1` (see `backend/Dockerfile.prod`). Scaling to multiple workers silently breaks the cache, SSE fan-out, and rate limiting — move that state to shared storage (e.g. redis) first.

### Slug model

Slug types that coexist:

- **episode.slug** — the RSS `<guid>` (fallback: `make_slug(audio_url)`, then `make_slug(title)`). Stable internal episode identity and a key in `_episode_index`. Also embedded in `podcast_slug` and used as the player's progress-tracking key. **Not** used in URLs (guids are often raw URLs).
- **url_slug** — `make_slug(episode.title)`, de-duplicated with a numeric suffix on collision. Human-readable; the **only** slug used for episode routing (`/episode/:slug`). Also registered as a key in `_episode_index`, so `GET /games/episode?slug=` accepts either the url_slug or the guid (legacy/cached links). Serialised as `urlSlug`.
- **name_slug** — `make_slug(game_name)`. Key in `_game_index`. One `PodcastGame` per unique game name.
- **podcast_slug** — `make_slug(game_name) + '-' + episode.slug` (the guid). Primary key of `igdb_cache` (DB and memory). One `IgdbEntry` per (game name, episode) pair. Stored on `GameAppearance` for IGDB lookup.
- **igdb_slug** — IGDB's own URL slug (e.g. `indiana-jones-and-the-great-circle`). Stored in `IgdbEntry.igdb_slug`. Used for URL routing (`/games/<igdb_slug>`).

`make_slug` normalizes any run of non-alphanumeric chars to a single dash. IGDB slugs can contain `--` (e.g. `resident-evil-2--1`) which `make_slug` would destroy, so igdb_slug lookups always use the raw IGDB value, not `make_slug(slug)`.

### Shared contract

`contracts/api.json` declares expected HTTP status codes and response fields for every endpoint. Both the Python tests (`tests/contract.py`) and the JS integration tests (`tests/contract.js`) validate against this file — keep it in sync when adding or changing endpoints.

### Service worker

`frontend/sw.js` is registered by `main.js` at `/silence/sw.js` with scope `/silence/`. Cache invalidation on deploy is handled by the build-hash keyed cache name (the Vite `stampServiceWorker` plugin in `vite.config.js` replaces `__CACHE_VERSION__` with a hash of output bundles). The SW uses `skipWaiting()` + `clients.claim()` so the new version takes over immediately; `main.js` listens for `controllerchange` and reloads open tabs.

### Secrets

`backend_secrets.env` is git-ignored. Required keys: `JWT_SECRET`, `ADMIN_KEY`, `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET`, `RESET_BASE_URL`. SMTP keys are optional (links are logged to stdout when omitted). See `SETUP.md` for the full reference.
