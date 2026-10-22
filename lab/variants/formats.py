"""A show's palmarès formats, known by their title like its « Bande-annonce »
episodes: a best-of, an awards show, a reading list hold no test, even when
the reading calls each entry a review (« Triple Click Picks »: 18 « review »
sections). Only explicit formats — « … Is GOTY Quality » is a review. On top of
`fiches_v2`."""
import re

from utils import norm
from variants import fiches_v2

NAME = 'formats'

# show → what marks a palmarès episode in its title (`utils.norm`ed).
PALMARES_TITLES = {
    'triple-click': re.compile(r'^triple click picks\b|^our favou?rite (video )?games of\b'),
    'the-besties': re.compile(r'\bbattle bracket\b|\brequired reading list\b|\bgoty spectacular\b'
                              r'|\bthe besties game of the year is\b'),
    'silence-on-joue': re.compile(r'\bsilences d or\b'),
}


def run(episode) -> dict:
    out = fiches_v2.run(episode)
    marker = PALMARES_TITLES.get(episode.podcast_id)
    return {**out, 'tests': []} if marker and marker.search(norm(episode.title)) else out
