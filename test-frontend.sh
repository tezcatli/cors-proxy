#!/bin/sh
set -e
docker compose -f docker-compose.test.yml run --no-deps --rm frontend-test
