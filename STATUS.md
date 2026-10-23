# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Dernière mise à jour : 2026-10-24.

- **Livré.** La chaîne du labo est portée (PR #14, #15). Les données du labo sont chargées en prod : 1 998 transcriptions et 1 998 lectures. `INGEST=true` depuis le 2026-10-23 ; sauvegarde de l'ancien fichier : `backend_secrets.env.bak-ingest2`.
- **Vérifié (2026-10-23).** L'ingestion en prod transcrit et lit les nouveaux épisodes (Triple Click « Castlevania, Ace Combat… », SoJ ép. 175 « Age of Empires II »). Six anciens épisodes échouent (DeepInfra 400 ou acast 429 sur le MP3 : 5 SoJ `djpod … id=167739, 172373, 179092, 182847, 192378`, Besties « games of 2014 ») ; ils réessaient avec un délai qui double, au plus une fois par jour.
- **En cours : refonte de l'interface « Studio radio »** (PR #20, branche `feat/ui-studio-radio`, en attente de merge). Faits : le verdict, les pour et contre de chaque test remontent dans l'API (`critique`, `verdicts` au catalogue, pochette et fiche de chaque test du flux) ; nouveau système visuel (noir, jaune « on air », Barlow / Barlow Condensed / JetBrains Mono, angles droits) ; accueil = « Tests » (Reprendre + derniers tests), catalogue sur `/jeux` trié par récence ; fiche jeu = tableau des tests avec verdicts et pour/contre ; page épisode = tests d'abord, toujours un bouton Écouter ; lecteur : test suivant/précédent, vitesse, vue « En lecture » sur téléphone ; barre d'onglets en bas sur mobile ; icône `LUDO//`. Reste : DaisyUI encore là (rethémé, sert aux consoles admin) ; recherche unique jeux + épisodes ; nom de l'app à trancher.
- **Ouvert.**
  - Les six épisodes en échec : voir si c'est le fichier (400) ou acast qui limite (429), ou les laisser.
  - Les épisodes « [Reportage] » sont toujours exclus du catalogue.
  - Nettoyage, branches : fait (19 branches locales mergées supprimées ; reste `v1.4.0_dev`, mergée dans `main` mais en avance sur son origin).
  - **Une mesure du labo ne garantit pas la réponse de la prod.** Les 59 questions libérées par #17, résolues par la prod : 52 sur la page du labo ; 2 sur une autre page *par la règle des pages* (IGDB classe *The 7th Guest Remake* comme portage de *The 7th Guest VR*, *1001 Spikes* comme version étendue d'*Aban Hawkins*) ; 4 sans fiche, le LLM ayant répondu autrement qu'au labo (*1348: Ex Voto*, *Left 4 Dead*, *Mario & Luigi: Paper Jam*, *Batman: Arkham Asylum*). #18 a remis ces 6 corrections. Le resolver de l'app est bien la v1 du labo.
  - Corrections : 27 (après #17 et #18). `l-ordre-des-geants` et `les-tortues-ninja` (noms affichés seuls) ne correspondent plus à aucun nom en prod depuis #17.
- **En attente.** `feat/more-shows` (ORIGAMI, ZQSD, The Back Page, The Game Informer Show).
- **Pour plus tard.** La prochaine relecture de tout l'historique passera par l'API batch d'OpenRouter (−50 %), avec un mode `--batch` dans `lab/read.py`.
