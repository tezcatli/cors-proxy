import datetime
from unittest.mock import patch, MagicMock

import pytest

import games as games_module
from contract import assert_contract, CONTRACT
from conftest import auth_header
from rss import extract_game_names as _extract_game_names, extract_legacy_names as _extract_legacy_names, extract_fdg_names as _extract_fdg_names, parse_feed as _parse_feed, assign_url_slugs as _assign_url_slugs, sanitize_html as _sanitize_html
from podcasts import PODCAST_BY_ID

GAMES = CONTRACT['games']

MINIMAL_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <item>
      <title>On a joue a \xc2\xabZelda\xc2\xbb et \xc2\xabMario Kart\xc2\xbb</title>
      <guid isPermaLink="false">ep1guid</guid>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="0" />
      <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
      <description>00:30 Zelda
01:00 Mario Kart
01:30 Outro</description>
    </item>
    <item>
      <title>Quelle est la meilleure plateforme ?</title>
      <guid isPermaLink="false">ep2guid</guid>
      <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="0" />
      <pubDate>Mon, 08 Jan 2024 00:00:00 +0000</pubDate>
      <description>No games here</description>
    </item>
  </channel>
</rss>"""

# Fix the guillemet bytes in the constant (they were escaped above for clarity)
MINIMAL_RSS = MINIMAL_RSS.replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())


def mock_rss_response(content=MINIMAL_RSS, status=200):
    m = MagicMock()
    m.content = content
    m.status_code = status
    m.raise_for_status.return_value = None
    return m


# ── _extract_game_names ───────────────────────────────────────────────────────

def test_extract_game_names_guillemets():
    names = _extract_game_names('On a joué à «Zelda» et «Mario»')
    assert names == ['Zelda', 'Mario']


# ── _extract_legacy_names ─────────────────────────────────────────────────────

@pytest.mark.parametrize('title,expected', [
    ('Silence, on joue ! Gears of War 3, Resistance 3',
     ['Gears of War 3', 'Resistance 3']),
    ('Silence, on joue ! Battlefield 3, Uncharted 3, Dark Souls',
     ['Battlefield 3', 'Uncharted 3', 'Dark Souls']),
    ('Silence on joue ! World of Warcraft, Donkey Kong Country et Splatterhouse',
     ['World of Warcraft', 'Donkey Kong Country', 'Splatterhouse']),
    ('Silence on joue! Kinect, Fable III et James Bond',
     ['Kinect', 'Fable III', 'James Bond']),
    ('Silence on joue ! Skyrim, Shinobi',
     ['Skyrim', 'Shinobi']),
    ('Silence on joue! Batman Arkham City',
     ['Batman Arkham City']),
    ('Silence, on joue: Dreamcast, Gears of War 2...',
     ['Dreamcast', 'Gears of War 2']),
    ('La semaine des jeux vidéo ! The Legend of Zelda : Phantom Hourglass, PES 2008',
     ['The Legend of Zelda : Phantom Hourglass', 'PES 2008']),
])
def test_extract_legacy_names(title, expected):
    assert _extract_legacy_names(title) == expected

@pytest.mark.parametrize('title', [
    'Silence on joue! Spécial E3 2011',
    'Silence on joue ! Grand entretien avec Juliette',
    'Silence on joue ! Le bilan 2021',
    'Silence on joue ! En public à Muséogames',
    'Not a SOJ title at all',
])
def test_extract_legacy_names_skipped(title):
    assert _extract_legacy_names(title) == []

# ── _extract_fdg_names (Fin du Game title format) ─────────────────────────────

@pytest.mark.parametrize('title,expected', [
    ('Episode 167 - Ghost of Tsushima (feat. Julie le Baron)', ['Ghost of Tsushima']),
    ('Episode 163 - Tony Hawk\'s Underground 2',                ['Tony Hawk\'s Underground 2']),
    ('Episode 166 - Castlevania: Symphony of the Night (feat. Théo Arbogast)',
     ['Castlevania: Symphony of the Night']),                       # colon inside name kept
    ('Episode 89 : StarCraft II',                              ['StarCraft II']),  # colon separator
    ('Episode 22 - Resident Evil 2 (Remake)',                 ['Resident Evil 2 (Remake)']),  # non-feat paren kept
    ('Episode 142 - Les Sims (Feat. Héloïse Linossier & Margorito)', ['Les Sims']),  # capital Feat + &
    ('Episode 01 - Celeste',                                  ['Celeste']),  # zero-padded number
])
def test_extract_fdg_names(title, expected):
    assert _extract_fdg_names(title) == expected


@pytest.mark.parametrize('title', [
    'L\'avenir de Fin du Game',
    'Annonce Saison Six de Fin du Game',
    'Episode Bonus - Lancement du Patreon',   # non-numbered bonus → excluded
    '',
])
def test_extract_fdg_names_non_game(title):
    assert _extract_fdg_names(title) == []


def test_extract_game_names_falls_back_to_legacy():
    names = _extract_game_names('Silence, on joue ! Gears of War 3, Resistance 3')
    assert names == ['Gears of War 3', 'Resistance 3']

def test_extract_game_names_guillemets_take_priority():
    names = _extract_game_names('Silence on joue ! «Skyrim», «Doom» et «L.A. Noire» débarquent sur la Switch')
    assert names == ['Skyrim', 'Doom', 'L.A. Noire']


# ── _parse_feed ───────────────────────────────────────────────────────────────

def test_parse_feed_returns_game_list():
    episodes = _parse_feed(MINIMAL_RSS)
    names = {g.name for ep in episodes for g in ep.games}
    assert 'Zelda' in names
    assert 'Mario Kart' in names

def test_parse_feed_includes_non_game_episodes():
    episodes = _parse_feed(MINIMAL_RSS)
    assert len(episodes) == 2
    game_ep = next(ep for ep in episodes if ep.games)
    assert len(game_ep.games) == 2
    no_game_ep = next(ep for ep in episodes if not ep.games)
    assert no_game_ep.title == 'Quelle est la meilleure plateforme ?'

def test_parse_feed_uses_raw_podcast_name():
    # parse_feed no longer applies corrections — canonical name comes from IGDB
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
      <item>
        <title>On a joue \xc2\xab artic eggs \xc2\xbb</title>
        <enclosure url="https://example.com/ep3.mp3" type="audio/mpeg" length="0" />
        <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate><description></description>
      </item></channel></rss>"""
    rss = rss.replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    episodes = _parse_feed(rss)
    assert episodes[0].games[0].name.strip() == 'artic eggs'

