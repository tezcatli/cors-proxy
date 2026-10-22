# Le labo

On y **définit** la chaîne de lecture : quels jeux pour un épisode, à quel niveau, sur quelle fiche IGDB, avec quels chapitres. On la valide sur ton jugement avant de la porter dans l'app. Le labo ne fait pas partie de l'app : celle-ci ne l'importe jamais et il n'entre pas dans l'image de prod.

```bash
./pull-prod-data.sh                                     # les données de la prod en dev (sans les comptes)
docker compose -f docker-compose.dev.yml up lab         # http://localhost:5050
docker compose -f docker-compose.dev.yml run --rm lab python -m pytest tests
```

- **`reference.json`** : les épisodes de référence. Une part est tirée au hasard par émission et par période, ce qui la rend représentative ; l'autre part regroupe les modes d'échec connus.
- **`spec.json`** (versionné) : la spécification, **indépendante de toute variante**. Pour chaque jeu d'un épisode de référence, le niveau qu'il *devrait* avoir (`consacré`, `évoqué`, `absent`) et la fiche IGDB qu'il est (une fiche, ou `absent` d'IGDB). On la remplit dans la page « Juger » : la frise de l'épisode, et tous les jeux qu'une source propose (titre, description, chapitres, lecture), plus ceux que tu ajoutes. L'app la rejouera comme test d'acceptation une fois la variante portée.
- **`candidates.py`** : ces candidats et la frise ; **`spec.py`** : la lecture et l'écriture de la spécification.
- **`variants/`** : les chaînes comparées, chacune avec `run(episode) -> {read, games}`. `current` est la chaîne de l'app telle qu'elle est.
- **`snapshot.py`** : la base de dev, ouverte en **lecture seule**. Les modules de l'app sont utilisés comme bibliothèques et ne sont jamais modifiés.

**Critère d'arrêt**, fixé avant d'itérer : aucun « consacré » faux, c'est-à-dire ni un épisode rattaché à tort au premier niveau d'une fiche, ni une mauvaise fiche IGDB ; et au moins 90 % de l'ensemble des jugements respectés.
