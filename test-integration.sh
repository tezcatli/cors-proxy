#!/bin/sh
set -e
docker compose -f docker-compose.test.yml run --rm frontend-test \
  node /node_modules/.bin/vitest run --config vitest.integration.config.js
docker compose -f docker-compose.test.yml down