def test_parse_feed_sets_audio_url():
    episodes = _parse_feed(MINIMAL_RSS)
    assert episodes[0].audio_url == 'https://example.com/ep1.mp3'

def test_parse_feed_parses_pub_ts():
    episodes = _parse_feed(MINIMAL_RSS)
    assert isinstance(episodes[0].pub_ts, int)
    assert episodes[0].pub_ts > 0

def test_parse_feed_resolves_timestamps():
    episodes = _parse_feed(MINIMAL_RSS)
    zelda = next(g for g in episodes[0].games if g.name == 'Zelda')
    assert zelda.timestamp == '00:30'
    assert zelda.timestamp_seconds == 30


# ── HTML sanitisation ──────────────────────────────────────────────────────────

def test_sanitize_html_drops_script_and_event_handlers():
    dirty = '<p>Hi</p><script>alert(1)</script><img src=x onerror="alert(2)">'
    clean = _sanitize_html(dirty)
    assert '<script' not in clean
    assert 'onerror' not in clean
    assert 'alert' not in clean          # script body dropped entirely
    assert '<p>Hi</p>' in clean

def test_sanitize_html_keeps_whitelisted_formatting():
    clean = _sanitize_html('<p>a <strong>b</strong> <em>c</em></p><ul><li>x</li></ul>')
    assert clean == '<p>a <strong>b</strong> <em>c</em></p><ul><li>x</li></ul>'

