"""The tests the reading variant (`reader.py`) finds — read with the curator's
definition — under the show's format rules: a Fin du Game episode is the
title's game, a SoJ « Bande-annonce » holds none (`fiches_v2` as before). Each
test on the resolution variant's entry (`fiches.py`), once decided."""
import fiches
import reader
from variants import fiches_v2, sans_bande_annonce, un_jeu

NAME = 'lecture_v2'


def run(episode) -> dict:
    out = fiches_v2.run(episode)
    marker = sans_bande_annonce.NO_TEST_TITLES.get(episode.podcast_id)
    if episode.podcast_id in un_jeu.ONE_GAME or (marker and marker.search(sans_bande_annonce.norm(episode.title))):
        return out
    read = reader.tests(episode)
    if read is None:
        return out
    tests = []
    for t in read:
        decided, fiche = fiches.lookup(t['game'], episode)
        tests.append({'game': t['game'], 'start': t['start'], 'end': t['end'],
                      'minutes': round((t['end'] - t['start']) / 60), 'verdict': t['verdict'],
                      'igdb': fiche if decided else None})
    return {**out, 'tests': tests}
