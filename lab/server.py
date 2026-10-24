"""The lab's pages (dev only).

    docker compose -f docker-compose.dev.yml up lab      → http://localhost:5050

« Juger » writes the specification on what a listener gets: the episode's
chapters as the player shows them, each with the tests the catalog references
from it — each right, not a test, or on the wrong IGDB entry — plus the ones
missing; then « Valider »: the rest is right, on to the next episode.
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
app.jinja_env.filters['dur'] = lambda s: (f'{int(s) // 3600} h {int(s) % 3600 // 60:02d}' if s >= 3600
                                         else f'{int(s) // 60} min {int(s) % 60:02d} s')
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
snapshot.load()

import catalog_state as state                       # noqa: E402  (after the snapshot)
import feeds                                        # noqa: E402
import judge                                        # noqa: E402
import measure                                      # noqa: E402
import transcribe                                   # noqa: E402
from igdb import search_games                       # noqa: E402
from podcasts import PODCAST_BY_ID                  # noqa: E402
from variants import VARIANTS                        # noqa: E402

app.jinja_env.globals['variants'] = list(VARIANTS)
# The proposals « Juger » shows, whatever the URL says: the best variant so far.
# The others are compared in /mesure.
DEFAULT = 'identite_fiche'


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


def _variant() -> str:
    variant = request.args.get('variant') or (request.get_json(silent=True) or {}).get('variant') or DEFAULT
    if variant not in VARIANTS:
        abort(404, f'No variant {variant}')
    return variant


def _judged(ep, variant: str) -> tuple[dict, list[dict], str]:
    """(the variant's output, the rows to judge, the episode's status)."""
    out = VARIANTS[variant].run(ep)
    rows = judge.rows(out['tests'], spec.for_episode(ep.slug))
    return out, rows, judge.status(rows, spec.validated(ep.slug) is not None)


def _statuses(variant: str) -> list[tuple[dict, object, str | None]]:
    out = []
    for ref in reference():
        ep = _find(ref['guid'])
        out.append((ref, ep, _judged(ep, variant)[2] if ep else None))
    return out


def _next(guid: str, variant: str) -> str | None:
    """The next reference episode not validated, after `guid`, wrapping round."""
    todo = [(ref['guid'], st) for ref, ep, st in _statuses(variant)]
    i = next((k for k, (g, _) in enumerate(todo) if g == guid), -1)
    return next((g for g, st in todo[i + 1:] + todo[:i + 1] if st not in (None, 'validé') and g != guid), None)


@app.route('/')
def index():
    variant = DEFAULT   # judging shows the best proposals; variants compare in /mesure
    rows = [{**ref, 'found': ep is not None, 'date': _date(ep.pub_ts) if ep else '?',
             'show': PODCAST_BY_ID[ep.podcast_id].label if ep else '?', 'status': st}
            for ref, ep, st in _statuses(variant)]
    progress = {name: (sum(r['status'] == 'validé' for r in rows if r.get('set', 'référence') == name),
                       sum(r.get('set', 'référence') == name for r in rows)) for name in measure.SETS}
    return render_template('index.html', rows=rows, variant=variant, progress=progress)


@app.route('/episode')
def episode():
    # The guid as a query parameter: some are URLs with their own query string.
    ep = _episode(request.args.get('guid', ''))
    variant = DEFAULT   # judging shows the best proposals; variants compare in /mesure
    out, rows, status = _judged(ep, variant)
    chapters = out['chapters']
    total = max((c['end'] or c['start'] for c in chapters), default=0) or 1
    return render_template('episode.html', ep=ep, show=PODCAST_BY_ID[ep.podcast_id].name,
                           date=_date(ep.pub_ts), total=total, variant=variant, status=status,
                           groups=judge.timeline(chapters, rows),
                           unjudged=sum(1 for r in rows if r['shown'] and (r['spec'] or {}).get('test') is None))


@app.route('/validate', methods=['POST'])
def validate():
    """The rest is right: what the variant proposes — run again here, not taken
    from the page — and wasn't judged becomes a test, on the entry proposed."""
    ep = _episode((request.get_json(silent=True) or {}).get('episode', ''))
    variant = DEFAULT   # judging shows the best proposals; variants compare in /mesure
    _, rows, _ = _judged(ep, variant)
    spec.validate(ep, {r['game']: r['shown']['igdb'] for r in rows if r['shown']}, variant)
    return jsonify({'status': _judged(ep, variant)[2], 'next': _next(ep.slug, variant)})


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
    if body.get('rename'):
        try:
            return jsonify(spec.rename(ep, game, body['rename'].strip()))
        except ValueError as exc:
            abort(400, str(exc))
    fields = {k: body[k] for k in ('test', 'igdb', 'added', 'start') if k in body}
    try:
        return jsonify(spec.update(ep, game, **fields))
    except ValueError as exc:
        abort(400, str(exc))


@app.route('/mesure')
def measure_page():
    variant = _variant()
    episodes = measure.score(VARIANTS[variant].run, _find)
    return render_template('measure.html', variant=variant, episodes=episodes, threshold=measure.THRESHOLD,
                           sets=measure.by_set(episodes))


@app.route('/changements')
def changes():
    """What the delivery changes in the catalog (data/changes.json: the catalog
    prod serves, against the ported chain on prod's data plus the lab's pack),
    each change linked to its episode to listen."""
    path = HERE / 'data' / 'changes.json'
    if not path.exists():
        abort(404, 'No data/changes.json: build the comparison first')
    by_title = {e.title: e for e in feeds.all_episodes()}
    rows = []
    for r in json.loads(path.read_text()):
        ep = by_title.get(r['episode'])
        rows.append({**r, 'guid': ep.slug if ep else None, 'date': _date(ep.pub_ts) if ep else '?',
                     'show': PODCAST_BY_ID[ep.podcast_id].label if ep else '?'})
    rows.sort(key=lambda r: (r['show'], r['date']), reverse=True)
    return render_template('changes.html', rows=rows)


@app.route('/transcript')
def transcript():
    """The episode's transcript, to read under its chapters and tests."""
    t = transcribe.load(request.args.get('guid', ''))
    if t is None:
        abort(404, 'Not transcribed')
    return jsonify({'segments': t.segments})


@app.route('/igdb')
def igdb_search():
    q = (request.args.get('q') or '').strip()
    return jsonify(search_games(q) if q else [])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)