def test_sanitize_html_neutralises_javascript_urls():
    clean = _sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert 'javascript:' not in clean
    assert '>x</a>' in clean

def test_sanitize_html_keeps_safe_links():
    clean = _sanitize_html('<a href="https://example.com">link</a>')
    assert 'href="https://example.com"' in clean

def test_parse_feed_sanitizes_description():
    rss = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
  <item>
    <title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <enclosure url="https://example.com/ep.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
    <content:encoded><![CDATA[<p>Bonjour</p><script>alert(1)</script>]]></content:encoded>
  </item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    episodes = _parse_feed(rss)
    assert '<script' not in (episodes[0].description or '')
    assert '<p>Bonjour</p>' in episodes[0].description


# ── Episode identity (guid) + L2 collision ──────────────────────────────────────

def test_parse_feed_uses_guid_as_slug():
    episodes = _parse_feed(MINIMAL_RSS)
    assert episodes[0].slug == 'ep1guid'
    assert episodes[1].slug == 'ep2guid'

def test_parse_feed_guid_fallback_to_enclosure():
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>No Guid Here</title>
    <enclosure url="https://example.com/x.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description></description></item>
</channel></rss>"""
    ep = _parse_feed(rss)[0]
    assert ep.slug == games_module.make_slug('https://example.com/x.mp3')

def test_same_day_episodes_both_kept():
    # Two DISTINCT episodes, same calendar day, both mention «Zelda», different guids.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Matin on a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>day-a</guid><enclosure url="https://example.com/a.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
  <item><title>Soir on rejoue a \xc2\xabZelda\xc2\xbb</title>
    <guid>day-b</guid><enclosure url="https://example.com/b.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 20:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    _, game_index = games_module._build_indexes(_parse_feed(rss))
    zelda = game_index[games_module.make_slug('Zelda')]
    assert zelda.episode_count == 2
    assert {a.episode.slug for a in zelda.appearances} == {'day-a', 'day-b'}

def test_multi_feed_merges_same_game_across_podcasts():
    # A game covered by BOTH podcasts merges into one PodcastGame with two
    # appearances tagged with their distinct podcast_ids; url_slugs stay unique.
    soj_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>soj-zelda</guid><enclosure url="https://example.com/soj.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    fdg_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Episode 50 - Zelda</title>
    <guid>fdg-zelda</guid><enclosure url="https://example.com/fdg.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 10 Jan 2025 09:00:00 +0000</pubDate><description>Analyse complete</description></item>
</channel></rss>"""
    soj = PODCAST_BY_ID['silence-on-joue']
    fdg = PODCAST_BY_ID['fin-du-game']
    episodes = (
        _parse_feed(soj_rss, extractor=soj.extractor, podcast_id=soj.id)
        + _parse_feed(fdg_rss, extractor=fdg.extractor, podcast_id=fdg.id)
    )
    _assign_url_slugs(episodes)
    assert len({ep.url_slug for ep in episodes}) == len(episodes)  # globally unique

    _, game_index = games_module._build_indexes(episodes)
    zelda = game_index[games_module.make_slug('Zelda')]
    assert zelda.episode_count == 2
    assert {a.episode.podcast_id for a in zelda.appearances} == {'silence-on-joue', 'fin-du-game'}


def test_multi_feed_episodes_interleave_by_date():
    # The combined feed must be newest-first across BOTH podcasts, so a recent FDG
    # episode sorts above older SOJ episodes instead of all SOJ coming first.
    soj_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Vieux \xc2\xabZelda\xc2\xbb</title>
    <guid>soj-old</guid><enclosure url="https://example.com/o.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>x</description></item>
  <item><title>Recent \xc2\xabMario\xc2\xbb</title>
    <guid>soj-new</guid><enclosure url="https://example.com/n.mp3" type="audio/mpeg" length="0" />
    <pubDate>Wed, 01 Jan 2025 09:00:00 +0000</pubDate><description>x</description></item>
