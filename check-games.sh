#!/bin/sh
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
docker compose -f "$REPO/docker-compose.dev.yml" run --rm \
  -v "$REPO/tools:/tools" \
  backend python3 /tools/check_games.py "$@"
