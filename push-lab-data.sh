#!/bin/sh
# Once, at the delivery of the lab's chain: hand prod what the lab produced —
# the history's transcripts, readings and resolutions — then restart its
# backend, which loads them at start. See tools/push_lab_data.py.
#   docker compose -f docker-compose.dev.yml run --rm lab python pack_for_prod.py
#   ./push-lab-data.sh
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
HOST="${PROD_SSH:-user@tezcat.fr}"
PACK="$REPO/lab/data/prod-pack.json.gz"
[ -f "$PACK" ] || { echo "no $PACK: run lab/pack_for_prod.py first" >&2; exit 1; }

scp -q "$PACK" "$HOST:/tmp/lab-pack.json.gz"
ssh "$HOST" "chmod 644 /tmp/lab-pack.json.gz && cd ~/opt/silence \
  && docker compose -f compose.yml cp /tmp/lab-pack.json.gz backend:/tmp/lab-pack.json.gz \
  && rm /tmp/lab-pack.json.gz \
  && docker compose -f compose.yml exec -T backend python - load /tmp/lab-pack.json.gz; \
  docker compose -f compose.yml exec -T -u root backend rm -f /tmp/lab-pack.json.gz; \
  docker compose -f compose.yml restart backend" \
  < "$REPO/tools/push_lab_data.py"