</channel></rss>"""
    fdg_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Episode 50 - Balatro</title>
    <guid>fdg-mid</guid><enclosure url="https://example.com/m.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 10 May 2024 09:00:00 +0000</pubDate><description>x</description></item>
</channel></rss>"""
    soj = PODCAST_BY_ID['silence-on-joue']
    fdg = PODCAST_BY_ID['fin-du-game']
    episodes = (
        _parse_feed(soj_rss, extractor=soj.extractor, podcast_id=soj.id)
        + _parse_feed(fdg_rss, extractor=fdg.extractor, podcast_id=fdg.id)
    )
    episodes.sort(key=lambda e: e.pub_ts or 0, reverse=True)
    order = [e.slug for e in episodes]
    assert order == ['soj-new', 'fdg-mid', 'soj-old']     # interleaved, newest-first
    pts = [e.pub_ts or 0 for e in episodes]
    assert pts == sorted(pts, reverse=True)


def test_intra_episode_duplicate_deduped():
    # Same game mentioned twice in ONE episode → a single appearance.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Special \xc2\xabZelda\xc2\xbb et encore \xc2\xabZelda\xc2\xbb</title>
    <guid>solo</guid><enclosure url="https://example.com/s.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    _, game_index = games_module._build_indexes(_parse_feed(rss))
    zelda = game_index[games_module.make_slug('Zelda')]
    assert len(zelda.appearances) == 1


# ── AI chapter injection (L2 gotcha + L5 guard) ────────────────────────────────

def _blank_episode(title, slug):
    from models import Episode
    return Episode(title=title, slug=slug, audio_url=None, pub_ts=None,
                   image_url=None, description=None, chapters=[], games=[])

def test_inject_ai_chapters_matches_on_title_slug():
    # episode.slug is now a guid; injection must still match on make_slug(title).
    ep = _blank_episode('My Episode', 'guid-xyz')
    ai_index = {games_module.make_slug('My Episode'): [
        {'start_s': 30, 'title': 'Intro'}, {'start_s': 90, 'title': 'Zelda'},
    ]}
    games_module._inject_ai_chapters([ep], ai_index)
    assert [c.title for c in ep.chapters] == ['Intro', 'Zelda']

def test_inject_ai_chapters_skips_malformed_entries():
    ep = _blank_episode('Bad Ep', 'g')
    ai_index = {games_module.make_slug('Bad Ep'): [
        {'title': 'no start'},                # missing start_s → skipped
        {'start_s': 10},                       # missing title  → skipped
        {'start_s': 20, 'title': 'Good'},      # kept
    ]}
    games_module._inject_ai_chapters([ep], ai_index)
    assert [c.title for c in ep.chapters] == ['Good']


# ── Catalog episodeCount (L4) ───────────────────────────────────────────────────

def test_catalog_counts_distinct_episodes():
    # Two name variants resolving to ONE igdb_slug, co-occurring in ONE episode,
    # must count that episode once (not twice).
    from models import IgdbEntry
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb et \xc2\xabZelda BOTW\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/e.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    episodes = _parse_feed(rss)
    episode_index, game_index = games_module._build_indexes(episodes)
    games_module._cached_episodes = episodes
    games_module._episode_index   = episode_index
    games_module._game_index      = game_index
    now = '2999-01-01T00:00:00'
    games_module._igdb_cache = {
        f"{games_module.make_slug('Zelda')}-g1":
            IgdbEntry('z-g1', 1, 'zelda-botw', 'Zelda BOTW', {'metacritic': 97}, False, now),
        f"{games_module.make_slug('Zelda BOTW')}-g1":
            IgdbEntry('zb-g1', 1, 'zelda-botw', 'Zelda BOTW', {'metacritic': 97}, False, now),
    }
    catalog = games_module._build_catalog()
    entry = next(g for g in catalog if g['slug'] == 'zelda-botw')
    assert entry['episodeCount'] == 1


