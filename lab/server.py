"""The lab's pages (dev only).

    docker compose -f docker-compose.dev.yml up lab      → http://localhost:5050

« Juger » writes the specification: for each game of a reference episode, the
level it should have and the IGDB entry it is — on the episode's structure and
every game any source proposes, independent of any variant.
"""
import datetime
import json
import logging
import pathlib

from flask import Flask, abort, jsonify, render_template, request

import snapshot
import spec

HERE = pathlib.Path(__file__).parent
app = Flask(__name__, template_folder=str(HERE / 'templates'))
app.jinja_env.filters['hms'] = lambda t: (f'{int(t) // 3600}:{int(t) % 3600 // 60:02d}:{int(t) % 60:02d}'
                                         if t is not None else '?')
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
snapshot.load()

import catalog_state as state                       # noqa: E402  (after the snapshot)
import feeds                                        # noqa: E402
from candidates import candidates                   # noqa: E402
from igdb import search_games                       # noqa: E402
from podcasts import PODCAST_BY_ID                  # noqa: E402


def reference() -> list[dict]:
    with (HERE / 'reference.json').open(encoding='utf-8') as f:
        return json.load(f)['episodes']


def _find(guid: str):
    """Any episode of the feeds — the catalog leaves out the LLM-read shows'
    episodes not read yet, and those are to be judged too."""
    with state.lock:
        ep = state.episode_index.get(guid)
    return ep or next((e for e in feeds.all_episodes() if e.slug == guid), None)


def _episode(guid: str):
    ep = _find(guid)
    if ep is None:
        abort(404, f'No episode {guid} in the feeds')
    return ep


def _date(ts) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).date().isoformat() if ts else '?'


@app.route('/')
def index():
    rows = []
    for ref in reference():
        ep = _find(ref['guid'])
        judged = [g for g in spec.for_episode(ref['guid']).values() if g['level']]
        rows.append({**ref, 'found': ep is not None, 'date': _date(ep.pub_ts) if ep else '?',
                     'show': PODCAST_BY_ID[ep.podcast_id].label if ep else '?',
                     'judged': len(judged)})
    return render_template('index.html', rows=rows)


@app.route('/episode')
def episode():
    # The guid as a query parameter: some are URLs with their own query string.
    ep = _episode(request.args.get('guid', ''))
    written = spec.for_episode(ep.slug)
    timeline, games, read = candidates(ep, [g for g, s in written.items() if s.get('added')])
    for g in games:
        g['spec'] = written.get(g['game'])
    total = max((s['end'] or s['start'] for s in timeline), default=0) or 1
    return render_template('episode.html', ep=ep, show=PODCAST_BY_ID[ep.podcast_id].name,
                           date=_date(ep.pub_ts), timeline=timeline, total=total, games=games,
                           read=read, levels=spec.LEVELS)


@app.route('/spec', methods=['POST'])
def write_spec():
    body = request.get_json(silent=True) or {}
    ep = _episode(body.get('episode', ''))
    game = (body.get('game') or '').strip()
    if not game:
        abort(400, 'game is required')
    if body.get('remove'):
        spec.remove(ep, game)
        return jsonify({'ok': True})
    fields = {k: body[k] for k in ('level', 'igdb', 'added') if k in body}
    try:
        return jsonify(spec.update(ep, game, **fields))
    except ValueError as exc:
        abort(400, str(exc))


@app.route('/igdb')
def igdb_search():
    q = (request.args.get('q') or '').strip()
    return jsonify(search_games(q) if q else [])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)
