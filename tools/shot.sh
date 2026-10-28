#!/bin/sh
# A screenshot (or with --text, the accessibility tree) of the dev app — tools/shot.py.
# Needs the dev stack up; writes shots/<route>-<device>.jpg (git-ignored).
set -e
cd "$(dirname "$0")/.."
mkdir -p shots
TOKEN=$(./peek.sh token)
exec docker compose -f docker-compose.dev.yml run --rm --no-deps -T -e TOKEN="$TOKEN" shot \
  python /tools/shot.py "$@" 2>&1 | grep -v '^ *Container '
