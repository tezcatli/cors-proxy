#!/bin/sh
# Quiet by default (dot reporter). Arguments go to vitest
# (./test-frontend.sh tests/auth.test.js); --reporter=default brings the names back.
set -e
docker compose -f docker-compose.test.yml run --no-deps --rm frontend-test \
  node /node_modules/.bin/vitest run --reporter=dot "$@"