def test_count_pending_respects_ttl():
    """TTL-expired-but-cached appearances are counted as pending (so the catalog
    gate, SSE endpoint, and periodic retry agree on what needs resolving); freshly
    cached ones are not. Guards the resolver-trigger unification + datetime compare."""
    from models import IgdbEntry
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/e.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    episodes = _parse_feed(rss)
    _, game_index = games_module._build_indexes(episodes)
    games_module._game_index = game_index
    slugs = [a.podcast_slug for g in game_index.values() for a in g.appearances]
    assert slugs

    def cache_with(cached_at):
        return {s: IgdbEntry(s, 1, 'zelda', 'Zelda', {'metacritic': 90}, False, cached_at) for s in slugs}

    def recount():
        games_module._pending_cache = None      # bust the per-minute memo
        games_module._data_version += 1
        return games_module._count_pending()

    games_module._igdb_cache = cache_with(games_module.utcnow().isoformat())
    assert recount() == 0                         # fresh → nothing pending

    games_module._igdb_cache = cache_with('2000-01-01T00:00:00')
    assert recount() == len(slugs)                # TTL-expired → all pending


# ── GET /games ────────────────────────────────────────────────────────────────

def test_no_auth_returns_401(client):
    r = client.get('/silence/games')
    assert_contract(r, GAMES['catalog']['unauthorized'])


