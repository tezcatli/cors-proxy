"""The chains the lab compares — hypotheses, free in how they work. Each module
has NAME and run(episode) -> {chapters, tests}."""
from variants import cinq_minutes, current, sans_bande_annonce, sans_palmares, un_jeu

VARIANTS = {v.NAME: v for v in (current, un_jeu, sans_palmares, sans_bande_annonce, cinq_minutes)}
