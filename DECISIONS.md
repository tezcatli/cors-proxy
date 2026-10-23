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

## Fiches
- Une fiche = un jeu : ses DLC, extensions, éditions, portages et remasters sont sur la même fiche ; **seul un remake est à part**. (2026-10-23)
- Deux noms sont un même jeu par leur fiche, pas par leurs mots. (2026-10-23)
- La date de l'épisode ne départage que des homonymes : les podcasts testent des jeux récents, et IGDB est plein d'homonymes anciens. (2026-10)
- Le LLM lit les noms, IGDB connaît les jeux : le modèle n'affirme jamais un fait sur un jeu (les jeux récents sont plus récents que son entraînement). Une résolution est mise en cache : on n'appelle le LLM qu'une fois. (2026-10)

## Pipeline
- Le LLM décrit, le code décide : une règle va dans le code, pas dans le prompt. (2026-10)
- La prod produit, le dev consomme : les données vont de la prod vers le dev ; ce que le dev décide passe par git (`corrections.json`, prompts). (2026-10)
- Le labo définit la chaîne, indépendamment de l'app (l'app suit), avec son critère d'arrêt : aucun test faux, aucune mauvaise fiche, ≥ 90 % trouvés, jugé sur le contrôle. Le labo ne fait pas partie de l'app. (2026-10-22)
- On transcrit nous-mêmes (Whisper turbo sur DeepInfra), et seulement pour en tirer les tests : on ne diffuse pas de transcriptions. (2026-10)
- Verdicts : moyenne sur trois niveaux ; « enthousiaste » compte comme positif. (2026-10)

## Interface
- Direction visuelle *Studio radio* : noir pur, un seul accent jaune (`#ffd23f`) réservé à ce qui joue, Barlow Condensed (titres), Barlow (texte), JetBrains Mono (libellés, timecodes), angles droits et filets, verdict en glyphe et mot (▲ POSITIF, ◆ MITIGÉ, ▼ NÉGATIF, ○ NON LU) ; plus d'accent tiré des pochettes. Maquettes : https://claude.ai/artifact/NT5XTroWYFNjRkMEXyBNnX. (2026-10-24)

- L'accueil est le flux des tests (Reprendre, puis les derniers tests) ; le catalogue des jeux est un onglet, trié par récence. (2026-10-24)
- Un verdict par test, jamais de moyenne par jeu : la tuile montre un glyphe par test, la fiche le compte par verdict. (2026-10-24)

- Le nom : « Ludothèque », « Ludo » en court (écran d'accueil, mot-symbole `LUDO//`). (2026-10-24)

- Fiche jeu : un artwork en bandeau et une grande pochette qui le chevauche ; les images en planche après les tests, bande-annonce en tête. (2026-10-24)

- Fiche jeu : les tests et un bouton d'écoute au premier écran ; le bandeau et la case « +n » prennent une capture (un artwork répète souvent le logo) ; la fiche technique est en français. (2026-10-24)

## Écarté (et pourquoi)
- RAG / questions sur les transcriptions (« intégrale des Jiknep ») : abandonné. (2026-10)
- Lexique Whisper (`initial_prompt`) : DeepInfra perdait 60 % des mots ; c'était statique, et ça demandait des informations venues d'ailleurs. Les noms sont corrigés à la lecture, à partir du titre et de la description. (2026-10)
- Accélérer l'audio (×1,5) : ~6 $ une fois, ne vaut pas ffmpeg et le CPU sur le serveur partagé. (2026-10)
- Prompt qui liste directement les tests (`lecture_v2`) : 88 % trouvés contre 96 %. (2026-10-23)
- Giant Bombcast. Les podcasts anglais retenus sont Triple Click et The Besties. (2026-10)
- Une table `resolution_overrides` à côté de `corrections.json` : un seul endroit, versionné.

## Façon de travailler
- Projet perso, serveur de hobby : une fois le feu vert donné pour une étape en prod, Claude la fait lui-même (sauvegarde avant, vérification après), sans renvoyer les commandes. (2026-10-23)
