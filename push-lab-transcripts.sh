#!/bin/sh
# One-off: hand prod the Silence on Joue transcripts the lab already made, so the
# ingestion doesn't pay to transcribe them again. Run after deploying the
# transcription, before setting DEEPINFRA_API_KEY. See tools/lab_transcripts.py.
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
HOST="${PROD_SSH:-user@tezcat.fr}"
LAB="${LAB_DB:-$HOME/dev/llmplayground/data/soj.db}"

PACK="$(mktemp)"
trap 'rm -f "$PACK"' EXIT
python3 -I "$REPO/tools/lab_transcripts.py" pack "$LAB" > "$PACK"
scp -q "$PACK" "$HOST:/tmp/lab-transcripts.json.gz"
ssh "$HOST" "cd ~/opt/silence \
  && docker compose -f compose.yml cp /tmp/lab-transcripts.json.gz backend:/tmp/lab-transcripts.json.gz \
  && rm /tmp/lab-transcripts.json.gz \
  && docker compose -f compose.yml exec -T backend python - load /tmp/lab-transcripts.json.gz" \
  < "$REPO/tools/lab_transcripts.py"
