"""The chains the lab compares — hypotheses, free in how they work. Each module
has NAME and run(episode) -> {chapters, tests}."""
from variants import (app, cinq_minutes, current, fiche_versions, fiches_v2, formats, lecture_v2, sans_bande_annonce,
                      sans_palmares, titre_critique, un_jeu)

VARIANTS = {v.NAME: v for v in (current, un_jeu, sans_palmares, sans_bande_annonce, cinq_minutes, fiches_v2,
                                 lecture_v2, formats, *fiche_versions.ALL,
                                 titre_critique, app)}
