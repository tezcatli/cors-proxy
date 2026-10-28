#!/usr/bin/env python3
"""
Read-only, compact answers about the dev data — the questions otherwise asked
with a throwaway script each session. Runs in the dev backend container (`./peek.sh`):
the catalog lives in the running backend's memory, so games and episodes are
read through its API (GET only, with an admin token minted here); the memo
tables through SQLite opened `mode=ro`. Nothing here can write.

    ./peek.sh game <slug>                 a game's page: its tests, one line each
    ./peek.sh episode <url_slug|guid>     an episode's chapters and tests
    ./peek.sh search <text>               games and episodes whose name matches
    ./peek.sh question <key prefix>       `resolutions` rows, with the game's name
    ./peek.sh llm <task> [text]           `llm_cache` rows of a task whose input matches
    ./peek.sh transcript <guid> [from] [to]   the transcript between two times (m:ss)
    ./peek.sh ref <guid|text>             the curator's judgment (tests/fixtures/reference.json)
    ./peek.sh catalog [--save N] [--diff N]   catalog size; save it as N, or what changed since N

    ./peek.sh token                       an admin JWT, for tools/shot.sh (not for reading)

Every listing stops at --limit lines (default 40); --full keeps long fields whole.
"""
import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, '/backend')

DB = '/backend/data/users.db'
API = 'http://localhost:5000'
REFERENCE = '/backend/tests/fixtures/reference.json'
SAVES = '/backend/data/peek-{}.json'   # git-ignored, seen from the host too

args = argparse.Namespace(full=False, limit=40, save=None, diff=None)


def cut(text, n=100):
    text = ' '.join(str(text or '').split())
    return text if args.full or len(text) <= n else text[:n - 1] + '…'


def clock(seconds):
    if seconds is None:
        return '—'
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def seconds(text):
    parts = [int(p) for p in text.split(':')]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def show(lines):
    lines = list(lines)
    for line in lines[:args.limit]:
        print(line)
    if len(lines) > args.limit:
        print(f'… {len(lines) - args.limit} more (--limit)')


def db():
    return sqlite3.connect(f'file:{DB}?mode=ro', uri=True)


_token = None


def token():
    global _token
    if _token is None:
        import auth
        with db() as conn:
            row = conn.execute('SELECT id, email FROM users WHERE is_admin = 1 LIMIT 1').fetchone()
        if not row:
            sys.exit('no admin user in the dev DB')
        _token = auth._make_jwt(*row)
    return _token


def get(path):
    req = urllib.request.Request(API + path, headers={'Authorization': f'Bearer {token()}'})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        sys.exit(f'{e.code} on GET {path}')


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_game(slug):
    g = get('/games/' + urllib.parse.quote(slug))
    igdb = g.get('igdb') or {}
    print(f"{g['name']}  [{g['slug']}]  igdb: {g.get('igdbName') or '(none)'} {igdb.get('released') or ''}"
          f"  names={','.join(g.get('nameSlugs') or [])}{'  corrected' if g.get('corrected') else ''}")
    rows = []
    for e in g['episodes']:
        c = e.get('critique') or {}
        rows.append(f"{e.get('podcast', {}).get('id', '?'):<18} {e['urlSlug']:<50} "
                    f"start={clock(e.get('timestampSeconds'))} dur={clock(e.get('durationSeconds'))} "
                    f"{c.get('verdict') or '-'}  +{len(c.get('pros') or [])}/-{len(c.get('cons') or [])}")
    show(rows)


def cmd_episode(slug):
    e = get('/games/episode?slug=' + urllib.parse.quote(slug))
    print(f"{e['title']}  [{e['urlSlug']} · {e['slug']}]  {(e.get('podcast') or {}).get('id', '')}")
    show(f"{c['timestamp']:>8}  {cut(c['title'], 70):<70} {('→ ' + c['slug']) if c.get('slug') else ''}"
         for c in e.get('chapters') or [])
    for game in e.get('games') or []:
        c = game.get('critique') or {}
        print(f"  test {game.get('slug')}  {cut(game.get('name'), 40)}  at={clock(c.get('at'))}  {c.get('verdict') or '-'}")


