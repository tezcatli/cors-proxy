"""Read the reference episodes the current prompt hasn't read, into the lab's
cache (`data/lab.db`, see snapshot.py) — the snapshot stays as prod made it.

    docker compose -f docker-compose.dev.yml run --rm lab python read.py [--jobs N]

Needs OPENROUTER_API_KEY. An episode without a transcript is skipped (the lab
doesn't transcribe); a reading that fails is reported and asked again next run.
"""
import argparse
import json
import logging
import pathlib
from concurrent.futures import ThreadPoolExecutor

import snapshot

HERE = pathlib.Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    snapshot.load()
    import feeds
    import llm
    import transcribe
    if not llm.enabled():
        raise SystemExit('OPENROUTER_API_KEY is not set')

    guids = [e['guid'] for e in json.loads((HERE / 'reference.json').read_text())['episodes']]
    episodes = {e.slug: e for e in feeds.all_episodes() if e.slug in guids}
    rows = transcribe.rows()
    todo = []
    for guid in guids:
        ep, row = episodes.get(guid), rows.get(guid)
        if ep is None or not (row and row.model):
            logging.warning('Skipped (%s): %s', 'not in the feeds' if ep is None else 'no transcript', guid)
        elif not llm.has_current_reading(transcribe.reading_input(ep, row.model)):
            todo.append(ep)
    logging.info('%d to read', len(todo))

    def read(ep):
        t = transcribe.load(ep.slug)
        ok = llm.read_transcript(transcribe.reading_input(ep, t.model), t.segments) is not None
        logging.info('%s %s', 'Read' if ok else 'FAILED', ep.title)
        return ok

    with ThreadPoolExecutor(args.jobs) as pool:
        done = list(pool.map(read, todo))
    logging.info('%d read, %d failed', sum(done), len(done) - sum(done))


if __name__ == '__main__':
    main()
