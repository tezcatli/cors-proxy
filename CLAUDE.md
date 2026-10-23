# CLAUDE.md

**Silence on Joue** companion app — a PWA that reads podcast feeds (Silence on Joue, Fin du Game, Triple Click, The Besties), finds the **video-game tests** each episode holds, groups them by game, and plays them. Invite-only (JWT).

@DECISIONS.md
@STATUS.md

## How to work here

- **Step back before proposing.** Name the goal and the principle at stake, re-read `DECISIONS.md`, look for the general rule rather than the next special case, size the fix to the real stakes, and measure before building. A proposal that adds a special case says why the general rule isn't enough.
- **When the user decides something, add the line to `DECISIONS.md` in the same turn.** Conversations are compacted and decisions in them get lost; the file isn't.
- **When the state changes** (a deploy, a job started or finished, a next step agreed), rewrite `STATUS.md`.
- **One fact, one place.** The detail of a module lives in its docstring and comments, next to the code; this file only maps and holds what crosses modules. Change the docstring, not a copy here.
- The user writes in French; code, comments and commits are in English, `DECISIONS.md` / `STATUS.md` / `lab/` in French.

## Stack

Flask (Python) + SQLite, Gunicorn in prod · Vue 3 + Pinia + Vue Router, Vite, Tailwind + DaisyUI · Docker Compose everywhere · Nginx: a shared edge in prod, owned by the separate `tezcat-edge` repo · GitHub Actions → images on GHCR → the host pulls (nothing built in prod).

## Commands

```bash
docker compose -f docker-compose.dev.yml up --build   # dev: http://localhost:5173 (Vite), API :5000
./test-backend.sh  ./test-frontend.sh  ./test-integration.sh
docker compose -f docker-compose.test.yml run --rm backend-test pytest tests/test_auth.py::test_login_success
cd frontend && npx vitest run tests/auth.test.js
./pull-prod-data.sh                                   # prod's produced tables → dev DB (allowlist, no users)
docker compose -f docker-compose.dev.yml up lab       # the lab, http://localhost:5050 — see lab/README.md
python invite.py [--admin] alice@example.com          # $ADMIN_KEY, $RESET_BASE_URL
```

Dev runs the real auth (no bypass); Vite proxies `/auth` and `/games` to Flask. **Deploy is CI-only**: push to `main` → `.github/workflows/ci.yml` tests, pushes images, calls `tezcat-edge`'s deploy workflow (`SETUP.md`). Rollback:

```bash
ssh user@tezcat.fr "cd ~/opt/silence && sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=<old-sha>/' .env && docker compose -f compose.yml up -d"
```

`INGEST` lives in the server's `backend_secrets.env` (the file deploys don't rewrite); `false` in dev.

## Invariants (break one and prod breaks)

- **gunicorn `--workers 1`.** Catalog, worker, rate limiter are in process memory.
- **`worker.py` is the only writer of the catalog.** Requests read under `catalog_state.lock` or `worker.call()` a job. The ingestion thread only fills memo tables (`transcripts`, `llm_cache`) and hands the rebuild to the worker.
- **Read `catalog_state` through the module** (`state.game_index`), never `from catalog_state import …`: `feeds.refresh_feed` replaces those objects. Tests patch the module that owns a function.
- **`corrections.json` is the only store of curated corrections** — git-tracked, written in dev only (`corrections.is_writable()`; the admin endpoints 409 in prod). A shipped correction changes a question's key; the sweep answers the new one and prunes the old, nothing else to do.
- **An answered IGDB question is never re-asked** (not by age, prompt or model); the TTL expires the game's data, re-fetched by id. Re-asking takes a purge.
- **LLM answers are cached forever by (task, prompt version, input)**: bump a task's version when its prompt changes; `any_version` keeps the catalog whole meanwhile.
- **Nginx fragment `deploy/silence.conf`**: upstreams through a variable (`set $up …; proxy_pass http://$up;`) so the shared edge starts when this app is down; aliases app-prefixed (`silence-backend`, `silence-web`).
- **`contracts/api.json`** declares every endpoint's statuses and fields; Python and JS contract tests read it. Change it with the endpoint.
- **`tests/test_reference.py`** replays the curator's judged episodes (`tests/fixtures/reference.json`, exported by the lab). A rule about which tests an episode holds changes in the lab first.
- Flask never serves pages. `GET /games` never fetches (except a cold start); the background tick keeps the catalog fresh.

## Where to look

Request flow: `edge-nginx (ludo.tezcat.fr) → / silence-web (static SPA) · /auth/*, /games/* silence-backend:8000`.

**Backend (`backend/`)** — each module's docstring is its documentation.

| Module | Owns |
|---|---|
| `app` · `config` · `db` · `models` | factory + `/healthz` · env config · SQLite schema & migrations · dataclasses |
| `auth` | `/auth`: invites, login, resets, account admin, `require_admin` |
| `games` | `/games` routes only, memoised catalog/feed payloads + ETags |
| `catalog_state` | the in-memory catalog and the IGDB cache's write side |
| `feeds` · `rss` · `podcasts` | RSS → catalog · pure parsing · the show registry and per-show rules |
| `critiques` | **which tests an episode holds** (ported from the lab) |
| `questions` · `resolver` | what resolving a name asks · answering it, the sweep, the tick |
| `llm` · `igdb` · `metacritic` · `hltb` | OpenRouter tasks · IGDB client · scraped scores · time to beat |
| `transcribe` · `ingest` | Whisper on DeepInfra · the background ingestion thread |
| `corrections` | loads/validates/writes `corrections.json` |
| `worker` · `serializers` · `review` | the one writer thread · payloads & grouping · admin quality view |

**Frontend (`frontend/src/`)** — `lib/` API clients and the audio state machine (`audioEngine.js`, the only owner of `<audio>`), `stores/` (`games.js` catalog, `player.js` the only driver of the engine + listening progress), `composables/`, `pages/` (admin consoles, lazy-loaded, scoped styles), `components/`. `frontend/sw.js`: service worker, cache keyed by build hash.

**Lab (`lab/`)** — not part of the app (never imported, not in the image): where the reading chain is defined against the curator's judgments, measured, then ported and delivered. `lab/README.md`.

**Tools** — `tools/prod_data.py` (allowlisted export for `pull-prod-data.sh`), `tools/push_lab_data.py` (`push-lab-data.sh`).

## Slugs

`episode.slug` = RSS guid (internal identity, progress key, never in URLs) · `url_slug` = slugified title, the only episode route · `name_slug` = slugified game name (`game_index` key) · `podcast_slug` = name_slug + guid (an appearance) · question key `name|…`, `search|…`, `pin|<id>` (`resolutions` PK) · `igdb_slug` = IGDB's own, for game routes — never re-slugify it (`resident-evil-2--1`).

## Secrets

`backend_secrets.env` (git-ignored): `JWT_SECRET`, `ADMIN_KEY`, `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET`, `RESET_BASE_URL`; optional SMTP, `OPENROUTER_API_KEY`, `DEEPINFRA_API_KEY`. See `SETUP.md`.
