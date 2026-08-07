# Setup — Silence on Joue

## Prerequisites

- Docker + Docker Compose
- A domain with a valid TLS certificate (prod only — Let's Encrypt recommended)
- An SMTP relay for outgoing e-mail (optional; links are logged to stdout when not configured)

---

## Repository layout

```
cors-proxy/
├── backend/            # Flask backend (API + auth)
├── frontend/           # Vue 3 PWA sources
├── nginx/              # web.conf + Dockerfile.web — the static-serving image
├── deploy/             # what ships to the host: compose.yml + silence.conf
├── backend_secrets.env # Backend secrets (git-ignored; lives on the host)
├── docker-compose.dev.yml
├── docker-compose.test.yml
└── invite.py           # CLI tool for sending invitations
```

---

## Secret file

`backend_secrets.env` must be created manually — it is not committed, and in production it
is never shipped by the pipeline either: it is created once on the host and left alone.

### `backend_secrets.env`

```env
# JWT signing key — keep long and secret
JWT_SECRET=<long random string>

# Admin key — used to call POST /auth/invite
ADMIN_KEY=<long random string>

# IGDB / Twitch application credentials (https://api-docs.igdb.com)
IGDB_CLIENT_ID=<your igdb client id>
IGDB_CLIENT_SECRET=<your igdb client secret>

# Base URL used to build invite and password-reset links.
# In production this is the app's own subdomain: https://ludo.tezcat.fr
RESET_BASE_URL=https://your-domain.com

# SMTP (optional — omit to log links to stdout instead of sending e-mail)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=user@example.com
SMTP_PASS=<smtp password>
SMTP_FROM=noreply@example.com
```

Generate strong random values with:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(40))"
```

---

## Development

In dev mode the Flask server runs with hot-reload (`DEBUG=true`), authentication is
bypassed for proxy requests, and e-mail links are printed to the container logs instead
of being sent.

**1. Create the secret files** (see above). `RESET_BASE_URL` can stay as
`http://localhost:5000`.

**2. Start the stack:**
```bash
docker compose -f docker-compose.dev.yml up --build
```

The frontend is served at **http://localhost:5000/silence** and the API at
**http://localhost:5000**. In dev, frontend asset requests are proxied to Vite's
hot-reload server on port `5173`.

**3. Invite the first user:**
```bash
ADMIN_KEY=<your key> RESET_BASE_URL=http://localhost:5000 \
  python invite.py alice@example.com
```

The invite URL is also printed in the `backend` container logs:
```
INVITE LINK for alice@example.com → http://localhost:5000/silence/?invite=…&email=…
```

Open the link in a browser to complete registration.

---

## Production

The app is served at **https://ludo.tezcat.fr/silence/**, behind the shared nginx edge
defined in the separate **`tezcat-edge`** repository. Nothing is built on the host:
`.github/workflows/ci.yml` builds images, pushes them to GHCR, and the host pulls them.

```
:443 ──▶ edge-nginx  ──┬─▶ silence-web      static SPA, baked into the image
   ludo.tezcat.fr      └─▶ silence-backend  Flask/Gunicorn on :8000 (internal)
```

| Service | Image | Role |
|---|---|---|
| `backend` | `ghcr.io/tezcatli/silence-backend` | API + auth. Holds all catalog state in memory — **`--workers 1`** |
| `web`     | `ghcr.io/tezcatli/silence-web`     | nginx serving the built SPA. Stateless |

The edge itself (TLS, routing, ACME) is documented in `tezcat-edge/README.md`.

### What deploys, and how

Push to `main` → tests → images tagged with the commit SHA → the reusable
`tezcat-edge/.github/workflows/deploy-app.yml` ships two files and restarts:

| Shipped | To | Owner |
|---|---|---|
| `deploy/compose.yml`  | `~/opt/silence/compose.yml`          | this repo |
| `deploy/silence.conf` | `~/opt/edge/conf.d/10-silence.conf`  | this repo |

`~/opt/silence/.env` holds `IMAGE_TAG=<sha>` and is the record of what is deployed.
`backend_secrets.env` sits beside them and is never touched by the pipeline.

Required repository secrets: `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER`,
`DEPLOY_KNOWN_HOSTS` (the pinned host key — **not** `ssh-keyscan`, which would re-trust
whatever answers DNS on every run and then hand it the deploy key).

The deploy fails if the backend does not report healthy within 150 s, or if the smoke test
against `https://ludo.tezcat.fr/silence/` does not return 2xx.

### Rollback

Seconds, and no rebuild — the images for every past commit are still in GHCR:

```bash
ssh user@tezcat.fr "cd ~/opt/silence && sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=<old-sha>/' .env \
  && docker compose -f compose.yml up -d"
```

### Certificates

Issued and renewed by certbot on the host with the **webroot** authenticator, so renewal
never stops nginx. See `tezcat-edge/README.md`; the app's certificate is
`/etc/letsencrypt/live/ludo.tezcat.fr/`, referenced by `deploy/silence.conf`.

### Backups

SQLite lives in the named volume `silence_backend_data`, mounted at `/backend/data`. Back
it up before anything destructive:

