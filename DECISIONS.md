# Décisions

Ce qui a été tranché, une ligne par décision, avec la date. **À relire avant de proposer.** On ajoute la ligne dans le tour où l'utilisateur tranche, et on n'en rediscute pas sans fait nouveau.

## L'objectif
- L'app sert à écouter des **critiques de jeux vidéo**. Son objet est une **base de tests** : quels jeux un épisode teste, sur quelle fiche, où commence le test, et le verdict. (2026-10)
- On juge toute observation par son effet sur cette base. Chapitres, sections, `kind` : c'est du contexte et du mécanisme, pas des questions éditoriales. Le lecteur montre tous les chapitres, découpés comme la lecture les découpe. (2026-10-22)

## Ce qu'est un test
- Un test, c'est un jeu vidéo auquel les animateurs ont joué et qu'ils jugent. Une news, une mention, un jeu de société, une cérémonie (« Les Silences d'or »), un palmarès, un classement, un best-of ou un GOTY n'en sont pas. Les « Bande-annonce » de SoJ n'en contiennent aucun. (2026-10-22)
- Au moins 5 minutes sur le jeu, sauf si le titre le nomme ; en dessous, on ne distingue pas un test d'une mention. (2026-10-22)
- Le titre propose, la lecture confirme : le jeu du titre est un test si la lecture le trouve, sauf quand elle ne l'a entendu que sans critique. (2026-10-21)
- Les chapitres d'un épisode sont ceux de son flux, sinon ceux de sa lecture. Les chapitres faits par l'ancien pipeline en mai (`chapters.json`) sont retirés : ils masquaient ceux de la lecture sur 601 épisodes SoJ, plus pauvres dans 94 % des cas. Un entretien sans jeu, qui y perd en détail, se règle dans le prompt de lecture, au labo. (2026-10-25)
- Fin du Game : chaque épisode porte sur **un seul jeu**, celui du titre, sur tout l'épisode. (2026-10-22)
- Les apparitions ne comptent pas, seulement les critiques. (2026-10)
- Un test commence à sa critique : sa plus longue section critique, ou les sections critiques qui la précèdent quand seules des pubs les en séparent (une coupure pub coupe un test en deux, pas en deux tests). Le début se juge et se mesure, comme le test et sa fiche. (2026-10-24)

## Fiches
- Une fiche = un jeu : ses DLC, extensions, éditions, portages et remasters sont sur la même fiche ; **seul un remake est à part**. (2026-10-23)
- Deux noms sont un même jeu par leur fiche, pas par leurs mots. (2026-10-23)
- La date de l'épisode ne départage que des homonymes : les podcasts testent des jeux récents, et IGDB est plein d'homonymes anciens. (2026-10)
- Le LLM lit les noms, IGDB connaît les jeux : le modèle n'affirme jamais un fait sur un jeu (les jeux récents sont plus récents que son entraînement). Une résolution est mise en cache : on n'appelle le LLM qu'une fois. (2026-10)
- Les fiches se contrôlent sur tout le catalogue, pas sur un échantillon : chaque fiche qu'un changement de résolution donne ou change est revue. (2026-10-24)

## Pipeline
- Le LLM décrit, le code décide : une règle va dans le code, pas dans le prompt. (2026-10)
- La prod produit, le dev consomme : les données vont de la prod vers le dev ; ce que le dev décide passe par git (`corrections.json`, prompts). (2026-10)
- Le labo définit la chaîne, indépendamment de l'app (l'app suit), avec son critère d'arrêt : aucun test faux, aucune mauvaise fiche, ≥ 90 % trouvés, jugé sur le contrôle. Le labo ne fait pas partie de l'app. (2026-10-22)
- On transcrit nous-mêmes (Whisper turbo sur DeepInfra), et seulement pour en tirer les tests : on ne diffuse pas de transcriptions. (2026-10)
- Verdicts : moyenne sur trois niveaux ; « enthousiaste » compte comme positif. (2026-10)
- Une nouvelle émission passe par le labo avant d'entrer dans l'app (un échantillon jugé, mesuré au critère d'arrêt), et son historique entre par le chemin de livraison du labo (`pack_for_prod.py`), jamais par l'ingestion de la prod. (2026-10-24)
- Nouvelles émissions : ORIGAMI L'Hebdo, ZQSD et The Game Informer Show. The Back Page est mis de côté (peu de tests, des épisodes à thème qui produisent des faux), à reprendre avec la prochaine relecture de tout l'historique. (2026-10-24)

## Interface
- Les décisions d'interface sont dans `frontend/DECISIONS.md` (chargé avec `frontend/CLAUDE.md`) : à relire avant de proposer quoi que ce soit sur l'interface, maquettes comprises. (2026-10-28)

## Écarté (et pourquoi)
- RAG / questions sur les transcriptions (« intégrale des Jiknep ») : abandonné. (2026-10)
- Lexique Whisper (`initial_prompt`) : DeepInfra perdait 60 % des mots ; c'était statique, et ça demandait des informations venues d'ailleurs. Les noms sont corrigés à la lecture, à partir du titre et de la description. (2026-10)
- Accélérer l'audio (×1,5) : ~6 $ une fois, ne vaut pas ffmpeg et le CPU sur le serveur partagé. (2026-10)
- Prompt qui liste directement les tests (`lecture_v2`) : 88 % trouvés contre 96 %. (2026-10-23)
- Giant Bombcast. Les podcasts anglais retenus sont Triple Click et The Besties. (2026-10)
- Une table `resolution_overrides` à côté de `corrections.json` : un seul endroit, versionné.

## Façon de travailler
- Rien ne part en prod (merge sur `main`) avant que l'utilisateur ait testé en dev : le travail reste sur une branche locale jusqu'à son feu vert. (2026-10-25)
- Un test garde une règle (une décision, un invariant, le contrat, la sécurité) ou un bug qui peut revenir : quand une règle change, on réécrit son test plutôt que d'en ajouter un ; le code qui part emporte ses tests. On retire d'abord le code obsolète, puis on fait l'inventaire des tests. (2026-10-25)
- Le contrat (`contracts/api.json`) décrit aussi les éléments des listes et les champs imbriqués : une forme ne s'écrit qu'à cet endroit, jamais à la main dans un test. (2026-10-25)
- Les consoles d'admin (outils de dev) : on teste ce qui protège, l'accès et l'écriture des corrections, pas le détail de leur affichage. (2026-10-25)
- Projet perso, serveur de hobby : une fois le feu vert donné pour une étape en prod, Claude la fait lui-même (sauvegarde avant, vérification après), sans renvoyer les commandes. (2026-10-23)
- Une session par tâche : une tâche livrée, `STATUS.md` réécrit, puis `/clear` plutôt que d'enchaîner ; `STATUS.md` ne dit que l'état présent (git porte l'historique). Les données de dev se lisent par `./peek.sh`, les captures par `tools/shot.sh`, plutôt que par un script ou un navigateur à chaque fois. (2026-10-28)
- La « prod » est un serveur de hobby : Claude y accède librement en lecture (`ssh user@tezcat.fr`, base, journaux) pour diagnostiquer, sans demander ; une écriture se fait avec sauvegarde avant et vérification après. (2026-10-28)
