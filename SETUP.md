# Setup — Silence on Joue

## Prerequisites

- Docker + Docker Compose
- A domain with a valid TLS certificate (prod only — Let's Encrypt recommended)
- An SMTP relay for outgoing e-mail (optional; links are logged to stdout when not configured)

---

## Repository layout

```
cors-proxy/
├── backend/            # Flask backend (CORS proxy + auth API)
├── frontend/           # Frontend PWA (static files)
├── nginx/              # Reverse proxy (prod only)
├── backend_secrets.env     # Backend secrets (git-ignored)
├── frontend_secrets.env    # Frontend build secrets (git-ignored)
├── docker-compose.dev.yml
├── docker-compose.prod.yml
└── invite.py           # CLI tool for sending invitations
```

---

## Secret files

Both env files must be created manually — they are not committed.

### `backend_secrets.env`

```env
# Shared proxy secret (legacy, can be any random string)
PROXY_SECRET=<random string>

# JWT signing key — keep long and secret
JWT_SECRET=<long random string>

# Admin key — used to call POST /auth/invite
ADMIN_KEY=<long random string>

# RAWG API key (https://rawg.io/apidocs) — kept server-side, never exposed to browser
RAWG_KEY=<your rawg api key>

# Base URL used to build invite and password-reset links
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

**1. Create the secret files** (see above). Set `RESET_BASE_URL` to your public domain,
e.g. `https://tezcat.fr`.

**2. Obtain a TLS certificate** with Certbot:
```bash
certbot certonly --standalone -d your-domain.com
```
The nginx config expects certificates at `/etc/letsencrypt/live/<domain>/`.

**3. Build and start the stack:**
```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Services:
| Service     | Role                                      | Port  |
|-------------|-------------------------------------------|-------|
| `backend`   | Flask/Gunicorn — API + proxy              | 8000 (internal) |
| `nginx`     | TLS termination, static files, routing    | 80, 443 |
| `frontend`  | One-shot build container (copies assets)  | — |

SQLite data is stored in the named Docker volume `backend_data` (mounted at
`/backend/data` inside the container). Back it up before destructive operations:
```bash
docker run --rm -v cors-proxy_backend_data:/data -v $(pwd):/out \
  busybox cp /data/users.db /out/users.db.bak
```

**4. Invite the first user:**
```bash
ADMIN_KEY=<your key> RESET_BASE_URL=https://your-domain.com \
  python invite.py alice@example.com
```

---

## Sending invitations

```bash
# Single user
python invite.py alice@example.com

# Multiple users
python invite.py alice@example.com bob@example.com

# Override URL or key inline
python invite.py --url https://tezcat.fr --key MY_KEY alice@example.com
```

The script reads `$ADMIN_KEY` and `$RESET_BASE_URL` from the environment if
`--key` / `--url` are not passed. It prints the invite URL and exits non-zero if
any invitation fails.

### Promoting an admin

Admins get the « Résolution des noms » dashboard (`/silence/admin/resolution`):
per-podcast resolution figures, plus the review queues and the correction picker.
There is no self-service promotion — flip the flag in SQLite:

```bash
# Prod (inside the container)
docker compose -f docker-compose.prod.yml exec backend \
  python -c "import db; conn=db.get_db().__enter__(); conn.execute(\"UPDATE users SET is_admin=1 WHERE email=?\", ('alice@example.com',)); conn.commit()"

# Or directly against the DB file
sqlite3 backend/data/users.db "UPDATE users SET is_admin = 1 WHERE email = 'alice@example.com';"
```

The flag is read from the DB on every admin request, so a promotion (or demotion)
takes effect immediately — no re-login needed. The JWT also carries an `admin`
claim, but only to decide whether to *show* the UI; it is never trusted for access.

`ADMIN_KEY` is unrelated: it guards `POST /auth/invite` only.

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
| `RAWG_KEY`         | *(required)*                   | RAWG.io API key — server-side only, responses cached 30 days in SQLite |
| `DEBUG`            | `false`                        | Set `true` in dev to skip auth checks on proxy |