```bash
docker run --rm -v silence_backend_data:/data -v $(pwd):/out \
  busybox cp /data/users.db /out/users.db.bak
```

### First user

```bash
ADMIN_KEY=<your key> RESET_BASE_URL=https://ludo.tezcat.fr \
  python invite.py --admin alice@example.com
```

---

## Managing accounts

Day to day this happens in the app: an administrator opens **« Comptes »** from the
account menu (`/silence/admin/users`) to send invitations, see which ones are still
pending (with their link, and a revoke button), promote or demote accounts, and
delete them. Two things the console will refuse, in the server and not just the UI:
removing or demoting **yourself**, and leaving the instance with **no administrator**.

`invite.py` is the way in before that console exists — an empty database has no
admin to log in as.

```bash
# Single user
python invite.py alice@example.com

# The account this invitation creates is an administrator (bootstrap)
python invite.py --admin alice@example.com

# Multiple users
python invite.py alice@example.com bob@example.com

# Override URL or key inline
python invite.py --url https://tezcat.fr --key MY_KEY alice@example.com
```

The script reads `$ADMIN_KEY` and `$RESET_BASE_URL` from the environment if
`--key` / `--url` are not passed. It prints the invite URL and exits non-zero if
any invitation fails.

### Promoting an admin

Admins get « Comptes » (above) and the « Résolution des noms » dashboard
(`/silence/admin/resolution`): per-podcast resolution figures, plus the review
queues and the correction picker.

Normally you promote from the console. The SQL below stays the escape hatch — a
first admin on an existing database, or an instance whose last admin was lost:

```bash
# Prod (inside the container, from ~/opt/silence on the host)
docker compose -f compose.yml exec backend \
  python -c "import db; conn=db.get_db().__enter__(); conn.execute(\"UPDATE users SET is_admin=1 WHERE email=?\", ('alice@example.com',)); conn.commit()"

# Or directly against the DB file
sqlite3 backend/data/users.db "UPDATE users SET is_admin = 1 WHERE email = 'alice@example.com';"
```

The flag is read from the DB on every admin request, so a promotion (or demotion)
takes effect immediately — no re-login needed. The JWT also carries an `admin`
claim, but only to decide whether to *show* the UI; it is never trusted for access.
(A user promoted while logged in sees the admin UI once their token is refreshed;
doing it to yourself from the console refreshes it for you.)

`ADMIN_KEY` is a second, independent credential for `POST /auth/invite`, so that
`invite.py` and CI can send invitations without a user session.

### Correcting a name→IGDB resolution

`backend/corrections.json` is the **single source of truth** — git-tracked, so a fix
is reviewed, survives a database wipe, and applies to every deployment. Corrections
are therefore curated **in dev**, where the repo is bind-mounted into the container:

```bash
docker compose -f docker-compose.dev.yml up -d
# open http://localhost:5173/silence/admin/resolution, fix what's wrong, then:
git diff backend/corrections.json     # review what the dashboard wrote
git add backend/corrections.json && git commit -m "corrections: ..."
```

Deploy to apply. In prod the dashboard is **read-only** (the file ships inside the
image, owned by root while the app runs as `appuser`), and the write endpoints answer
409 — the stats page shows the read-only notice instead of the Corriger buttons.

The file can equally be hand-edited: `podcast_name` plus either `igdb_id` (pin) or
`search_name`, with optional `display_name`, `hint_date` and `podcast_id` scopes. It
is validated on load, so a malformed entry fails the tests rather than production.

---

## Environment variable reference

| Variable           | Default                        | Description |
|--------------------|--------------------------------|-------------|
| `JWT_SECRET`       | `dev-insecure-change-me`       | JWT signing secret — **must** be changed in prod |
| `JWT_TTL_SECONDS`  | `604800` (7 days)              | Token lifetime |
| `ADMIN_KEY`        | *(empty — endpoint disabled)*  | Secret for `POST /auth/invite` |
| `RESET_BASE_URL`   | `http://localhost:5000`        | Public base URL for e-mail links |
| `SMTP_HOST`        | *(empty)*                      | SMTP server hostname; omit to log links only |
| `SMTP_PORT`        | `587`                          | SMTP port |
| `SMTP_USER`        | *(empty)*                      | SMTP username |
| `SMTP_PASS`        | *(empty)*                      | SMTP password |
| `SMTP_FROM`        | `noreply@example.com`          | Sender address |
| `IGDB_CLIENT_ID`     | *(required)*                 | IGDB/Twitch application id — server-side only |
| `IGDB_CLIENT_SECRET` | *(required)*                 | IGDB/Twitch application secret |
| `METACRITIC_SCRAPE`  | `true`                       | Scrape the real Metascore during resolution; falls back to IGDB's aggregate |
| `IGDB_TTL_HOURS`     | `720` (30 days)              | How long a cached IGDB resolution stays fresh |
| `RESOLVE_RETRY_MINUTES` | `15`                      | Periodic re-sweep of never-resolved appearances |
| `DEBUG`            | `false`                        | Set `true` in dev to skip auth checks on proxy |
