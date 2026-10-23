"""What the curator judges on an episode: the tests a variant references, beside
the ones already judged — so a new variant only asks about what it changes —
laid on the episode's chapters, where they are listened to.

The judgment is on what a listener gets, never on the chain's intermediate
steps: a game the variant doesn't reference isn't asked about, unless it was
judged before (it should be there, or it shouldn't) or the curator adds it as
missing. Validating an episode says the rest is right.
"""
import difflib
import functools

from utils import norm, norm_key

_ROMAN = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7',
          'viii': '8', 'ix': '9', 'x': '10'}


def _numbers(name: str) -> list[str]:
    """A name's numbers, roman numerals read as digits: a sequel is another game."""
    return [_ROMAN.get(w, w) for w in norm(name).split() if w.isdigit() or w in _ROMAN]


@functools.lru_cache(maxsize=None)   # 30 000 calls a measure, on a few thousand names
def same(a: str, b: str) -> bool:
    """One game under two spellings: the same letters but for spaces and
    punctuation (« Astro Bot »), or close (« Tinikin ») with the same numbers —
    « Gears of War 2 » and « Gears of War » are two games."""
    ka, kb = norm_key(a), norm_key(b)
    if ka == kb:
        return True
    return _numbers(a) == _numbers(b) and difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.85


def rows(tests: list[dict], judged: dict[str, dict]) -> list[dict]:
    """One row per game: {game, shown (the variant's test, or None), spec (the
    judgment, or None)} — a test and a judgment are one game when their names
    are (`same`) or their IGDB entries. A judged game keeps its judged name, whatever the
    variant calls it, so the judgment is found again."""
    out = [{'game': t['game'], 'shown': t, 'spec': None} for t in tests]

    def one_game(r, name, entry) -> bool:
        """The same name however spelled, or the same IGDB entry: « Sonic the
        Hedgehog 4: Episode I » is the « Sonic 4 » judged."""
        if same(r['game'], name):
            return True
        a, b = (r['shown'] or {}).get('igdb'), entry.get('igdb')
        return isinstance(a, dict) and isinstance(b, dict) and a['id'] == b['id']

    for name, entry in judged.items():
        row = next((r for r in out if r['spec'] is None and one_game(r, name, entry)), None)
        if row is None:
            out.append({'game': name, 'shown': None, 'spec': entry})
        else:
            row.update(game=name, spec=entry)
    return out


def start(row: dict) -> float | None:
    """Where a row is listened to: the variant's test, else where the curator
    added it."""
    return row['shown']['start'] if row['shown'] else (row['spec'] or {}).get('start')


def _overlap(a0, a1, b0, b1) -> float:
    return max(0, min(a1, b1) - max(a0, b0)) if a1 is not None and b1 is not None else 0


def timeline(chapters: list[dict], rows: list[dict]) -> list[dict]:
    """The chapters, each with the rows that lie in it: [{start, end, title,
    rows, within}]. A test lies in the chapter it starts in — unless it covers
    less than half of it: a chain's clock and the chapters' are seconds apart,
    so a test may start at the very end of the chapter before; then the next
    one — and is `within` every later chapter it covers at least half of. Rows
    with no start, or before the first chapter, come first in a group with no
    title."""
    lead = {'start': None, 'end': None, 'title': None, 'rows': [], 'within': []}
    groups = [{**c, 'rows': [], 'within': []} for c in chapters]

    def half(g, t, end) -> bool:
        return g['end'] is None or end is None or _overlap(t, end, g['start'], g['end']) >= (g['end'] - g['start']) / 2

    for row in rows:
        t, end = start(row), row['shown'] and row['shown'].get('end')
        i = None if t is None else next((k for k in range(len(groups) - 1, -1, -1) if groups[k]['start'] <= t), None)
        if i is None:
            lead['rows'].append(row)
            continue
        if not half(groups[i], t, end) and i + 1 < len(groups) and end is not None and end > groups[i + 1]['start']:
            i += 1
        groups[i]['rows'].append(row)
        for g in groups[i + 1:]:
            if end is not None and g['start'] < end and half(g, t, end):
                g['within'].append(row['game'])
    return ([lead] if lead['rows'] else []) + groups


def status(rows: list[dict], validated: bool) -> str:
    """à juger (never validated), validé, or à revoir: validated, but a variant
    references a test nobody judged."""
    if not validated:
        return 'à juger'
    return 'à revoir' if any(r['shown'] and (r['spec'] or {}).get('test') is None for r in rows) else 'validé'
