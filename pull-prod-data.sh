#!/bin/sh
# Pull the data prod produces (transcripts, LLM answers, IGDB resolutions) into
# the dev DB — never its users. See tools/prod_data.py.
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
HOST="${PROD_SSH:-user@tezcat.fr}"
DEV="docker compose -f $REPO/docker-compose.dev.yml"

SNAP="$(mktemp)"
trap 'rm -f "$SNAP"' EXIT
ssh "$HOST" "cd ~/opt/silence && docker compose -f compose.yml exec -T backend python - export" \
  < "$REPO/tools/prod_data.py" | gunzip > "$SNAP"

# The backend holds the catalog in memory and writes the DB: swap the tables
# while it is down, and its next start loads (and migrates) them.
RUNNING="$($DEV ps -q --status running backend)"
[ -n "$RUNNING" ] && $DEV stop backend
python3 -I "$REPO/tools/prod_data.py" import "$SNAP" "$REPO/backend/data/users.db"
[ -n "$RUNNING" ] && $DEV start backend
echo "Done."
