"""A show's formats that hold no test, known by their title: Silence on joue's
« Bande-annonce » episodes — a question, the hosts' anecdotes — are no tests,
however much the reading calls a section a review. On top of `sans_palmares`."""
import re

from utils import norm
from variants import sans_palmares

NAME = 'sans_bande_annonce'

# show → what marks an episode without tests in its title (`utils.norm`ed).
NO_TEST_TITLES = {'silence-on-joue': re.compile(r'\bbande annonce\b')}


def run(episode) -> dict:
    out = sans_palmares.run(episode)
    marker = NO_TEST_TITLES.get(episode.podcast_id)
    return {**out, 'tests': []} if marker and marker.search(norm(episode.title)) else out
