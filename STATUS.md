# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Dernière mise à jour : 2026-10-24.

- **Livré.** La chaîne du labo est portée (PR #14, #15) et ses données chargées en prod (1 998 transcriptions et lectures) ; `INGEST=true` depuis le 2026-10-23 (sauvegarde : `backend_secrets.env.bak-ingest2`). L'interface « Studio radio » (PR #20). La transcription par morceaux au-delà de 190 Mio, DeepInfra refusant plus de 200 Mio (PR #22) : vérifiée en prod, la Besties « games of 2014 » est transcrite.
- **Livré (2026-10-24) : le début d'un test coupé par une pub** (PR #23, `9c21a93`, déployé, `/healthz` ok) : 62 tests de l'historique commencent plus tôt (SoJ « Baldur's Gate 3 » à 56:22).
- **En cours : trois nouvelles émissions** (ORIGAMI L'Hebdo, ZQSD, The Game Informer Show), branche `feat/more-shows-lab`, non poussée. The Back Page est retiré. Fait :
  - la résolution v9 (labo, puis portée dans `resolver._unsearched`) : les fiches que le catalogue donne déjà à un nom écrit pareil, les noms alternatifs d'IGDB, la première date de sortie. Sur les 211 tests jugés, 7 mauvaises fiches → 2 (Spiderbot, déjà faux ; Overwatch, un homonyme que le LLM tranche à pile ou face). Sur les 84 tests sans fiche du catalogue, 43 en reçoivent une (42 justes, « L'histoire de Tomb Raider » discutable). Sur 200 tests déjà résolus, aucune régression ;
  - la mesure « nouvelles émissions » : 68 tests, 100 % trouvés, 0 faux, 0 mauvaise fiche → **critère atteint** ;
  - les débuts : « changer le début » sur la page de jugement, « début faux » (> 1 min) dans `/mesure` et dans le critère.

  Reste :
  1. **l'utilisateur juge les débuts** des 26 épisodes « nouvelles émissions » ;
  2. la livraison : l'historique (~825 h) transcrit, lu et résolu en dev, `/changements`, `pack_for_prod.py`, puis en prod `INGEST=false`, déploiement, `push-lab-data.sh`, `INGEST=true`. **Le paquet ne doit remplir que les questions sans réponse** : en remplacer une donnée, ce serait y mettre l'aléa du labo (Overwatch, juste en prod).
- **Ouvert.**
  - Les 5 SoJ `djpod` en échec : acast répond 429 au téléchargement.
  - `67c9a8d0…` est bloqué en « LLM unavailable », avec un nouvel essai prévu le 2026-10-22, une date passée.
  - En dev, le conteneur backend n'a pas la clé du LLM (`ingest.py` transcrit sans lire).
  - Recherche unique jeux + épisodes (prévue, pas faite).
  - Pour et contre en anglais pour Triple Click et The Besties : langue du prompt de lecture, à régler dans le labo.
  - Les épisodes « [Reportage] » sont toujours exclus du catalogue.
  - **Une mesure du labo ne garantit pas la réponse de la prod** : le labo et l'app interrogent le LLM chacun de leur côté et ne répondent pas toujours pareil (encore Endless Legend II et 33 Immortals le 2026-10-24). D'où la livraison des réponses du labo par le paquet.
  - Corrections : 27. `l-ordre-des-geants` et `les-tortues-ninja` ne correspondent plus à aucun nom en prod.
- **Pour plus tard.** La prochaine relecture de tout l'historique passera par l'API batch d'OpenRouter (−50 %), avec un mode `--batch` dans `lab/read.py` ; The Back Page et la langue des pour et contre la rejoindront.
