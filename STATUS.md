# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Dernière mise à jour : 2026-10-23.

- **Livré.** La chaîne du labo est portée (PR #14, #15). Les données du labo sont chargées en prod : 1 998 transcriptions et 1 998 lectures. `INGEST=true` depuis le 2026-10-23 ; sauvegarde de l'ancien fichier : `backend_secrets.env.bak-ingest2`.
- **À vérifier.** Que l'ingestion en prod transcrit et lit bien les épisodes parus depuis le 22 :
  `ssh user@tezcat.fr "cd ~/opt/silence && docker compose -f compose.yml logs backend --since 1h | grep -i ingest"`, ou la console `/admin/resolution`.
- **Ouvert.**
  - Les épisodes « [Reportage] » sont toujours exclus du catalogue.
  - Nettoyage : 13 corrections devenues inutiles, la table `lab_resolutions_before_pack`, les branches locales mergées.
- **En attente.** `feat/more-shows` (ORIGAMI, ZQSD, The Back Page, The Game Informer Show).
- **Pour plus tard.** La prochaine relecture de tout l'historique passera par l'API batch d'OpenRouter (−50 %), avec un mode `--batch` dans `lab/read.py`.
