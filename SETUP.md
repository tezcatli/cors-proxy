# Setup — Silence on Joue

## Prerequisites

- Docker + Docker Compose
- A domain with a valid TLS certificate (prod only — Let's Encrypt recommended)
- An SMTP relay for outgoing e-mail (optional; links are logged to stdout when not configured)

---

## Repository layout

```
cors-proxy/
├── corsproxy/          # Flask backend (CORS proxy + auth API)
├── silence/            # Frontend PWA (static files)
├── nginx/              # Reverse proxy (prod only)
├── corsproxy_secrets.env   # Backend secrets (git-ignored)
├── silence_secrets.env     # Frontend build secrets (git-ignored)
├── docker-compose.dev.yml
├── docker-compose.prod.yml
└── invite.py           # CLI tool for sending invitations
```

---

## Secret files

Both env files must be created manually — they are not committed.

### `corsproxy_secrets.env`

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
**http://localhost:5000**.

**3. Invite the first user:**
```bash
ADMIN_KEY=<your key> RESET_BASE_URL=http://localhost:5000 \
  python invite.py alice@example.com
```

The invite URL is also printed in the `corsproxy` container logs:
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
| `corsproxy` | Flask/Gunicorn — API + proxy              | 8000 (internal) |
| `nginx`     | TLS termination, static files, routing    | 80, 443 |
| `silence`   | One-shot build container (copies assets)  | — |

SQLite data is stored in the named Docker volume `corsproxy_data` (mounted at
`/corsproxy/data` inside the container). Back it up before destructive operations:
```bash
docker run --rm -v cors-proxy_corsproxy_data:/data -v $(pwd):/out \
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
