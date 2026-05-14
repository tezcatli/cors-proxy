#!/bin/sh
set -e
docker compose -f docker-compose.test.yml run --rm backend-test
