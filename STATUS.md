# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Dernière mise à jour : 2026-10-23.

- **Livré.** La chaîne du labo est portée (PR #14, #15). Les données du labo sont chargées en prod : 1 998 transcriptions et 1 998 lectures. `INGEST=true` depuis le 2026-10-23 ; sauvegarde de l'ancien fichier : `backend_secrets.env.bak-ingest2`.
- **Vérifié (2026-10-23).** L'ingestion en prod transcrit et lit les nouveaux épisodes (Triple Click « Castlevania, Ace Combat… », SoJ ép. 175 « Age of Empires II »). Six anciens épisodes échouent (DeepInfra 400 ou acast 429 sur le MP3 : 5 SoJ `djpod … id=167739, 172373, 179092, 182847, 192378`, Besties « games of 2014 ») ; ils réessaient avec un délai qui double, au plus une fois par jour.
- **Ouvert.**
  - Les six épisodes en échec : voir si c'est le fichier (400) ou acast qui limite (429), ou les laisser.
  - Les épisodes « [Reportage] » sont toujours exclus du catalogue.
  - Nettoyage, branches : fait (19 branches locales mergées supprimées ; reste `v1.4.0_dev`, mergée dans `main` mais en avance sur son origin).
  - **Le resolver de l'app n'est pas celui du labo.** La livraison a chargé les *réponses* du labo (`lab/fiches.py`, `lab_pick` v1, fiche exacte), pas sa façon de résoudre : une question nouvelle en prod passe par `resolver._decide` (`pick`, renvoi au jeu parent). Mesuré le 2026-10-23 sur les 59 questions libérées par #17 : 52 sur la fiche du labo, 7 non (3 mauvaises fiches, 4 sans fiche) ; #18 a remis les 6 corrections en cause. Tout nouvel épisode passe par l'ancien resolver : à porter.
  - Corrections : 27 (après #17 et #18). `l-ordre-des-geants` et `les-tortues-ninja` (noms affichés seuls) ne correspondent plus à aucun nom en prod depuis #17.
- **En attente.** `feat/more-shows` (ORIGAMI, ZQSD, The Back Page, The Game Informer Show).
- **Pour plus tard.** La prochaine relecture de tout l'historique passera par l'API batch d'OpenRouter (−50 %), avec un mode `--batch` dans `lab/read.py`.
