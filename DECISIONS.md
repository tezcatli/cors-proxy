# Décisions

Ce qui a été tranché, une ligne par décision, avec la date. **À relire avant de proposer.** On ajoute la ligne dans le tour où l'utilisateur tranche, et on n'en rediscute pas sans fait nouveau.

## L'objectif
- L'app sert à écouter des **critiques de jeux vidéo**. Son objet est une **base de tests** : quels jeux un épisode teste, sur quelle fiche, où commence le test, et le verdict. (2026-10)
- On juge toute observation par son effet sur cette base. Chapitres, sections, `kind` : c'est du contexte et du mécanisme, pas des questions éditoriales. Le lecteur montre tous les chapitres, découpés comme la lecture les découpe. (2026-10-22)

## Ce qu'est un test
- Un test, c'est un jeu vidéo auquel les animateurs ont joué et qu'ils jugent. Une news, une mention, un jeu de société, une cérémonie (« Les Silences d'or »), un palmarès, un classement, un best-of ou un GOTY n'en sont pas. Les « Bande-annonce » de SoJ n'en contiennent aucun. (2026-10-22)
- Au moins 5 minutes sur le jeu, sauf si le titre le nomme ; en dessous, on ne distingue pas un test d'une mention. (2026-10-22)
- Le titre propose, la lecture confirme : le jeu du titre est un test si la lecture le trouve, sauf quand elle ne l'a entendu que sans critique. (2026-10-21)
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
- L'app rend hommage au jeu vidéo, dans toute l'interface ; chaque fiche jeu rend hommage à son jeu : ses couleurs (tirées de ses images) et ses images en vedette. Elle reste une app d'écoute : le lecteur, les tests et le verdict d'abord. La direction se choisit sur maquettes. Remplace *Studio radio* (https://claude.ai/artifact/NT5XTroWYFNjRkMEXyBNnX). (2026-10-24)
- Direction retenue : « la pochette en vedette » (maquettes C′, https://claude.ai/artifact/8CzayrRjeDURCEjrfAwWnm). Sora (titres, libellés) et Inter (texte) ; panneaux sombres teintés de la couleur du jeu, à coins marqués ; sur la fiche, la pochette en grand, droite, sur un fond tiré d'elle (floutée) ; les tests en journal. Pas de simulation de manette, pas de police rétro. (2026-10-25)
- Sur téléphone, un écran = une fonction : ce qui répète une autre partie de l'écran disparaît (le dernier test en grand, qui est la première carte ; la reprise en cours, qui est dans le mini-lecteur) ; les filtres d'émission passent dans un bouton de l'en-tête. Le bureau garde la vitrine. Un bouton dit une action ; son contexte (l'émission, la date) est écrit à côté. (2026-10-25)
- Une grille de pochettes ne répète pas le nom du jeu sous la pochette : la pochette le porte déjà (il reste pour les lecteurs d'écran). (2026-10-25)

- L'accueil est le flux des tests (Reprendre, puis les derniers tests) ; le catalogue des jeux est un onglet, trié par récence. (2026-10-24)
- Un verdict par test, jamais de moyenne par jeu : la fiche le compte par verdict. (2026-10-24)
- Le verdict s'écrit en mot seul : « Positif », « Mitigé », « Négatif » ; un test sans verdict n'affiche rien. Les glyphes (▲ ◆ ▼ ○) n'étaient pas compris. (2026-10-25)
- Une carte de test (accueil) mène à la fiche du jeu, ce test ouvert dans le journal ; l'épisode est un lien du journal. (2026-10-25)
- La page Jeux sert à parcourir le catalogue : des pochettes seules, sans verdicts ni nombre de tests (ils sont sur la fiche) ; recherche, filtres d'émission et tri restent. (2026-10-25)

- Le nom : « Ludothèque », « Ludo » en court (écran d'accueil, mot-symbole `LUDO//`). (2026-10-24)

- Fiche jeu : un artwork en bandeau et une grande pochette qui le chevauche ; les images en planche après les tests, bande-annonce en tête. (2026-10-24)

- Fiche jeu : les tests et un bouton d'écoute au premier écran ; le bandeau et la case « +n » prennent une capture (un artwork répète souvent le logo) ; la fiche technique est en français. (2026-10-24)

- Fiche jeu sur téléphone : le bandeau est la scène de la pochette (assombri, jusqu'aux deux tiers de la pochette), la pochette grande et centrée ; une seule image vedette par écran de téléphone. (2026-10-24)

## Écarté (et pourquoi)
- RAG / questions sur les transcriptions (« intégrale des Jiknep ») : abandonné. (2026-10)
- Lexique Whisper (`initial_prompt`) : DeepInfra perdait 60 % des mots ; c'était statique, et ça demandait des informations venues d'ailleurs. Les noms sont corrigés à la lecture, à partir du titre et de la description. (2026-10)
- Accélérer l'audio (×1,5) : ~6 $ une fois, ne vaut pas ffmpeg et le CPU sur le serveur partagé. (2026-10)
- Prompt qui liste directement les tests (`lecture_v2`) : 88 % trouvés contre 96 %. (2026-10-23)
- Giant Bombcast. Les podcasts anglais retenus sont Triple Click et The Besties. (2026-10)
- Une table `resolution_overrides` à côté de `corrections.json` : un seul endroit, versionné.

## Façon de travailler
- Projet perso, serveur de hobby : une fois le feu vert donné pour une étape en prod, Claude la fait lui-même (sauvegarde avant, vérification après), sans renvoyer les commandes. (2026-10-23)
