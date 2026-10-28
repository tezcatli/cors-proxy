#!/bin/sh
# Quiet by default: one dot per test, short tracebacks. Arguments go to pytest
# (./test-backend.sh tests/test_auth.py -k login); -v brings the names back.
set -e
[ $# -eq 0 ] && set -- tests/
docker compose -f docker-compose.test.yml run --rm backend-test \
  python -m pytest -q --tb=short -p no:cacheprovider "$@"
