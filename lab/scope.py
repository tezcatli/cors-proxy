"""What counts as a test at all — the curator's call, part of the definition,
not of any chain: at least five minutes of the episode on the game, unless the
episode's title names it. Shorter, a test can't be told from a mention with
enough confidence (1–2 min demos were tests in one episode, not in another).

The minutes are the episode's reading's — the longest section on the game.
"""
from judge import same
from podcasts import PODCAST_BY_ID

MIN_MINUTES = 5


def title_games(episode) -> list[str]:
    """The games the episode's title names, for the shows whose titles name them."""
    if PODCAST_BY_ID[episode.podcast_id].games_by_llm:
        return []
    proposed = episode.proposed if getattr(episode, 'proposed', None) is not None else episode.games
    return [m.name for m in proposed if not m.read]


def in_scope(episode, reading: list[dict] | None):
    """name → whether a test of that game is in scope in this episode."""
    named = title_games(episode)

    def check(name: str) -> bool:
        if any(same(name, n) for n in named):
            return True
        longest = max((s['end'] - s['start'] for s in reading or []
                       if s['game'] and not s['ad'] and same(s['game'], name)), default=0)
        return longest >= MIN_MINUTES * 60
    return check
