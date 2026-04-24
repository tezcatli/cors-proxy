#!/bin/sh
set -e
docker compose -f docker-compose.test.yml run --rm corsproxy-test
