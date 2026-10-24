# Où on en est

À **réécrire** (pas à compléter) quand l'état change. Dernière mise à jour : 2026-10-24.

- **Livré.** La chaîne du labo est portée (PR #14, #15), l'interface « Studio radio » (PR #20), la transcription par morceaux au-delà de 190 Mio (PR #22), le début d'un test coupé par une pub (PR #23).
- **Livré (2026-10-24) : trois nouvelles émissions**, ORIGAMI L'Hebdo, ZQSD et The Game Informer Show (PR #24, `de2941b`, déployé, `/healthz` ok). The Back Page est mis de côté.
  - La résolution v9 est portée (`resolver._unsearched`) : sur les 211 tests jugés, les mauvaises fiches passent de 7 à 2.
  - L'historique a été transcrit (398 épisodes, 788 h, 9,44 $), lu (~2,50 $) et résolu en dev, puis livré par `push-lab-data.sh` : +431 transcriptions et lectures, +308 jeux, 1 171 questions qui reçoivent un jeu. Sauvegardes : `backend_secrets.env.bak-shows`, `users.db.bak-shows`.
  - La revue (`/changements`) : +1 230 tests sur les nouvelles émissions. Sur les anciennes, 5 changements, tous justes, et aucun test retiré. Les 122 cas à risque (sans fiche, ou jeu loin de la date de l'épisode) ont été relus et ont donné 7 corrections (`corrections.json`). Les ~1 100 autres tests n'ont pas été relus un par un.
  - `INGEST=true` depuis 20:08 UTC ; l'ingestion n'a retranscrit aucun épisode de l'historique.
- **En cours en prod.** Le sweep répond aux ~1 000 questions des **mentions** des nouvelles émissions : le paquet ne porte que les fiches des tests (`resolve.py --fiches` ne décide que les tests). Avant, la prod demande au LLM les jeux annoncés par la description de chaque nouvel épisode (`reviewed`), une tâche que le paquet ne contenait pas non plus. Vérifier que le sweep se termine.
- **À vérifier à l'écran** (pas d'accès sans compte à l'API de prod) : les trois émissions dans le catalogue, et quelques fiches corrigées (*Symphonia*, *Far Cry 5*, *Donkey Kong Bananza*).
- **Ouvert.**
  - Les 5 SoJ `djpod` en échec : acast répond 429 au téléchargement.
  - Le paquet devrait aussi porter les réponses des mentions et les `reviewed`, pour que la prod ne les redemande pas (prochaine livraison).
  - Recherche unique jeux + épisodes (prévue, pas faite).
  - Pour et contre en anglais pour Triple Click, The Besties et The Game Informer Show : langue du prompt de lecture, à régler dans le labo.
  - Les épisodes « [Reportage] » sont toujours exclus du catalogue.
  - **Une mesure du labo ne garantit pas la réponse de la prod** : le labo et l'app interrogent le LLM chacun de leur côté. D'où la livraison des réponses du labo par le paquet.
  - Corrections : 34. `les-tortues-ninja` ne correspond plus à aucun nom.
  - Le catalogue regroupe par nom : une mauvaise fiche d'une émission entraîne celle d'une autre (Symphonia, SoJ et ORIGAMI).
- **Pour plus tard.** La prochaine relecture de tout l'historique passera par l'API batch d'OpenRouter (−50 %, ~5 $ d'économie), avec un mode `--batch` dans `lab/read.py`. The Back Page et la langue des pour et contre la rejoindront.
