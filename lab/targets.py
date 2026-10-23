"""Which episodes the lab's scripts work on: the reference episodes, or — with
`--all` — every transcribed episode of the feeds, newest first (the history
the chain will run on once ported)."""
import json
import pathlib

HERE = pathlib.Path(__file__).parent


def guids(everything: bool = False) -> list[str]:
    if not everything:
        return [e['guid'] for e in json.loads((HERE / 'reference.json').read_text())['episodes']]
    import feeds
    import transcribe
    rows = transcribe.rows()
    eps = sorted((e for e in feeds.all_episodes() if (r := rows.get(e.slug)) and r.model),
                 key=lambda e: e.pub_ts or 0, reverse=True)
    return list(dict.fromkeys(e.slug for e in eps))