def test_catalog_returns_list(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        r = client.get('/silence/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])
    data = r.get_json()
    assert isinstance(data['games'], list)
    assert any(g['name'] == 'Zelda' for g in data['games'])


def test_catalog_response_has_igdb_field(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        r = client.get('/silence/games', headers=auth_header())
    data = r.get_json()
    assert all('igdb' in g for g in data['games'])


def test_cache_hit_skips_fetch(client):
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
        client.get('/silence/games', headers=auth_header())
    mock_get.assert_called_once()


def test_expired_cache_refetches(client):
    games_module._cached_at = (datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                               - datetime.timedelta(hours=9))
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('games._schedule_resolve'):
        r = client.get('/silence/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])
    mock_get.assert_called_once()


def test_catalog_deduplicates_by_igdb_slug(client):
    rss_two_names = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>z1</guid>
    <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
    <description>00:30 Zelda</description>
  </item>
  <item>
    <title>On a joue a \xc2\xabZelda BotW\xc2\xbb</title>
    <guid>z2</guid>
    <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate>
    <description>00:30 Zelda BotW</description>
  </item>
</channel></rss>"""
    rss_two_names = rss_two_names.replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())

    from models import IgdbEntry
    igdb_cache = {
        'zelda-z1':      IgdbEntry('zelda-z1',      1, 'zelda', 'Zelda', None, False, '2099-01-01'),
        'zelda-botw-z2': IgdbEntry('zelda-botw-z2', 1, 'zelda', 'Zelda', None, False, '2099-01-01'),
    }
    with patch('games.http.get', return_value=mock_rss_response(rss_two_names)), \
         patch('games._schedule_resolve'), \
         patch.object(games_module, '_igdb_cache', igdb_cache):
        r = client.get('/silence/games', headers=auth_header())

    data = r.get_json()['games']
    zelda_entries = [g for g in data if g['slug'] == 'zelda']
    assert len(zelda_entries) == 1
    assert zelda_entries[0]['episodeCount'] == 2


def test_catalog_serves_cache_on_refresh_parse_error(client):
    # warm the in-memory catalog
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
    # force staleness so the next request attempts a refresh
    games_module._cached_at = (datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                               - datetime.timedelta(hours=9))
    # a malformed feed (non-RequestException) must NOT 500 when we already have data
    with patch('games._refresh_feed', side_effect=ValueError('malformed XML')):
        r = client.get('/silence/games', headers=auth_header())
    assert r.status_code == 200
    assert any(g['name'] == 'Zelda' for g in r.get_json()['games'])


def test_catalog_returns_304_on_matching_etag(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        r1 = client.get('/silence/games', headers=auth_header())
    etag = r1.headers.get('ETag')
    assert etag
    # second load with the same ETag and an unchanged catalog → 304, no re-transfer
    r2 = client.get('/silence/games', headers={**auth_header(), 'If-None-Match': etag})
    assert r2.status_code == 304
    assert r2.get_data() == b''


def test_catalog_igdb_is_slim(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        r = client.get('/silence/games', headers=auth_header())
    data = r.get_json()['games']
    for game in data:
        if game['igdb'] is not None:
            assert set(game['igdb'].keys()) == {'metacritic', 'coverImageId'}


# ── GET /games/<slug> ─────────────────────────────────────────────────────────

def test_game_detail_returns_episodes(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
    r = client.get('/silence/games/Zelda', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)
    assert len(data['episodes']) > 0
    assert data['episodes'][0]['audioUrl'] == 'https://example.com/ep1.mp3'


# ── POST /games/refresh ───────────────────────────────────────────────────────

def test_refresh_always_fetches(client):
    with patch('games.http.get', return_value=mock_rss_response()) as mock_get:
        r = client.post('/silence/games/refresh', headers=auth_header())
    assert_contract(r, GAMES['refresh']['success'])
    mock_get.assert_called_once()


# ── POST /games/<slug>/igdb-refresh ──────────────────────────────────────────

def test_igdb_refresh_returns_game_detail(client):
    episodes = _parse_feed(MINIMAL_RSS)
    episode_index, game_index = games_module._build_indexes(episodes)
    games_module._cached_episodes = episodes
    games_module._episode_index   = episode_index
    games_module._game_index      = game_index
    with patch('games._resolve_one'):
        r = client.post('/silence/games/Zelda/igdb-refresh', headers=auth_header())
    assert_contract(r, GAMES['igdb_refresh']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)


# ── GET /games/episodes ───────────────────────────────────────────────────────

_UNIFIED_EPISODE_KEYS = ('title', 'slug', 'urlSlug', 'audioUrl', 'pubTs', 'imageUrl',
                         'description', 'chapters', 'games', 'podcast', 'timestamp', 'timestampSeconds')

# The feed *list* is a slim shape: `description` and `chapters` are omitted (they're
# served by the single-episode detail) to keep the payload small.
_SLIM_EPISODE_KEYS = tuple(k for k in _UNIFIED_EPISODE_KEYS if k not in ('description', 'chapters'))

def test_episodes_returns_list_with_slim_shape(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
    r = client.get('/silence/games/episodes', headers=auth_header())
    assert_contract(r, GAMES['episodes']['success'])
    data = r.get_json()
    assert isinstance(data, list) and len(data) > 0
    for key in _SLIM_EPISODE_KEYS:
        assert key in data[0], f"missing '{key}' in feed episode"
    # Heavy fields must NOT be in the list payload — they belong to the detail endpoint.
    assert 'description' not in data[0]
    assert 'chapters'    not in data[0]


# ── GET /games/episode ────────────────────────────────────────────────────────

def test_episode_detail_returns_unified_shape(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
    slug = client.get('/silence/games/episodes', headers=auth_header()).get_json()[0]['slug']
    r = client.get(f'/silence/games/episode?slug={slug}', headers=auth_header())
    assert_contract(r, GAMES['episode']['success'])
    # The single-episode endpoint keeps the FULL shape (incl. description + chapters).
    body = r.get_json()
    for key in _UNIFIED_EPISODE_KEYS:
        assert key in body, f"missing '{key}' in episode detail"

def test_episode_missing_slug_returns_400(client):
    r = client.get('/silence/games/episode', headers=auth_header())
    assert_contract(r, GAMES['episode']['bad_request'])

def test_episode_unknown_slug_returns_404(client):
    with patch('games.http.get', return_value=mock_rss_response()), \
         patch('games._schedule_resolve'):
        client.get('/silence/games', headers=auth_header())
    r = client.get('/silence/games/episode?slug=does-not-exist', headers=auth_header())
    assert_contract(r, GAMES['episode']['not_found'])
