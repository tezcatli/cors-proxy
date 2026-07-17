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
- **`auth.py`** — Blueprint at `/auth`: invite-token-based registration, login, password reset. All tokens (invite, reset, JWT) are random `secrets.token_urlsafe` strings stored in SQLite. `require_admin()` gates the admin routes in `games.py`; it re-reads `users.is_admin` from the DB on every call (the JWT's `admin` claim is cosmetic — it only decides whether the SPA shows the admin UI — so a demotion applies immediately instead of at token expiry). Promotion is manual SQL (see SETUP.md).
- **`models.py`** — Dataclasses shared across the backend: `Chapter`, `GameMention`, `Episode`, `GameAppearance`, `PodcastGame`, `IgdbEntry`. No logic.
- **`rss.py`** — Pure RSS feed parsing (no I/O, no state). Public API: `parse_feed(xml_bytes) -> list[Episode]`, `extract_game_names(title)`, `extract_legacy_names(title)`.
- **`games.py`** — Blueprint at `/games`. In-memory structures rebuilt at startup; **no DB reads per request**. A background thread resolves game names against IGDB and writes to `igdb_cache` (pruned to live appearances on each feed re-parse). Catalog/feed JSON bodies + ETags are memoised by a monotonic `_data_version`. Key endpoints: `GET /games` (slim catalog, `igdb` field contains only `{ metacritic, coverImageId }`), `GET /games/<slug>` (full igdb + episodes + `nameSlugs`), `GET /games/episodes` (full feed), `GET /games/episode?slug=<episode-slug>` (single episode with IGDB-resolved chapter annotations), `POST /games/refresh`, `POST /games/<slug>/igdb-refresh`, `GET /games/resolution-stream` (SSE). Admin-only (`require_admin`): `GET /games/resolution-stats` (per-podcast figures + **every** group as `games`, each with a `status` of resolved/suspect/unresolved — classified server-side, filtered client-side, so a correctly-resolved game stays reachable; ~860 KB, admin-only, uncached), `GET /games/igdb-search?q=` (picker), `PUT`/`DELETE /games/corrections` (writes corrections.json; 409 where it's read-only), `POST /games/podcasts/<podcast_id>/igdb-refresh` (purge + background re-sweep of one show).
  `PUT /games/corrections` takes `igdbId` and/or `displayName` (at least one). **A rename must not re-resolve**: `display_name` is applied at response time by `_group_display_name`, so changing it only bumps `_data_version` (`_bump_version`) — purging would burn a round of IGDB + Metacritic + HLTB calls to arrive at the same entry. Only an `igdbId` change takes the `_reresolve` path.
- **`igdb.py`** — Internal IGDB helpers only. Looks up game metadata from IGDB API (Twitch OAuth) via a persistent `requests.Session`. Rate-limited to 4 req/s. `_resolve_canonical` resolves DLCs/versions to their parent game using inline nested fields in the query (no extra API call). `IgdbResult` includes an `is_child` flag set when the result was redirected to a parent. `fetch_time_to_beat(igdb_id)` is the IGDB `/game_time_to_beats` fallback for durée de vie. `fetch_by_name(name, pub_ts)` filters/prefers releases in a window around `pub_ts`; called with `pub_ts=None` it instead breaks name-score ties toward the **earliest** release (`_rank_results(prefer_earliest=)`), since IGDB lists ports and re-releases under the identical name. `search_games(q)` backs the admin picker: raw IGDB matches with release years, no window, no canonical redirect, no ranking — a human is choosing.
- **`metacritic.py`** — Scrapes the real critic Metascore from the public Metacritic game page (JSON-LD `ratingValue`). No API; best-effort + gently rate-limited (~1 req/1.4 s), gated by `Config.METACRITIC_SCRAPE`. Any failure (404, Cloudflare block, parse error) returns `None` and the caller keeps IGDB's aggregate. `_resolve_one()` overrides the cached `metacritic` with this when found.
- **`hltb.py`** — HowLongToBeat main-story completion time via the unofficial `howlongtobeatpy` lib. No official API, so every failure path returns `None`; rate-limited (~1 req/1.2 s). Primary source for `timeToBeatHours`, with `igdb.fetch_time_to_beat` as fallback. The lib is an optional dep — if it isn't installed the import is swallowed and HLTB is skipped (IGDB fallback used).
- **`corrections.json` + `corrections.py`** — **The single source of truth for name→IGDB corrections.** The JSON file holds the data (git-tracked: reviewed in a PR, survives a DB wipe, applies to every deployment); the module loads, validates, looks up and writes it. There is deliberately **no second store** — an earlier design had a `resolution_overrides` DB table alongside this, which duplicated the `igdb_id` pin and needed a precedence rule; the file won because a DB row is invisible to review and dies with the volume.
  - Entry = `podcast_name` + exactly one of `igdb_id` (pin, bypasses the search) or `search_name` (search this instead); optional `display_name` (applied at response time in `games.py`, so it composes with a pin), and optional **scopes** `hint_date` (episode published that UTC day) and `podcast_id`. An entry applies when every scope it declares matches; the most specific match wins (`_specificity`), so a bare entry is the name's fallback.
  - `load()` **fails loudly** on an incoherent entry (unknown field, `igdb_id`+`search_name` together — the search would be dead config — or two entries sharing a name *and* scope, where one could never apply). A test asserts the shipped file loads, so a bad commit fails CI rather than the prod container.
  - Entries are matched by `make_slug(podcast_name)`, so a spelling that doesn't match the feed's exact wording silently does nothing — `unmatched_slugs()` logs those at each feed re-parse, and `_key()` uses the slug too so write-identity matches read-identity.
  - `upsert(podcast_name, podcast_id='', *, igdb_id=None, display_name=_UNSET)` **merges** rather than replaces: pinning a game and renaming it are independent decisions, so neither may discard the other. Setting `igdb_id` drops any `search_name` (a pin bypasses the search, and `_validate` rejects the pair); `display_name=''` clears the override, omitting it leaves it alone.
  - **Writing is a dev-time activity.** `is_writable()` is True in dev (the repo is bind-mounted into the container) and False in prod (`COPY . .` bakes the file into a root-owned image layer and the app runs as `appuser`; a write would be permission-denied *and* discarded on the next build). The admin endpoints 409 when it's False. `_write()` is atomic (temp + `os.replace`) and **carries the original file's mode/owner across** — `mkstemp` makes a 0600 file owned by the writer, so without that the dev container (root) leaves `corrections.json` root:root 0600 and the human can't `git diff` or commit it.
- **`podcasts.py`** — The feed registry. Each `Podcast` carries its feed URL, the title→game-name extractor for that show's title convention, and `use_date_hint`: whether the episode's publication date is evidence of *the game's* release date. True for Silence on Joue (covers new releases); **False for Fin du Game**, a retrospective show where the date window would resolve a 1997 game to an unrelated 2026 release. Feed URLs are env-overridable (`<ID>_FEED_URL`).
- **`db.py`** — SQLite at `backend/data/users.db`. WAL mode. Four tables: `users` (incl. `is_admin`), `invitations`, `reset_tokens`, `igdb_cache`. `igdb_cache` is keyed by **podcast_slug** (`make_slug(podcast_name) + '-' + episode.slug`, the RSS guid), one row per (game name, episode) pair. Columns: `igdb_id`, `igdb_slug` (IGDB's own slug, used for URL routing), `name` (canonical IGDB name), `igdb_data` (JSON blob), `is_child` (1 if resolved to a parent game). Loaded into memory at startup; only written when new IGDB resolutions arrive.
- **`config.py`** — All config from env vars; `Config.DEBUG` gates auth bypass and static file serving, `Config.METACRITIC_SCRAPE` gates the Metacritic scrape.

### Frontend (`frontend/`)

- **`src/lib/games.js`** — Thin API client for the `/games/*` and stream endpoints: `fetchCatalog()`, `fetchGameDetail(slug)`, `refreshCatalog()`, `refreshGameIgdb(slug)`, `fetchEpisodes()`, `fetchEpisodeDetail(episodeSlug)`, and `openResolutionStream()` (fetches a short-lived stream token, then opens the SSE `EventSource`). Admin-only: `fetchResolutionStats()`, `searchIgdb(q)`, `setCorrection()`/`deleteCorrection()`, `refreshPodcastIgdb(id)`. All use `igdb_slug` as the identifier. No XML parsing — all feed processing happens on the backend.
- **`src/lib/igdbCdn.js`** — One-liner helper that builds IGDB image CDN URLs (`igdbUrl(imageId, template)`).
- **`src/lib/platformIcons.js`** — Maps the backend's `platforms[].family` key (playstation/xbox/nintendo/pc/apple/android) to a monochrome brand-glyph SVG path (simple-icons, CC0) via `platformIconPath(family)`; unknown family → `null` (DetailView falls back to the lucide `Gamepad2` icon).
- **`src/lib/auth.js`** — JWT stored in `localStorage` under key `soj-auth-token`. `apiFetch()` attaches `Authorization: Bearer` header to every request and throws on non-2xx. `isAdmin()` reads the token's `admin` claim to show/hide admin UI only — never a security boundary (the server re-checks the DB).
- **`src/pages/ResolutionStatsPage.vue`** — Admin console at `/admin/resolution` (lazy-loaded; router `meta.admin` + `isAdmin()` guard). **The app's only desktop-first, dense surface** — its job is scanning ~1660 rows and comparing two names, so filters sit inline as `.tab-group` segmented controls rather than behind popovers, and sorting lives on the column headers (`setSort`'s click-again-to-flip idiom). Each row is the confrontation the page exists to judge: podcast name → IGDB name, with the cover as the fastest wrong-match detector and a left accent bar for status (green/amber/red from the score palette). Reuses the catalogue's two perf measures — a module-level `Intl.Collator` and a 140 ms query debounce — plus `useInfiniteScroll` (pageSize 80, `resetKey`); that's incremental reveal, not virtualization, so a fully-scrolled unfiltered list is ~1660 live rows. Structure copies DetailView's **fixed shell + inner scroller**: `.back-pill` is `position: absolute`, so a page that scrolls its own root scrolls the pill away. Table CSS stays scoped — SFC scoped styles code-split with the lazy chunk, keeping admin CSS out of the bundle every reader downloads. Shows a banner while `pending > 0` (a half-swept cache reads exactly like a quality problem) and goes read-only when `writable` is false.
  **`games._is_suspect` is tuned for signal, not rigour**: a false positive buries the real misses, while a miss is still fixable from the game's own page — so it passes spacing (`Astrobot`/`Astro Bot`), numeral style (`Hades 2`/`Hades II`, via `_numerals`), subtitles, word order and plurals (word overlap ≥ `_SUSPECT_OVERLAP`), and a row already ruled on in corrections.json (`_correction_for`, surfaced as `corrected`) is dropped from the queue. Tuning against the live catalogue took it from 68 mostly-noise rows to ~50 mostly-real ones. Known residual false positives: abbreviations (`GTA V` → `Grand Theft Auto V`) and French titles (`Le Vaillant Petit Page` → `The Plucky Squire`).
- **`src/components/IgdbPickerModal.vue`** — Two independent decisions, separated in the UI: « Nom affiché » (writes `display_name`; saving it alone costs no IGDB call) and the IGDB picker below it (writes `igdb_id`). Debounced search with stale responses dropped by sequence number. Offers a podcast scope selector only when the game spans both shows. Also reachable from `DetailView` (wrench icon), but only when the entry maps to exactly one podcast name. **A correction is keyed by one `podcast_name`**, so for an entry merging several spellings the picker warns that only that spelling moves; `_group_summary` reports such a group under its *resolving* (best-member) name and lists every `nameSlugs` behind it, rather than picking one by dict order.
- **`src/stores/games.js`** — Central Pinia store. Loads `all` games from the catalog, exposes `filtered(query)` with sort (alpha / date / metacritic) and a `selectedPodcast` filter (persisted to `soj-podcast-filter`). That podcast choice is shared with the Épisodes tab: `EpisodesFeed` filters on `ep.podcast?.id` and `AppHeader` shows the Podcast group of the popover on both tabs (sort + « résolus uniquement » stay catalog-only). When a user-initiated load reports `pending > 0` it opens an SSE resolution stream (`openResolutionStream`); each `resolved` event patches the matching store entry's `slug`/`igdb` in place (and migrates the player store's slug). A final `done` event reconciles the catalog once **without** re-arming SSE (`load(false)`), so a resolve that leaves `pending > 0` can't spin into a reload loop — background retries are owned by the server's periodic resolver.
- **`src/stores/player.js`** — Audio player state **and** listening-progress tracking. Two `localStorage` keys: `soj-player` (the resumable snapshot `{ current, currentTime }`, restored *paused* by `App.vue` on load — `restore()` sets a `restored` flag that drives the player's resume cue and is cleared on `play()`/`setPaused(false)`) and `soj-progress` (`progressMap`: key `` `${episodeSlug}|${chapterTs}` `` → `{ currentTime, chapterEnd, gameSlug, ts, savedAt }`). Progress is written on a 5 s `currentTime` debounce, on chapter change, on `play()`, and on `close()`; `_pruneProgressMap` (180-day TTL by `savedAt` + newest-500 cap) runs on load and after each write to keep it bounded. Reads: `liveProgress` (computed, the currently-playing target), `getEpisodeProgress(slug, ts)`, `getGameProgress(slug)` (most-recently-saved entry), `getEpisodeLatestProgress(slug)` (newest-`savedAt` entry across all chapters of an episode), and `resumeTimeFor(slug, startTs)` (the central tap-resume rule: returns the saved `currentTime` when that chapter is partway through — `progressPct` between `PROGRESS_MIN_PCT` and `PROGRESS_DONE_PCT` — else `startTs`). **Single-worker note does not apply here — this is per-browser client state.**
- **`src/composables/useProgress.js`** — the one live-aware progress reader used by every consumer (`GameCard`, `EpisodeCard`, `EpisodeFeedCard`, `EpisodeView` chapter rows): `episodeProgress(episodeSlug, chapterTs)` and `gameProgress(gameSlug)` each return `{ pct, done }` (`done` at ≥ `PROGRESS_DONE_PCT`), checking the store's `liveProgress` first then the stored map. Views gate the bar on `pct > PROGRESS_MIN_PCT` and switch to the "listened" treatment when `done`. (Thresholds + `progressPct`/`formatTime` live in `lib/utils.js`.)
- **`src/composables/useEpisodePlayer.js`** — `playEp(ep)` builds the player payload and hands it to `playerStore.play()`. On tap it **resumes from saved progress** by setting `ts: playerStore.resumeTimeFor(ep.slug, ep.timestampSeconds || 0)` — the resume rule lives in the store so episode cards, `EpisodeView` chapter rows, and the "Reprendre" button all behave identically (partway → saved `currentTime`; untouched/finished → chapter start). (This is the *tap* resume — distinct from `App.vue`'s reload resume via `soj-player`, which restores paused with the cue.)
- **`src/components/AudioPlayer.vue`** — owns the `<audio>` element and media-event wiring. A single persistent `loadedmetadata` handler (keyed off a module-scoped `_seekTarget` set in the `playVersion` watch) sets duration, seeks, and plays — not a per-play one-shot listener. A `buffering` ref (set on new `src`, on `waiting`; cleared on `playing`/`canplay`) drives a `Loader2` spinner on the play button while audio loads after a tap. Mobile-only collapsed affordances: a tap-to-toggle grab handle (`toggleCollapsed()`, a non-button `<div>` so the bottom-sheet drag still works) and a bottom-edge progress hairline; both are hidden ≥900px where the inline seek bar shows position.
- **`src/composables/useMediaSession.js`** — Wires the browser MediaSession API (lock-screen / OS media controls) to the player store and the `<audio>` element, feature-guarded so it's inert where unavailable. `buildMetadata()` keeps the OS card in sync with the **current chapter**: `title` is the chapter title whenever in a chapter (even one with no art), `artist` the episode name, plus a `chapterInformation` array. `currentArtwork()` mirrors `AudioPlayer`'s `playerCoverSrc` resolution — chapter cover → episode image in a chapter, launch-game cover → episode image otherwise. `syncMediaSessionMeta()` reassigns a **fresh** `MediaMetadata` for reliable cross-browser repaint, and watches on `currentChapter` / `episodeImageUrl` re-sync it. `previoustrack`/`nexttrack` seek between chapters (only registered when the episode has chapters).
- **`src/router.js`** — History-mode router at base `/silence/`. The `beforeEach` guard forwards `?reset=` and `?invite=` query params to `/login`, redirects unauthenticated users to `/login`, and bounces non-admins off `meta.admin` routes to `/`.

### In-memory state (`games.py`)

Core structures, all rebuilt from RSS + DB at startup. No per-request DB reads.

```
_cached_episodes   list[Episode]            source of truth; owns all Episode objects
_episode_index     dict[slug, Episode]      episode.slug AND url_slug → same Episode objects
_game_index        dict[name_slug, PodcastGame]   one entry per unique game name
_igdb_cache        dict[podcast_slug, IgdbEntry]  loaded from DB at startup
```

Corrections are **not** in this list: they live in `corrections.json` and are owned by
`corrections.py` (loaded at import, reloaded after each admin write).

**Catalog grouping is per *appearance*, not per name.** `_group_members()` buckets every
`GameAppearance` by `_group_key` — its own resolved `igdb_slug`, falling back to its game's
`name_slug` while unresolved — and returns the cache snapshot the keys came from (rank within
a group against *that* snapshot, or a concurrent resolution can move an entry between reads).
`_build_catalog`, `_match_appearances` and `_load_game` all work on those groups, so one
podcast name whose episodes resolve to different IGDB games splits into separate catalog
entries (Fin du Game on *Silent Hill 2* 2001 vs Silence on Joue on the 2024 remake) instead of
one silently absorbing the other's episodes. Conversely, name variants converging on one
`igdb_slug` still merge. `_best_member` picks a group's representative (non-child first, then
newest `cached_at`). A name_slug that is *also* a real igdb_slug serves the resolved group;
the all-appearances fallback exists only so a stale `/game/<name_slug>` link still renders.

`_igdb_cache` is written whenever `_resolve_one()` completes (background thread or explicit refresh), and pruned to current appearances on each successful feed re-parse so it stays bounded. All other structures are read-only from the perspective of HTTP handlers.

**Derived response caches.** A monotonic `_data_version` (int) is bumped under `_state_lock` on every feed re-parse, IGDB resolution, and `igdb-refresh` delete. `_catalog_cache`/`_feed_cache` hold the *serialised* JSON body + ETag keyed by it (catalog also keys on `pending`), so repeat reads and 304 revalidations skip re-serialising/re-hashing; `_pending_cache` memoises the pending count per `(version, minute)`.

**IGDB resolution.** `_resolve_one()` resolves one appearance, then enriches it with external sources (real Metacritic score via `metacritic.fetch_metascore`, durée de vie via `hltb.fetch_time_to_beat` → IGDB fallback) before caching, and broadcasts an SSE `resolved` event; `_resolve_pending()` sweeps all pending appearances then broadcasts `done`. Resolution order is **`corrections.json` → name search**; a pinned `igdb_id` is fetched with `canonical=False` so a curator's choice is never redirected to a parent game. The date passed to `fetch_by_name` is: a correction's explicit `hint_date` if set, else `None` when the appearance's podcast has `use_date_hint=False`, else the episode's `pub_ts`. The catalog `pending` count, the SSE endpoint, and the periodic retry (`_periodic_resolve`, every `RESOLVE_RETRY_MINUTES`) all share one **`_appearance_pending()`** notion; the SSE endpoint starts a resolver when work is pending instead of emitting an instant `done` (otherwise the client would reload-loop).

**Applying a shipped correction to a running instance.** An appearance is pending when it is never-cached, older than `IGDB_TTL_HOURS`, **or** the correction now in force fingerprints differently than when it was last resolved. Each `igdb_cache` row stores `correction_sig` — `corrections.fingerprint()` of the entry used to resolve it (`igdb_id` + `search_name` + `hint_date`; **`display_name` excluded**, since a rename is applied at response time and must not re-resolve). Because `corrections.json` is baked into the image but `igdb_cache` lives in a volume that survives deploys, this is how a curated fix reaches an already-deployed instance: at startup the fingerprints mismatch and the existing sweep re-resolves *exactly* the affected appearances — an added, changed, or removed correction all surface the same way. A legacy row (`correction_sig` NULL) reads as `''` = "resolved with no correction", so the first deploy re-resolves once every entry a live correction applies to, and nothing else.

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
