"""Two names are one game when they are one page of the catalog — the identity
the measure and the catalog use — not when they share half their words: the
app's chain (`app`) matches a section of the reading to a game the title names
like a chapter title to a game (`rss.find_chapter_for_game`), and so gives
Broken Sword 5's critique to Broken Age, The Wreck's to The Invincible, Assassin's
Creed II's to Assassin's Creed, while « Lego City 3DS » never meets the
reading's « LEGO City Undercover: The Chase Begins ».

Here a name is one game with another when they are spelled the same
(`critiques.same`) or, both having an entry (`fiches.lookup`, v1), when the
entries are one page (`groups.page`); only when one has none — « Pokémon X et
Pokémon Y » is two games — do the names' words decide, as in the app, numbers
apart (a sequel is another game); a news mention, never resolved, is its
spelling alone. Each game — the names the title proposes and the
reading's names on it — is then judged once, by `critiques`' rules, under the
title's name, else a name that has an entry (words can't tell « Assassin's
Creed » from « Assassin's Creed: Brotherhood »: an entry they chose would be a
wrong one). Only the names whose identity can
matter are resolved: the title's, and the reading's that critique or rank a
game.
`missing` collects the names not resolved yet (`python -m variants.identite_fiche`
resolves them)."""
import catalog_state as state
import critiques
import fiches
import groups
from models import Chapter
from podcasts import PODCAST_BY_ID
from rss import find_chapter_for_game, is_game_catalog_excluded
from variants import app, current

NAME = 'identite_fiche'
missing: set[tuple[str, str]] = set()   # (name, episode guid) not resolved yet


def _page(name: str, episode) -> int | None:
    decided, fiche = fiches.lookup(name, episode)
    if not decided:
        missing.add((name, episode.slug))
        return None
    return fiche and groups.page(fiche['id'])


def games(episode, sections: list[dict]) -> list[dict]:
    """The episode's games: [{names, proposed (the title's or the description's
    name, or None), name (the test's), sections}], one per game."""
    proposed = [m.name for m in episode.proposed or [] if not m.read]
    names = list(dict.fromkeys([*proposed, *(s['game'] for s in sections)]))
    judged = {s['game'] for s in sections if s['kind'] in critiques._JUDGED}
    pages = {n: _page(n, episode) for n in names if n in proposed or n in judged}

    def one(a, b):
        if critiques.same(a, b):
            return True
        if pages.get(a) and pages.get(b):
            return pages[a] == pages[b]
        if a not in pages or b not in pages:   # a name only in the news: its spelling
            return False
        # A sequel is another game, as `critiques.same` has it.
        return critiques._numbers(a) == critiques._numbers(b) and \
            find_chapter_for_game(a, [Chapter('', 0, b, b)]) is not None
    parent = {n: n for n in names}

    def root(n):
        while parent[n] != n:
            n = parent[n]
        return n

    # A game is one page: names joined through one without an entry (« La saga
    # Assassin's Creed ») stay apart when their pages differ.
    held = {n: {pages[n]} if pages.get(n) else set() for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ra, rb = root(a), root(b)
            if ra != rb and len(held[ra] | held[rb]) <= 1 and one(a, b):
                parent[rb] = ra
                held[ra] |= held[rb]
    out: dict[str, dict] = {}
    for n in names:
        g = out.setdefault(root(n), {'names': [], 'proposed': None, 'sections': [], 'name': None})
        g['names'].append(n)
        if n in proposed and g['proposed'] is None:
            g['proposed'] = n
    for g in out.values():
        g['name'] = g['proposed'] or next((n for n in g['names'] if pages.get(n)), g['names'][0])
    for s in sections:
        out[root(s['game'])]['sections'].append(s)
    return list(out.values())


def _test(g: dict, by_llm: bool) -> bool:
    """`critiques`' rules, on a game's sections: a name the title or description
    proposed needs a section of it; the title's game is vetoed when heard only
    without a critique; any other is a test from five minutes of a critique."""
    kinds = {s['kind'] for s in g['sections']}
    if g['proposed'] and not g['sections']:
        return False
    if kinds == {'ranking'}:
        return False
    if g['proposed'] and not by_llm:
        return bool(kinds & critiques._JUDGED)
    if not g['proposed'] and not kinds & critiques.CRITIQUE_KINDS:
        return False
    return max(s['end'] - s['start'] for s in g['sections']) >= critiques.MIN_SECONDS


def run(episode) -> dict:
    out = app.run(episode)
    out = {**out, 'tests': [{**t, 'igdb': fiches.lookup(t['game'], episode)[1]} for t in out['tests']]}
    reading = current._reading(episode)
    with state.lock:
        shown = state.episode_index.get(episode.slug)
    if not reading or shown is None or is_game_catalog_excluded(shown.title):
        return out
    podcast = PODCAST_BY_ID[shown.podcast_id]
    if podcast.one_game or critiques.palmares(podcast, shown.title):
        return out
    sections = [s for s in reading if s['game'] and not s['ad']]
    tests = []
    for g in games(shown, sections):
        if not _test(g, by_llm=podcast.games_by_llm):
            continue
        name = g['name']
        judged = [s for s in g['sections'] if s['kind'] in critiques._JUDGED]
        main = max(judged, key=lambda s: s['end'] - s['start']) if judged else g['sections'][0]
        decided, fiche = fiches.lookup(name, shown)
        tests.append({'game': name, 'start': main['start'], 'end': None, 'minutes': None,
                      'verdict': (main['opinion'] or {}).get('verdict'), 'igdb': fiche if decided else None})
    return {**out, 'tests': tests}


if __name__ == '__main__':
    import argparse
    import logging
    from concurrent.futures import ThreadPoolExecutor

    import server
    import targets
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--dry', action='store_true', help='count what is to resolve, resolve nothing')
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    eps = [e for e in map(server._find, targets.guids(args.all)) if e is not None]
    for e in eps:
        run(e)
    todo = sorted(missing)
    print(f'{len(todo)} names to resolve over {len(eps)} episodes')
    if not args.dry:
        by_guid = {e.slug: e for e in eps}

        def decide(item):
            try:
                f = fiches.decide(item[0], by_guid[item[1]])
                return f and f['id']
            except Exception as exc:   # noqa: BLE001 — one name failing doesn't stop the rest
                logging.warning('%s: %s', item[0], exc)
        with ThreadPoolExecutor(args.jobs) as pool:
            ids = list(pool.map(decide, todo))
        groups.fill(ids)
