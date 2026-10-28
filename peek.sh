#!/bin/sh
# Read-only answers about the dev data (tools/peek.py), run in the dev backend.
# The script goes in on stdin: nothing to mount, no container to recreate.
exec docker compose -f docker-compose.dev.yml exec -T backend python - "$@" < "$(dirname "$0")/tools/peek.py"
