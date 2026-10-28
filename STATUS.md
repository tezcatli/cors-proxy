# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Il ne dit que l'état présent : ce qui a été livré est dans `git log` et les PR, le pourquoi dans `DECISIONS.md`. Dernière mise à jour : 2026-10-28.

## La prod
- En prod : `main` à `efef68f` (PR #39, le retour s'arrête à la Ludothèque dans l'app installée). Elle n'a pas pu être testée en dev, parce que le mode installé demande du HTTPS : c'est à essayer sur le téléphone, avec retour à `c5bafd5` si besoin.
- Podcasts : Silence on Joue, Fin du Game, Triple Click, The Besties, ORIGAMI L'Hebdo, ZQSD et The Game Informer Show. `INGEST=true`.
- Sauvegardes sur le serveur (`~/opt/silence`) : `users.db.bak-<étape>`. La plus récente est `users.db.bak-virtue` (2026-10-28).
- La base de dev n'a pas les lectures d'ORIGAMI, ZQSD et Game Informer (la prod en a 122, 208 et 93) : `./pull-prod-data.sh` les ramène.

## En cours
- Livraison (2026-10-28) de la branche `chore/token-economy`. Elle apporte deux choses.
  - **Les gestes du lecteur sur téléphone** :
    - le retour ferme le plein écran ;
    - on le réduit en le glissant vers le bas ;
    - on ferme le mini-lecteur en le glissant de côté, on l'ouvre en le glissant vers le haut.

    Testés en jsdom et dans un Chromium tactile ; à confirmer sur le téléphone.
  - **Moins de tokens par session** : les décisions d'interface dans `frontend/DECISIONS.md`, `./peek.sh`, `tools/shot.sh`, des tests silencieux. Plus `pack_for_prod.py`, qui ne livre plus de réponse vide.

## Ouvert
- **Les réponses vides du paquet sont rouvertes** (2026-10-28). Le paquet du labo du 2026-10-24 avait livré 222 réponses « aucune fiche », figées jusqu'au TTL. Elles ont été effacées en prod (sauvegarde `users.db.bak-reopen`), puis reposées : 32 fiches trouvées, aucune erreur. `pack_for_prod.py` ne livre plus de réponse vide (branche `chore/token-economy`).
  - Dans le catalogue, 4 fiches changent :
    - « Virtue and a Sledgehammer » (SoJ S20E08) : trouvée ;
    - « Pokémon Diamant Étincelant et Perle Scintillante » : passe de Pokémon Perle au remake ;
    - « Voidbreaker » (Game Informer) : devient Void Breaker 2025 ;
    - « Jump! » (SoJ 2009) : était tombée sur Koron de Jump!!, remise à « aucune fiche » à la main (IGDB n'a pas ce jeu).
  - Les 28 autres fiches trouvées vont à des noms qui ne sont pas des tests. Certaines sont fausses (« crise » → Tricolore Crise, « jeu vidéo » → Ghostbusters, « demo », « 2010 », « riveting rooms » → Riven) ; elles ne se voient pas, mais seraient à revoir si l'un de ces noms devenait un test.
- Tests sans début connu (`timestamp` nul, jamais « en cours ») : ORIGAMI 115 sur 115 dans l'échantillon, ZQSD 28 sur 50, Game Informer 26. Des tests ZQSD partagent un même début.
- Le paquet du labo devrait aussi porter deux choses, pour que la prod ne les redemande pas (prochaine livraison) :
  - les réponses aux noms qui ne sont pas des tests ;
  - les tâches `reviewed`.

  Il reste à mesurer ce que ces noms ont changé dans les tests de la prod (des fusions sont possibles).
- **Une mesure du labo ne garantit pas la réponse de la prod** : le labo et l'app interrogent le LLM chacun de leur côté. C'est pour cela que le paquet livre les réponses du labo.
- Les 5 épisodes SoJ hébergés sur `djpod` sont en échec : acast répond 429 au téléchargement.
- Pour et contre en anglais pour Triple Click, The Besties et The Game Informer Show : c'est la langue du prompt de lecture, à régler dans le labo.
- Les épisodes « [Reportage] » sont toujours exclus du catalogue.
- Corrections : 34. `les-tortues-ninja` ne correspond plus à aucun nom.
- Le catalogue regroupe par nom : une mauvaise fiche dans un podcast entraîne la même dans un autre (Symphonia, entre SoJ et ORIGAMI).
- Les consoles d'admin n'ont pas été restylées : elles héritent seulement des polices et des couleurs.
- Revue de `/changements` à la livraison des nouveaux podcasts : les cas à risque ont été relus, pas les quelque 1 100 autres tests un par un.

## Pour plus tard
- La prochaine relecture de tout l'historique passera par l'API batch d'OpenRouter (−50 %), avec un mode `--batch` dans `lab/read.py`. Deux sujets la rejoindront : The Back Page et la langue des pour et contre.
