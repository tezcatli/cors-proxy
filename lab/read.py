"""Read the reference episodes the current prompt hasn't read, into the lab's
cache (`data/lab.db`, see snapshot.py) — the snapshot stays as prod made it.
`--tests` reads them with the reading variant instead (`reader.py`).

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
    parser.add_argument('--tests', action='store_true', help='the reading variant (reader.py)')
    parser.add_argument('--all', action='store_true', help='every transcribed episode, newest first')
    parser.add_argument('--limit', type=int, help='at most N episodes to read')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    snapshot.load()
    import feeds
    import llm
    import transcribe
    if not llm.enabled():
        raise SystemExit('OPENROUTER_API_KEY is not set')

    import targets
    guids = targets.guids(args.all)
    episodes = {e.slug: e for e in feeds.all_episodes() if e.slug in guids}
    rows = transcribe.rows()
    todo = []
    for guid in guids:
        ep, row = episodes.get(guid), rows.get(guid)
        if ep is None or not (row and row.model):
            logging.warning('Skipped (%s): %s', 'not in the feeds' if ep is None else 'no transcript', guid)
        elif args.tests:
            import reader
            if reader.tests(ep) is None:
                todo.append(ep)
        elif not llm.has_current_reading(transcribe.reading_input(ep, row.model)):
            todo.append(ep)
    todo = todo[:args.limit] if args.limit else todo
    logging.info('%d to read', len(todo))

    def read(ep):
        if args.tests:
            import reader
            ok = reader.tests(ep, read=True) is not None
        else:
            t = transcribe.load(ep.slug)
            ok = llm.read_transcript(transcribe.reading_input(ep, t.model), t.segments) is not None
        logging.info('%s %s', 'Read' if ok else 'FAILED', ep.title)
        return ok

    with ThreadPoolExecutor(args.jobs) as pool:
        done = list(pool.map(read, todo))
    logging.info('%d read, %d failed', sum(done), len(done) - sum(done))


if __name__ == '__main__':
    main()
