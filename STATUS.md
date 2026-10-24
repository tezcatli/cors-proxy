# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Dernière mise à jour : 2026-10-24.

- **Livré.** La chaîne du labo est portée (PR #14, #15) et ses données chargées en prod (1 998 transcriptions et lectures) ; `INGEST=true` depuis le 2026-10-23 (sauvegarde : `backend_secrets.env.bak-ingest2`). L'interface « Studio radio » (PR #20). La transcription par morceaux au-delà de 190 Mio, DeepInfra refusant plus de 200 Mio (PR #22) : vérifiée en prod, la Besties « games of 2014 » est transcrite.
- **En cours : le début d'un test coupé par une pub** (branche `fix/test-start`). Un test commence aux sections critiques qui précèdent sa plus longue quand seules des pubs les en séparent : 62 tests sur 3 387 commencent plus tôt dans l'historique (SoJ « Baldur's Gate 3 » de 1:39:42 à 56:22), rien d'autre ne change. Avec la fin et la durée de chaque test sur la page de jugement du labo.
- **En cours : trois nouvelles émissions** (ORIGAMI L'Hebdo, ZQSD, The Game Informer Show), branche `feat/more-shows-lab`, plan en six étapes (`DECISIONS.md` du 2026-10-24). Échantillon jugé (« nouvelles émissions ») : 100 % trouvés ; 1 faux, dans The Back Page, mis de côté ; 4 tests sans fiche. Prochaines étapes :
  1. une résolution v9 dans le labo, qui donne au LLM trois preuves de plus : les fiches que le catalogue donne déjà à un nom écrit pareil (`critiques.same`), les noms alternatifs d'IGDB, la première date de sortie (accès anticipé compris) ;
  2. un audit des **85 tests sans fiche de tout le catalogue** (dont 81 déjà en prod : *Palworld*, *Mewgenics*, *Indiana Jones et le Cercle Ancien*…), chaque fiche trouvée revue ;
  3. les débuts jugés et mesurés (« le test commence ici ») ;
  4. l'historique (~825 h) livré par le labo (`pack_for_prod.py`), avec `INGEST=false` pendant la livraison.
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
