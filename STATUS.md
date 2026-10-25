# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Dernière mise à jour : 2026-10-25.

- **Livré.** La chaîne du labo est portée (PR #14, #15), la transcription par morceaux au-delà de 190 Mio (PR #22), le début d'un test coupé par une pub (PR #23).
- **Livré (2026-10-24) : trois nouvelles émissions**, ORIGAMI L'Hebdo, ZQSD et The Game Informer Show (PR #24). The Back Page est mis de côté.
  - La résolution v9 est portée (`resolver._unsearched`).
  - L'historique a été transcrit, lu et résolu en dev, puis livré par `push-lab-data.sh`.
  - Revue de `/changements` : 7 corrections ajoutées. Les cas à risque ont été relus, mais pas les quelque 1 100 autres tests un par un.
  - `INGEST=true` ; l'ingestion n'a retranscrit aucun épisode de l'historique. Le sweep de la prod a répondu aux 1 019 noms que le paquet ne portait pas, avec 954 jeux trouvés et aucune erreur.
  - Sauvegardes : `backend_secrets.env.bak-shows`, `users.db.bak-shows`.
- **Livré (2026-10-25) : l'interface « hommage »** (PR #26), qui remplace Studio radio. Elle a été choisie sur maquettes : https://claude.ai/artifact/8CzayrRjeDURCEjrfAwWnm, rangée C′.
  - Chaque fiche, tuile, page épisode et le lecteur prennent les couleurs de la pochette de leur jeu (`useGameTheme`, palettes gardées en `localStorage`).
  - La fiche montre la pochette en vedette et les tests en journal. Le verdict s'écrit en mot seul.
  - Un seul écran, la Ludothèque (PR #28), à la place des onglets Tests et Jeux qui montraient le même écran en double : la vitrine du dernier test (bureau) et Reprendre, les nouveaux tests en rangée (une carte par test, qui mène à la fiche), puis tous les jeux en grille. Une seule recherche, le filtre d'émission et le tri dans l'en-tête ; plus de barre d'onglets sur téléphone.
- **Livré (2026-10-25) : ce qui passe** (PR #29) : le lecteur et la session média suivent la position, la pochette du test en cours sinon le visuel du podcast.
- **Livré (2026-10-25) : une page par podcast et une seule écoute** (PR #30, testé en dev par l'utilisateur avant la prod ; maquettes https://claude.ai/artifact/BZBqq7njbYNcYAN2fhYvWD).
  - La rangée « Les podcasts » sur la Ludothèque remplace le filtre de l'en-tête ; la page du podcast (`/podcast/:id`) : écouter le dernier épisode ou reprendre, tous ses épisodes par année, ses jeux. L'image d'un podcast vient de son flux, sa couleur du registre (`lib/podcasts.js`).
  - La page épisode : une liste de moments au même gabarit ; un test y mène à sa fiche, où est l'avis.
  - La recherche trouve aussi les épisodes par leur titre. Un titre trop long défile dans le lecteur.
  - Fiche jeu : on glisse entre la pochette, la bande-annonce et les images (`MediaViewer`) ; le journal des tests est aligné, une cible par action (▶, ↗, ⌄).
- **Livré (2026-10-25) : la durée des tests** sur la fiche jeu (« 13 min »), à la place de l'heure de début (PR #31, `critiques.span`, recalculée des lectures, sans migration). En prod, tous les tests contrôlés (763 sur 400 fiches) ont une durée. La base de dev n'a pas les lectures d'ORIGAMI, ZQSD et Game Informer (la prod en a 122, 208 et 93) : `pull-prod-data.sh` les ramènerait. Sauvegarde : `users.db.bak-duration`.
- **Livré (2026-10-25) : le code obsolète retiré** (PR #32). Les épisodes SoJ montrent les chapitres de la lecture (`chapters.json` retiré). Sont aussi retirés : la migration de l'ancien cache IGDB, les `ALTER TABLE is_admin`, l'ancien schéma IGDB (`category`) et le code mort du frontend. Sauvegarde : `users.db.bak-obsolete`. 
- **Livré (2026-10-25) : les tests suivent les règles** (PR #33). Doublons fusionnés, tests sur données réécrits, tests morts retirés, variantes paramétrées, contrat étendu (listes, champs imbriqués, absents), `test_games.py` découpé par module, tests d'interface sans classes CSS. Backend : 324 fonctions → 259 (378 cas → 324), frontend : 195 → 167. Couverture identique sauf `review.py` (affichage de la console, décision du 2026-10-25).
- **Livré (2026-10-25) : un test par épisode sur une fiche** (PR #34). Deux noms d'un même jeu dans un épisode sont un seul test (`serializers.tests_of`), celui dont l'avis a été lu. En dev, une seule fiche était touchée (`assassin-s-creed-iii`).
- **Ouvert.**
  - Tests sans début connu (`timestamp` nul, jamais « en cours ») : ORIGAMI 115 sur 115 dans l'échantillon, ZQSD 28 sur 50, Game Informer 26. Des tests ZQSD partagent un même début ; des chapitres Game Informer, tirés de la description, sont collés en un seul (« Introduction03:25 - … »).
  - Le paquet du labo devrait aussi porter les réponses des noms qui ne sont pas des tests, et les tâches `reviewed`, pour que la prod ne les redemande pas (prochaine livraison). Il reste à mesurer ce que ces noms ont changé dans les tests de la prod (des fusions possibles).
  - Les 5 SoJ `djpod` en échec : acast répond 429 au téléchargement.
  - Les consoles d'admin n'ont pas été restylées. Elles héritent seulement des polices et des couleurs.
  - Recherche unique jeux + épisodes (prévue, pas faite).
  - Pour et contre en anglais pour Triple Click, The Besties et The Game Informer Show : langue du prompt de lecture, à régler dans le labo.
  - Les épisodes « [Reportage] » sont toujours exclus du catalogue.
  - **Une mesure du labo ne garantit pas la réponse de la prod** : le labo et l'app interrogent le LLM chacun de leur côté, d'où la livraison des réponses du labo par le paquet.
  - Corrections : 34. `les-tortues-ninja` ne correspond plus à aucun nom.
  - Le catalogue regroupe par nom : une mauvaise fiche d'une émission entraîne celle d'une autre (Symphonia, SoJ et ORIGAMI).
- **Pour plus tard.** La prochaine relecture de tout l'historique passera par l'API batch d'OpenRouter (−50 %), avec un mode `--batch` dans `lab/read.py`. The Back Page et la langue des pour et contre la rejoindront.
