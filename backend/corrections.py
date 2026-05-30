"""
Corrections for games whose podcast name doesn't find the right IGDB entry.

Each entry requires:
  podcast_name  — the raw name extracted from the RSS (matched normalised)
  search_name   — search IGDB with this instead of podcast_name (None = use podcast_name)
  igdb_id       — direct IGDB numeric ID; bypasses name search when set
                  (None = do a name search using search_name or podcast_name)

Optional fields:
  hint_date     — ISO date string (YYYY-MM-DD). Dual purpose:
                  1. Selects this correction only when the episode's pub_ts falls on
                     the same UTC calendar date (exact day match).
                  2. Passed to IGDB as the date hint for the search window.
                  Corrections without hint_date are undated fallbacks.
  display_name  — Override the display_name stored in the DB after IGDB resolution,
                  instead of using the IGDB result name.

Multiple entries may share the same podcast_name (differentiated by hint_date).
Dated corrections take priority over undated ones; undated ones are the fallback.

Once IGDB resolves a game, its display_name is updated to the IGDB name unless
a display_name override is set in the correction.
"""
import datetime
from utils import make_slug

CORRECTIONS = [
    {
        "podcast_name": "artic eggs",
        "search_name":  "Arctic Eggs",
    },
    {
        "podcast_name": "l'ordre des géants",
        "search_name":  "Indiana Jones and the Great Circle: The Order of Giants",
        "display_name": "Indiana Jones et le Cercle Ancien: L'Ordre des Géants",
    },
    {
        "podcast_name": "indiana jones et le cercle ancien",
        "search_name":  "Indiana Jones and the Great Circle",
        "display_name": "Indiana Jones et le Cercle Ancien",
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
        "display_name": "Les Chevalier de Baphomet",
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
        "podcast_name": "LittleBigPlanet2",
        "search_name":  "LittleBigPlanet 2",
    },
    {
        "podcast_name": "Little Big Planet 3",
        "search_name":  "LittleBigPlanet 3",
    },
    {
        "podcast_name": "Kirby et le monde oublié",
        "search_name":  "Kirby and the Forgotten World",
        "display_name": "Kirby et le monde oublié",
    },
    {
        "podcast_name": "Farming Simulator 2022",
        "search_name":  "Farming Simulator 22"
    },
    {
        "podcast_name": "Pokémon Perle & Diamant",
        "search_name":  "Pokémon Pearl Version",
        "display_name": "Pokémon Perle & Diamant",
    },
    {
        "podcast_name": "Les gardiens de la galaxie",
        "search_name":  "Marvel's Guardians of the Galaxy",
        "display_name": "Les gardiens de la galaxie",
    },
    {
        "podcast_name": "NBA 2K21 next-gen",
        "search_name":  "NBA 2K21"
    },
    {
        "podcast_name": "Pokémon Epée et Bouclier",
        "search_name":  "Pokémon Sword & Pokémon Shield Double Pack",
        "display_name": "Pokémon Epée et Bouclier"
    },
    {
        "podcast_name": "Enterre-moi mon amour",
        "search_name":  "Bury me, my Love",
        "display_name": "Enterre-moi mon amour",
    },
    {
        "podcast_name": "star wars",
        "search_name":  "Star Wars: The Force Unleashed",
        "display_name": "Star Wars: Le Reveil de la Force",
    },
    {
        "podcast_name": "hades 2",
        "search_name":  "Hades II",
        "hint_date": "2024-05-10",
    },
    {
        "podcast_name": "civilization 6",
        "search_name":  "Sid Meier's Civilization VI"
    },
    {
        "podcast_name": "Heroes of the Storm",
        "igdb_id":      7313,
    },
    {
        "podcast_name": "Mario + Lapins Crétins : Sparks of Hope",
        "search_name":  "Mario + Rabbids Sparks of Hope",
        "display_name": "Mario + Lapins Crétins : Sparks of Hope",
    },
    {
        "podcast_name": "Mario et les Lapins Crétins",
        "search_name":  "Mario + Rabbids Kingdom Battle",
        "display_name": "Mario et les Lapins Crétins",
    },
    {
        "podcast_name": "Mario et Luigi",
        "hint_date": "2015-12-17",
        "search_name":  "Mario & Luigi: Paper Jam",
    },
    {
        "podcast_name": "MGS 4",
        "search_name":  "Metal Gear Solid 4: Guns of the Patriots",
    },
    {
        "podcast_name": "Pokémon Ecarlate et Violet",
        "search_name":  "Pokémon Scarlet and Pokémon Violet Double Pack",
        "display_name": "Pokémon Ecarlate et Violet",
    },
    {
        "podcast_name": "Les tortues ninja",
        "search_name":  "Teenage Mutant Ninja Turtles: Shredder's Revenge",
        "display_name": "Les Tortues Ninja : La revenche de Shredder",
        "hint_date": "2022-06-24",
    },
    {
        "podcast_name": "xcom2",
        "search_name":  "xcom 2",
    },
    {
        "podcast_name": "l'ombre de Mordor",
        "search_name":  "Middle-earth: Shadow of Mordor",
    },
    {
        "podcast_name": "l'orange box",
        "search_name":  "The Orange Box",
    },
    {
        "podcast_name": "rhythm Paradise megamix",
        "search_name":  "Rhythm Heaven Megamix",
        "display_name": "Rhythm Paradise Megamix",
    },
    {
        "podcast_name": "rhythm Paradise",
        "search_name":  "Rhythm Heaven",
        "display_name": "Rhythm Paradise",
    },
    {
        "podcast_name": "forza motosport",
        "search_name":  "Forza Motorsport 4",
        "hint_date": "2011-10-20",
    },
    {
        "podcast_name": "Pokémon X & Y",
        "search_name":  "Pokémon X",
        "display_name": "Pokémon X & Y",
    },
    {
        "podcast_name": "Bayonetta est-elle sexy?",
        "search_name":  "Bayonetta",    
    },
    {
        "podcast_name": "la rentrée avec Batman",
        "search_name":  "Batman: Arkham Asylum",
    },  
    {
        "podcast_name": "Street Fighter IV sur iPhone",
        "search_name":  "Street Fighter IV",
    }, 
    {
        "podcast_name": "PixelJunk Shooter2",
        "search_name":  "PixelJunk Shooter 2",
    },
    {
        "podcast_name": "la légende de Pac-man",
        "igdb_id":  2750,
    },
    {
        "podcast_name": "Danganrompa",
        "hint_date": "2014-03-27",
        "igdb_id":  9708,
    },
    {
        "podcast_name": "elec head",
        "search_name":  "elechead",
    },
    {
        "podcast_name": "Fortnite Battle Royale",
        "igdb_id":  1905,
    },
    {
        "podcast_name": "Broken Age acte 2",
        "igdb_id":  3087
    },
    {
        "podcast_name": "Might & Magic sur DS",
        "search_name":  "Might & Magic: Clash of Heroes",
    },
    {
        "podcast_name": "Lego City 3DS",
        "search_name":  "LEGO City Undercover",
    },
    {
        "podcast_name": "L'histoire de Tomb Raider",
        "igdb_id":  912,
    },
    {
        "podcast_name": "La ferme des animaux",
        "search_name":  "Orwell's Animal Farm",
    },
    {
        "podcast_name": "Soldats inconnus",
        "search_name":  "Valiant Hearts: The Great War",
        "display_name": "Soldats inconnus : Mémoires de la Grande Guerre",
    },
    {
        "podcast_name": "la chance du locataire",
        "search_name":  "Luck be a Landlord",
        "display_name": "La chance du locataire",
    },
    {
        "podcast_name": "La fin des Samouraïs",
        "search_name":  "Total War: Shogun 2 - Fall of the Samurai",
    },
    {
        "podcast_name": "make way",
        "search_name":  None,
        "igdb_id":      258230,
    },
]

_BY_SLUG: dict = {}
for _c in CORRECTIONS:
    hd    = _c.get('hint_date')
    entry = {**_c, '_date': datetime.date.fromisoformat(hd) if hd else None}
    _BY_SLUG.setdefault(make_slug(_c['podcast_name']), []).append(entry)


def _hint_date_matches(c: dict, pub_ts) -> bool:
    parsed = c.get('_date')
    if parsed is None:
        hd = c.get('hint_date')
        if not hd:
            return False
        parsed = datetime.date.fromisoformat(hd)
    if pub_ts is None:
        return False
    return datetime.datetime.fromtimestamp(pub_ts, datetime.timezone.utc).date() == parsed


def _find(slug: str, pub_ts):
    candidates = _BY_SLUG.get(slug, [])
    for c in candidates:
        if _hint_date_matches(c, pub_ts):
            return c
    for c in candidates:
        if not c.get('hint_date'):
            return c
    return None


def find_by_podcast(podcast_name: str, pub_ts=None):
    return _find(make_slug(podcast_name), pub_ts)


def find_by_slug(slug: str, pub_ts=None):
    return _find(slug, pub_ts)
