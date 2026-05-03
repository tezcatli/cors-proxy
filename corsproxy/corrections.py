"""
Corrections for games whose podcast name doesn't find the right IGDB entry.

Each entry requires:
  podcast_name  — the raw name extracted from the RSS (matched normalised)
  search_name   — search IGDB with this instead of podcast_name (None = use podcast_name)
  igdb_id       — direct IGDB numeric ID; bypasses name search when set
                  (None = do a name search using search_name or podcast_name)

Once IGDB resolves a game, its display_name is updated to the IGDB name.
Corrections only control HOW to find the right IGDB entry, not what to call it.
"""
from utils import make_slug

CORRECTIONS = [
    {
        "podcast_name": "artic eggs",
        "search_name":  "Arctic Eggs",
    },
    {
        "podcast_name": "make way",
        "search_name":  None,
        "igdb_id":      None,
    },
    {
        "podcast_name": "l'ordre des géants",
        "search_name":  "Indiana Jones and the Great Circle: The Order of Giants",
    },
    {
        "podcast_name": "indiana jones et le cercle ancien",
        "search_name":  "Indiana Jones and the Great Circle",
    },
    {
        "podcast_name": "1348: ex-voto",
        "search_name":  "1348: Ex Voto",
    },
    {
        "podcast_name": "elden ring nightrein",
        "search_name":  "Elden Ring Nightreign",
    },
    {
        "podcast_name": "vendran las aves",
        "search_name":  "Vendrán las aves",
    },
    {
        "podcast_name": "shogun shodown",
        "search_name":  "Shogun Showdown",
    },
    {
        "podcast_name": "eté",
        "search_name":  "Été",
    },
    {
        "podcast_name": "beyond good and evil remastered",
        "search_name":  "Beyond Good & Evil: 20th Anniversary Edition",
    },
    {
        "podcast_name": "top spin 2k25",
        "search_name":  "Top Spin 2K 25",
        "igdb_id":      282959,
    },
    {
        "podcast_name": "zach & wiki",
        "search_name":  "Zack & Wiki",
    },
    {
        "podcast_name": "Les Chevalier de Baphomet",
        "search_name":  "Broken Sword: The Shadow of the Templars",
    },
    {
        "podcast_name": "Process of Elimination: Deluxe Edition",
        "search_name":  "Process of Elimination",
    },
    {
        "podcast_name": "Darksiders2",
        "search_name":  "Darksiders 2",
    },
     {
        "podcast_name": "Little Big Planet",
        "search_name":  "LittleBigPlanet",
    },
    {
        "podcast_name": "Little Big Planet 2",
        "search_name":  "LittleBigPlanet 2",
    },
    {
        "podcast_name": "Little Big Planet 3",
        "search_name":  "LittleBigPlanet 3",
    },
    {
        "podcast_name": "Kirby et le monde oublié",
        "search_name":  "Kirby and the Forgotten World"
    },
    {
        "podcast_name": "Farming Simulator 2022",
        "search_name":  "Farming Simulator 22"
    },
    {
        "podcast_name": "Pokémon Perle & Diamant",
        "search_name":  "Pokémon Pearl Version"
    },
    {
        "podcast_name": "Les gardiens de la galaxie",
        "search_name":  "Marvel's Guardians of the Galaxy"
    },
    {
        "podcast_name": "NBA 2K21 next-gen",
        "search_name":  "NBA 2K21"
    },
    {
        "podcast_name": "Pokémon Epée et Bouclier",
        "search_name":  "Pokémon Sword & Pokémon Shield Double Pack"
    },
    {
        "podcast_name": "Enterre-moi mon amour",
        "search_name":  "Bury me, my Love"
    },

    
]


_BY_SLUG = {make_slug(c["podcast_name"]): c for c in CORRECTIONS}


def find_by_podcast(podcast_name: str):
    return _BY_SLUG.get(make_slug(podcast_name))


def find_by_slug(slug: str):
    return _BY_SLUG.get(slug)
