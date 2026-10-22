"""The lab's page (dev only): judge what a variant makes of the reference episodes.

    docker compose -f docker-compose.dev.yml up lab      → http://localhost:5050
"""
import datetime
import json
import logging
import pathlib

from flask import Flask, abort, jsonify, render_template, request

import snapshot
import judgments
from variants import VARIANTS

HERE = pathlib.Path(__file__).parent
app = Flask(__name__, template_folder=str(HERE / 'templates'))
app.jinja_env.filters['hms'] = lambda t: (f'{int(t) // 3600}:{int(t) % 3600 // 60:02d}:{int(t) % 60:02d}'
                                         if t is not None else '')
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
snapshot.load()

import catalog_state as state                       # noqa: E402  (after the snapshot)
import feeds                                        # noqa: E402
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
        judged = judgments.for_episode(ref['guid'])
        rows.append({**ref, 'found': ep is not None, 'date': _date(ep.pub_ts) if ep else '?',
                     'show': PODCAST_BY_ID[ep.podcast_id].label if ep else '?',
                     'judged': len(judged)})
    return render_template('index.html', rows=rows)


@app.route('/episode')
def episode():
    # The guid as a query parameter: some are URLs with their own query string.
    ep = _episode(request.args.get('guid', ''))
    variant = request.args.get('variant', 'current')
    if variant not in VARIANTS:
        abort(404, f'No variant {variant}')
    out = VARIANTS[variant].run(ep)
    judged = judgments.for_episode(ep.slug)
    for row in out['games']:
        row['judgment'] = judged.get(row['game'], {}).get('verdict')
    # Judgments on games this variant doesn't see stay visible: they are cases too.
    seen = {r['game'] for r in out['games']}
    missed = [j for g, j in judged.items() if g not in seen]
    return render_template('episode.html', ep=ep, show=PODCAST_BY_ID[ep.podcast_id].name,
                           date=_date(ep.pub_ts), out=out, missed=missed, variant=variant,
                           variants=list(VARIANTS), verdicts=judgments.VERDICTS)


@app.route('/judge', methods=['POST'])
def judge():
    body = request.get_json(silent=True) or {}
    ep = _episode(body.get('episode', ''))
    try:
        judgments.judge(ep, (body.get('game') or '').strip(), body.get('verdict'), body.get('igdbSlug'))
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)
