# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Dernière mise à jour : 2026-10-23.

- **Livré.** La chaîne du labo est portée (PR #14, #15). Les données du labo sont chargées en prod : 1 998 transcriptions et 1 998 lectures. `INGEST=true` depuis le 2026-10-23 ; sauvegarde de l'ancien fichier : `backend_secrets.env.bak-ingest2`.
- **Vérifié (2026-10-23).** L'ingestion en prod transcrit et lit les nouveaux épisodes (Triple Click « Castlevania, Ace Combat… », SoJ ép. 175 « Age of Empires II »). Six anciens épisodes échouent (DeepInfra 400 ou acast 429 sur le MP3 : 5 SoJ `djpod … id=167739, 172373, 179092, 182847, 192378`, Besties « games of 2014 ») ; ils réessaient avec un délai qui double, au plus une fois par jour.
- **Ouvert.**
  - Les six épisodes en échec : voir si c'est le fichier (400) ou acast qui limite (429), ou les laisser.
  - Les épisodes « [Reportage] » sont toujours exclus du catalogue.
  - Nettoyage, branches : fait (19 branches locales mergées supprimées ; reste `v1.4.0_dev`, mergée dans `main` mais en avance sur son origin).
  - Nettoyage, corrections : 6 ne correspondent plus à aucun nom du catalogue (prod, `unmatched_slugs`) : `beyond-good-and-evil-remastered`, `danganrompa`, `donkey-kong`, `l-orange-box`, `la-legende-de-pac-man`, `les-chevalier-de-baphomet`. Pour les autres, savoir lesquelles la chaîne résout seule sur la même fiche demande de résoudre sans corrections : `lab_fiches` les applique déjà (`question_for`), et la clé OpenRouter manque dans le `backend_secrets.env` de dev.
- **En attente.** `feat/more-shows` (ORIGAMI, ZQSD, The Back Page, The Game Informer Show).
- **Pour plus tard.** La prochaine relecture de tout l'historique passera par l'API batch d'OpenRouter (−50 %), avec un mode `--batch` dans `lab/read.py`.