def cmd_search(text):
    q = text.lower()
    games = [g for g in get('/games')['games'] if q in g['name'].lower()]
    episodes = [e for e in get('/games/episodes') if q in e['title'].lower()]
    show([f"game     {g['slug']:<45} {g['name']}  ({g['episodeCount']} ép.)" for g in games]
         + [f"episode  {e['urlSlug']:<45} {cut(e['title'], 60)}" for e in episodes])


def cmd_question(prefix):
    with db() as conn:
        rows = conn.execute(
            'SELECT r.question, r.igdb_id, g.name, r.method, r.attempts, r.last_error '
            'FROM resolutions r LEFT JOIN igdb_games g ON g.igdb_id = r.igdb_id '
            'WHERE r.question LIKE ? ORDER BY r.question', (prefix + '%',)).fetchall()
    show(f'{q:<55} {i or "-":>7} {cut(n, 40) if n else "(no game)"}  {m or ""}'
         f'{f"  err×{a}: {cut(err, 60)}" if err else ""}' for q, i, n, m, a, err in rows)


def cmd_llm(task, text=None):
    with db() as conn:
        rows = conn.execute(
            'SELECT version, input, answer, model FROM llm_cache WHERE task = ? AND input LIKE ? '
            'ORDER BY created_at DESC', (task, f'%{text or ""}%')).fetchall()
    show(f'v{v} {model}\n  in:  {cut(i, 160)}\n  out: {cut(a, 300)}' for v, i, a, model in rows)


def cmd_transcript(guid, start=None, end=None):
    lo, hi = seconds(start) if start else 0, seconds(end) if end else float('inf')
    with db() as conn:
        row = conn.execute('SELECT segments FROM transcripts WHERE guid = ?', (guid,)).fetchone()
    if not row or not row[0]:
        sys.exit('no transcript')
    show(f'{clock(a):>8}  {t.strip()}' for a, b, t in json.loads(row[0]) if lo <= a < hi)


def cmd_ref(key):
    episodes = json.load(open(REFERENCE))['episodes']
    found = [e for e in episodes if e['guid'] == key] or \
            [e for e in episodes if key.lower() in e['title'].lower()]
    for e in found[:args.limit]:
        print(f"{e['title']}  [{e['guid']} · {e['podcast']} · {e['set']}]")
        print(f"  tests:     {', '.join(e['tests']) or '—'}")
        print(f"  not tests: {', '.join(e['not_tests']) or '—'}")
        print('  starts:    ' + ', '.join(f"{c['game']} {clock(c['start'])}" for c in e['chain']))
    if not found:
        sys.exit('no judged episode matches')


def cmd_catalog():
    games = {g['slug']: (g['name'], g['episodeCount'], g.get('verdicts')) for g in get('/games')['games']}
    if args.save:
        json.dump(games, open(SAVES.format(args.save), 'w'))
    if args.diff:
        before = {k: tuple(v) for k, v in json.load(open(SAVES.format(args.diff))).items()}
        now = {k: (v[0], v[1], v[2]) for k, v in games.items()}
        show([f'- {k}  {before[k][0]}' for k in sorted(before.keys() - now.keys())]
             + [f'+ {k}  {now[k][0]}' for k in sorted(now.keys() - before.keys())]
             + [f'~ {k}  {before[k][1:]} → {now[k][1:]}'
                for k in sorted(before.keys() & now.keys()) if list(before[k]) != list(now[k])])
    print(f'{len(games)} games, {sum(v[1] for v in games.values())} appearances')


COMMANDS = {
    'game': cmd_game, 'episode': cmd_episode, 'search': cmd_search, 'question': cmd_question,
    'llm': cmd_llm, 'transcript': cmd_transcript, 'ref': cmd_ref, 'catalog': cmd_catalog,
    'token': lambda: print(token()),
}


def main():
    global args
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=COMMANDS)
    parser.add_argument('params', nargs='*')
    parser.add_argument('--limit', type=int, default=40)
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--save')
    parser.add_argument('--diff')
    args = parser.parse_args()
    import logging
    logging.disable(logging.CRITICAL)
    COMMANDS[args.command](*args.params)


if __name__ == '__main__':
    main()
