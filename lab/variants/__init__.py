"""The chains the lab compares — hypotheses, free in how they work. Each module
has NAME and run(episode) -> {chapters, tests}."""
from variants import cinq_minutes, current, fiches_v2, formats, lecture_v2, sans_bande_annonce, sans_palmares, un_jeu

VARIANTS = {v.NAME: v for v in (current, un_jeu, sans_palmares, sans_bande_annonce, cinq_minutes, fiches_v2,
                                 lecture_v2, formats)}
