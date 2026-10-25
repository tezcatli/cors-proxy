import datetime
from dataclasses import replace
from unittest.mock import patch, MagicMock

import pytest

import catalog_state as state
import feeds
import games as games_module
import resolver
import serializers
from db import get_db, utcnow
from utils import make_slug
from contract import assert_contract, CONTRACT
from conftest import auth_header, cache_entry, set_cache
import db as _db
from rss import extract_game_names as _extract_game_names, extract_legacy_names as _extract_legacy_names, extract_fdg_names as _extract_fdg_names, parse_feed as _parse_feed, assign_url_slugs as _assign_url_slugs, sanitize_html as _sanitize_html
from podcasts import PODCAST_BY_ID
from questions import question_for

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

def test_a_feed_item_becomes_an_episode():
    episodes = _parse_feed(MINIMAL_RSS)
    assert len(episodes) == 2                                  # one without a game too
    ep, other = episodes
    assert (ep.slug, ep.audio_url, other.slug) == ('ep1guid', 'https://example.com/ep1.mp3', 'ep2guid')
    assert ep.pub_ts == 1_705_276_800                          # Mon, 15 Jan 2024 00:00 UTC
    assert [(g.name, g.timestamp, g.timestamp_seconds) for g in ep.games] == [
        ('Zelda', '00:30', 30), ('Mario Kart', '01:00', 60)]
    assert (other.title, other.games) == ('Quelle est la meilleure plateforme ?', [])


# ── HTML sanitisation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize('dirty, clean', [
    ('<p>Hi</p><script>alert(1)</script><img src=x onerror="alert(2)">', '<p>Hi</p>'),  # script body dropped
    ('<p>a <strong>b</strong> <em>c</em></p><ul><li>x</li></ul>',
     '<p>a <strong>b</strong> <em>c</em></p><ul><li>x</li></ul>'),                         # formatting kept
    ('<a href="javascript:alert(1)">x</a>', '<a>x</a>'),
    ('<a href="https://example.com">link</a>',
     '<a href="https://example.com" rel="noopener noreferrer" target="_blank">link</a>'),
])
def test_sanitize_html_keeps_formatting_and_safe_links_only(dirty, clean):
    assert _sanitize_html(dirty) == clean


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

def test_parse_feed_guid_fallback_to_enclosure():
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>No Guid Here</title>
    <enclosure url="https://example.com/x.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description></description></item>
</channel></rss>"""
    ep = _parse_feed(rss)[0]
    assert ep.slug == make_slug('https://example.com/x.mp3')

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
    _, game_index = feeds.build_indexes(_parse_feed(rss))
    zelda = game_index[make_slug('Zelda')]
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

    _, game_index = feeds.build_indexes(episodes)
    zelda = game_index[make_slug('Zelda')]
    assert len(zelda.appearances) == 2
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
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    fdg_rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Episode 50 - Balatro</title>
    <guid>fdg-mid</guid><enclosure url="https://example.com/m.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 10 May 2024 09:00:00 +0000</pubDate><description>x</description></item>
</channel></rss>"""
    soj, fdg = PODCAST_BY_ID['silence-on-joue'], PODCAST_BY_ID['fin-du-game']
    feeds_by_url = {soj.feed_url: soj_rss, fdg.feed_url: fdg_rss}
    with patch.object(feeds, 'PODCASTS', [soj, fdg]), \
         patch('feeds.http.get', side_effect=lambda url, **_: mock_rss_response(feeds_by_url[url])):
        feeds.refresh_feed()
    assert [e.slug for e in state.episodes] == ['soj-new', 'fdg-mid', 'soj-old']


def test_intra_episode_duplicate_deduped():
    # Same game mentioned twice in ONE episode → a single appearance.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Special \xc2\xabZelda\xc2\xbb et encore \xc2\xabZelda\xc2\xbb</title>
    <guid>solo</guid><enclosure url="https://example.com/s.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 09:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    _, game_index = feeds.build_indexes(_parse_feed(rss))
    zelda = game_index[make_slug('Zelda')]
    assert len(zelda.appearances) == 1


# ── Catalog episodeCount (L4) ───────────────────────────────────────────────────

def test_count_pending_respects_ttl():
    """TTL-expired-but-cached appearances are counted as pending; freshly cached
    ones are not. Guards the datetime compare."""
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/e.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>"""
    episodes = _parse_feed(rss)
    _, game_index = feeds.build_indexes(episodes)
    state.game_index = game_index
    slugs = [a.podcast_slug for g in game_index.values() for a in g.appearances]
    assert slugs

    def cache_with(cached_at):
        return {s: cache_entry(s, 1, 'zelda', 'Zelda', {'metacritic': 90}, False, cached_at) for s in slugs}

    set_cache(cache_with(utcnow().isoformat()))
    assert resolver.count_pending() == 0                # fresh → nothing pending

    set_cache(cache_with('2000-01-01T00:00:00'))
    assert resolver.count_pending() == len(slugs)       # TTL-expired → all pending


# ── GET /games ────────────────────────────────────────────────────────────────

def test_no_auth_returns_401(client):
    r = client.get('/games')
    assert_contract(r, GAMES['catalog']['unauthorized'])


def test_catalog_returns_list(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        r = client.get('/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])
    data = r.get_json()
    assert isinstance(data['games'], list)
    assert any(g['name'] == 'Zelda' for g in data['games'])


def test_catalog_response_has_igdb_field(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        r = client.get('/games', headers=auth_header())
    data = r.get_json()
    assert all('igdb' in g for g in data['games'])


def test_refresh_serves_cache_on_parse_error(client):
    # warm the in-memory catalog
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    # a malformed feed (non-RequestException) must NOT 500 when we already have data
    with patch('feeds.refresh_feed', side_effect=ValueError('malformed XML')), \
         patch('resolver.quick_pass'), patch('resolver.schedule_resolve'):
        r = client.post('/games/refresh', headers=auth_header())
    assert r.status_code == 200
    assert any(g['name'] == 'Zelda' for g in r.get_json()['games'])


def test_catalog_returns_304_on_matching_etag(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        r1 = client.get('/games', headers=auth_header())
    etag = r1.headers.get('ETag')
    assert etag
    # second load with the same ETag and an unchanged catalog → 304, no re-transfer
    r2 = client.get('/games', headers={**auth_header(), 'If-None-Match': etag})
    assert r2.status_code == 304
    assert r2.get_data() == b''


@pytest.mark.parametrize('url', ['/games', '/games/episodes'])
def test_revalidation_accepts_the_weak_etag_gzip_leaves(client, url):
    # The edge gzips these responses, which turns the ETag weak: the browser then
    # revalidates with W/"…" and must still get a 304, not the full body again.
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    etag = client.get(url, headers=auth_header()).headers['ETag']
    r = client.get(url, headers={**auth_header(), 'If-None-Match': f'W/{etag}'})
    assert r.status_code == 304


def test_catalog_igdb_is_slim(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        r = client.get('/games', headers=auth_header())
    data = r.get_json()['games']
    for game in data:
        if game['igdb'] is not None:
            assert set(game['igdb'].keys()) == {'metacritic', 'coverImageId'}


# ── GET /games/<slug> ─────────────────────────────────────────────────────────

def test_game_detail_returns_episodes(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/Zelda', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['success'])
    data = r.get_json()
    assert data['name'] == 'Zelda'
    assert isinstance(data['episodes'], list)
    assert len(data['episodes']) > 0
    assert data['episodes'][0]['audioUrl'] == 'https://example.com/ep1.mp3'


def test_game_detail_surfaces_display_name_and_igdb_name(client, tmp_corrections):
    # displayName pre-fills the picker's « Nom affiché »; igdbName is the true
    # resolution behind the entry (top-level `name` is already the override).
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2', 'Silent Hill 2'),
    })
    corrections.upsert('Silent Hill 2', display_name='Silent Hill 2 (2001)')
    r = client.get('/games/silent-hill-2', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['success'])
    data = r.get_json()
    assert data['name']        == 'Silent Hill 2 (2001)'
    assert data['displayName'] == 'Silent Hill 2 (2001)'
    assert data['igdbName']    == 'Silent Hill 2'


# ── POST /games/refresh ───────────────────────────────────────────────────────

def test_refresh_always_fetches(client):
    with patch('feeds.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('resolver.quick_pass'), patch('resolver.schedule_resolve'):
        r = client.post('/games/refresh', headers=auth_header())
    assert_contract(r, GAMES['refresh']['success'])
    mock_get.assert_called_once()


def test_catalog_does_not_refetch_once_loaded(client):
    # The background tick owns feed freshness; a read never triggers a fetch
    # beyond the cold-start one, however old the catalog is.
    with patch('feeds.http.get', return_value=mock_rss_response()) as mock_get, \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
        state.cached_at = datetime.datetime(2000, 1, 1)
        client.get('/games', headers=auth_header())
    mock_get.assert_called_once()


def test_unchanged_feed_keeps_the_data_version(client):
    # Polled every tick and nearly always 304: rebuilding would bump the version
    # and invalidate every client's catalog ETag for nothing.
    with patch('feeds.http.get', return_value=mock_rss_response()):
        feeds.refresh_feed()
    version = state.data_version
    with patch('feeds.http.get', return_value=mock_rss_response(status=304)):
        feeds.refresh_feed()
    assert state.data_version == version


def _ask(name, pub_ts=None, podcast_id='silence-on-joue'):
    """The question `name`, heard in a `podcast_id` episode published at `pub_ts`, asks."""
    from models import Episode, PodcastGame
    from questions import question_for
    episode = Episode(title='t', slug='g', audio_url=None, pub_ts=pub_ts, image_url=None,
                      description=None, chapters=[], games=[], podcast_id=podcast_id)
    return question_for(PodcastGame(make_slug(name), name), episode)


def _igdb_hit(name):
    from igdb import IgdbResult
    return IgdbResult(id=7, name=name, slug=make_slug(name),
                      data={'coverImageId': 'abc'}, is_child=False)


def test_refresh_resolves_new_games_without_the_scrapers(client):
    # Someone pulling to refresh after an episode came out should get the new
    # games' names and covers in that response; the slow scrapers wait.
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.fetch_by_name', side_effect=lambda n, ts: _igdb_hit(n)), \
         patch('resolver.metacritic.fetch_metascore') as mc, \
         patch('resolver.hltb.fetch_time_to_beat') as hl, \
         patch('resolver.schedule_resolve'):
        r = client.post('/games/refresh', headers=auth_header())
    mc.assert_not_called()
    hl.assert_not_called()
    zelda = next(g for g in r.get_json()['games'] if g['name'] == 'Zelda')
    assert zelda['igdb'] == {'metacritic': None, 'coverImageId': 'abc'}
    # Not enriched yet → still pending, so the background sweep finishes the job.
    assert all(not g.enriched for g in state.games.values())
    assert resolver.count_pending() == len(state.resolutions)


def test_refresh_leaves_new_games_to_the_sweep_once_the_budget_is_spent(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.fetch_by_name') as by_name, \
         patch('resolver.schedule_resolve') as sweep, \
         patch('resolver.REFRESH_BUDGET_S', 0):
        client.post('/games/refresh', headers=auth_header())
    by_name.assert_not_called()
    sweep.assert_called_once_with()


def test_unenriched_flag_survives_a_restart():
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Zelda')):
        resolver.resolve(_ask('Zelda'), enrich=False)
    state.load_igdb_cache_from_db()
    assert state.games[7].enriched is False


# ── POST /games/<slug>/igdb-refresh ──────────────────────────────────────────

def test_igdb_refresh_returns_game_detail(client):
    episodes = _parse_feed(MINIMAL_RSS)
    episode_index, game_index = feeds.build_indexes(episodes)
    state.episodes = episodes
    state.episode_index   = episode_index
    state.game_index      = game_index
    with patch('resolver.resolve'):
        r = client.post('/games/Zelda/igdb-refresh', headers=auth_header())
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
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/episodes', headers=auth_header())
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
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    slug = client.get('/games/episodes', headers=auth_header()).get_json()[0]['slug']
    r = client.get(f'/games/episode?slug={slug}', headers=auth_header())
    assert_contract(r, GAMES['episode']['success'])
    # The single-episode endpoint keeps the FULL shape (incl. description + chapters).
    body = r.get_json()
    for key in _UNIFIED_EPISODE_KEYS:
        assert key in body, f"missing '{key}' in episode detail"

def test_episode_missing_slug_returns_400(client):
    r = client.get('/games/episode', headers=auth_header())
    assert_contract(r, GAMES['episode']['bad_request'])

def test_episode_unknown_slug_returns_404(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/episode?slug=does-not-exist', headers=auth_header())
    assert_contract(r, GAMES['episode']['not_found'])


# ── Per-appearance catalog grouping ───────────────────────────────────────────

def _seed(rss, cache, podcast_id='silence-on-joue'):
    """Parse an RSS blob into the module's in-memory state with a given IGDB cache."""
    podcast  = PODCAST_BY_ID[podcast_id]
    episodes = _parse_feed(rss, extractor=podcast.extractor, podcast_id=podcast.id)
    _assign_url_slugs(episodes)
    episode_index, game_index = feeds.build_indexes(episodes)
    state.episodes = episodes
    state.episode_index   = episode_index
    state.game_index      = game_index
    set_cache(cache)
    state.data_version   += 1
    games_module._catalog_cache   = None
    return episodes


_NOW = '2999-01-01T00:00:00'


def _entry(podcast_slug, igdb_id, igdb_slug, name, **data):
    return cache_entry(podcast_slug, igdb_id, igdb_slug, name, dict(data), False, _NOW)


_TWO_EPISODES_SAME_NAME = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabSilent Hill 2\xc2\xbb</title>
    <guid>remake</guid><enclosure url="https://example.com/a.mp3" type="audio/mpeg" length="0" />
    <pubDate>Tue, 15 Oct 2024 00:00:00 +0000</pubDate><description>00:30 Silent Hill 2</description></item>
  <item><title>On a joue a \xc2\xabSilent Hill 2\xc2\xbb</title>
    <guid>original</guid><enclosure url="https://example.com/b.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2001 00:00:00 +0000</pubDate><description>00:30 Silent Hill 2</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())


def test_same_name_resolving_to_two_games_splits_into_two_entries():
    # One podcast name covering two distinct IGDB games (the 2001 original and the
    # 2024 remake) must yield two catalog entries — not one absorbing the other.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake':   _entry(f'{ns}-remake',   2, 'silent-hill-2--1', 'Silent Hill 2', released='2024'),
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2',    'Silent Hill 2', released='2001'),
    })
    catalog = serializers.build_catalog()
    slugs   = {g['slug'] for g in catalog}
    assert {'silent-hill-2', 'silent-hill-2--1'} <= slugs

    # …and each detail page lists only its own episode.
    original = serializers.load_game('silent-hill-2')
    remake   = serializers.load_game('silent-hill-2--1')
    assert [e['slug'] for e in original['episodes']] == ['original']
    assert [e['slug'] for e in remake['episodes']]   == ['remake']
    assert original['igdb']['released'] == '2001'
    assert remake['igdb']['released']   == '2024'


def test_names_on_one_game_are_one_entry_counted_by_episode():
    # Two spellings landing on one igdb_slug are one entry, even both in one
    # episode, which counts once.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
  <item><title>On a joue a \xc2\xabZelda BOTW\xc2\xbb</title>
    <guid>g2</guid><enclosure url="https://example.com/2.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 22 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda BOTW</description></item>
  <item><title>On a joue a \xc2\xabZelda\xc2\xbb et \xc2\xabZelda BOTW\xc2\xbb</title>
    <guid>g3</guid><enclosure url="https://example.com/3.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 29 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    zelda, botw = make_slug('Zelda'), make_slug('Zelda BOTW')
    _seed(rss, {f'{name}-{guid}': _entry(guid, 1, 'zelda-botw', 'Zelda BOTW')
                for name, guid in ((zelda, 'g1'), (botw, 'g2'), (zelda, 'g3'), (botw, 'g3'))})
    catalog = [g for g in serializers.build_catalog() if g['slug'] == 'zelda-botw']
    assert len(catalog) == 1
    assert catalog[0]['episodeCount'] == 3


def test_unresolved_appearances_group_under_name_slug():
    ns = make_slug('Silent Hill 2')
    # Only the remake episode is resolved; the other is still pending.
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 2, 'silent-hill-2--1', 'Silent Hill 2', released='2024'),
    })
    catalog = {g['slug']: g for g in serializers.build_catalog()}
    assert catalog[ns]['igdb'] is None                       # unresolved bucket
    assert catalog['silent-hill-2--1']['igdb'] is not None
    # The name_slug entry carries only the unresolved appearance.
    assert [e['slug'] for e in serializers.load_game(ns)['episodes']] == ['original']


def test_name_slug_that_is_also_an_igdb_slug_serves_the_resolved_group():
    # make_slug('Silent Hill 2') == the original's igdb_slug. The resolved group
    # must win, so /game/silent-hill-2 is the 2001 game, not a mixed bag.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake':   _entry(f'{ns}-remake',   2, 'silent-hill-2--1', 'Silent Hill 2', released='2024'),
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2',    'Silent Hill 2', released='2001'),
    })
    detail = serializers.load_game(ns)
    assert [e['slug'] for e in detail['episodes']] == ['original']
    assert detail['igdb']['released'] == '2001'


def test_detail_falls_back_to_all_appearances_for_a_fully_resolved_name_slug():
    # A stale /game/<name_slug> link, for a name that is NOT itself an igdb_slug
    # and whose appearances have all resolved, must still render rather than 404.
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabZelda BOTW\xc2\xbb</title>
    <guid>g1</guid><enclosure url="https://example.com/1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description>00:30 Zelda BOTW</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())
    ns = make_slug('Zelda BOTW')       # 'zelda-botw' ≠ igdb slug below
    _seed(rss, {f'{ns}-g1': _entry(f'{ns}-g1', 1, 'the-legend-of-zelda-breath-of-the-wild', 'Zelda')})
    detail = serializers.load_game(ns)
    assert len(detail['episodes']) == 1
    assert detail['igdb'] is None      # unresolved fallback shape


def test_detail_episodes_are_newest_first():
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})
    pts = [e['pubTs'] for e in serializers.load_game(ns)['episodes']]
    assert pts == sorted(pts, reverse=True)


def test_each_test_carries_its_verdict_and_the_catalog_one_per_test():
    # Two tests of one game, newest first: the detail gives each episode its
    # critique, the catalog one verdict per test with no average across them.
    ns = make_slug('Silent Hill 2')
    episodes = _seed(_TWO_EPISODES_SAME_NAME, {})
    opinion = {'verdict': 'positive', 'pros': ['Brume'], 'cons': [], 'at': 30}
    episodes[0].games[0].critique = opinion
    detail = serializers.load_game(ns)
    assert [e['critique'] for e in detail['episodes']] == [opinion, None]
    assert detail['episodes'][0]['games'][0]['critique'] == opinion
    entry = next(g for g in serializers.build_catalog() if g['slug'] == ns)
    assert entry['verdicts'] == ['positive', None]
    assert serializers.serialise_episode_slim(episodes[0])['games'][0]['verdict'] == 'positive'


def test_unknown_slug_still_404s(client):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.get('/games/no-such-game', headers=auth_header())
    assert_contract(r, GAMES['game_detail']['not_found'])


# ── Resolution: per-podcast date hint + corrections ───────────────────────────

_FDG_RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Episode 166 - Chrono Trigger</title>
    <guid>fdg1</guid><enclosure url="https://example.com/f.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 05 Jun 2026 00:00:00 +0000</pubDate><description>00:30 Chrono Trigger</description></item>
</channel></rss>"""

_SOJ_RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>On a joue a \xc2\xabChrono Trigger\xc2\xbb</title>
    <guid>soj1</guid><enclosure url="https://example.com/s.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 05 Jun 2026 00:00:00 +0000</pubDate><description>00:30 Chrono Trigger</description></item>
</channel></rss>""".replace(b'\xc2\xab', '«'.encode()).replace(b'\xc2\xbb', '»'.encode())


def test_a_pin_is_fetched_as_is_neither_searched_nor_judged(tmp_corrections, monkeypatch):
    from config import Config
    from igdb import IgdbResult
    import corrections
    monkeypatch.setattr(Config, 'OPENROUTER_API_KEY', 'test-key')     # the LLM is on…
    corrections.upsert('Chrono Trigger', igdb_id=4242)
    result = IgdbResult(id=4242, name='Chrono Trigger', slug='chrono-trigger',
                        data={'metacritic': 92}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=result) as by_id, \
         patch('resolver.fetch_by_name') as by_name, \
         patch('llm.http.post') as llm_post, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve(_ask('Chrono Trigger', podcast_id='fin-du-game'))
    by_name.assert_not_called()
    llm_post.assert_not_called()                                         # …and outranked
    # canonical=False: a human's pin must not be redirected to a parent game.
    assert by_id.call_args == ((4242,), {'canonical': False})
    answer = state.resolutions['pin|4242']
    assert (answer.igdb_id, answer.method, state.games[4242].igdb_slug) == (4242, 'pin', 'chrono-trigger')


# ── A shipped correction changes the question ────────────────────────────────

def _single_soj_game():
    """Build a one-game index from an SOJ episode; return (game, appearance)."""
    podcast  = PODCAST_BY_ID['silence-on-joue']
    episodes = _parse_feed(_SOJ_RSS, extractor=podcast.extractor, podcast_id=podcast.id)
    _, game_index = feeds.build_indexes(episodes)
    state.game_index = game_index
    game = next(iter(game_index.values()))
    return game, game.appearances[0]


def _fresh_entry(appearance):
    """A fresh answer for `appearance`'s question, on a fresh game."""
    return cache_entry(appearance.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger',
                       {'metacritic': 90}, False, utcnow().isoformat())


def test_a_shipped_correction_asks_a_new_question_and_its_removal_the_old_one(tmp_corrections):
    import corrections
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: _fresh_entry(appearance)})
    assert resolver.count_pending() == 0
    corrections.upsert('Chrono Trigger', igdb_id=4242)               # ship a pin
    assert question_for(game, appearance.episode).key == 'pin|4242'
    assert resolver.count_pending() == 1                             # unanswered
    set_cache({appearance.podcast_slug: _fresh_entry(appearance)})   # the sweep answers it
    corrections.remove('Chrono Trigger')                             # ship its removal
    assert question_for(game, appearance.episode).kind == 'name'
    assert resolver.count_pending() == 1


# ── Pruning ─────────────────────────────────────────────────────────────────

def test_prune_drops_unasked_questions_then_unused_games():
    from models import Resolution
    game, appearance = _single_soj_game()
    asked_key = question_for(game, appearance.episode).key
    for key, igdb_id in ((asked_key, 1), ('name|silence-on-joue|2020|gone', 2)):
        state.store_resolution(Resolution(key, igdb_id, False, _NOW))
    for igdb_id in (1, 2, 3):
        state.store_game(cache_entry('x', igdb_id, f'g{igdb_id}', f'G{igdb_id}').game)

    state.prune_igdb_cache()

    assert set(state.resolutions) == {asked_key}
    assert set(state.games) == {1}                   # 2 lost its last answer; 3 had none
    state.load_igdb_cache_from_db()                  # …and the DB agrees
    assert (set(state.resolutions), set(state.games)) == ({asked_key}, {1})


def test_prune_keeps_everything_when_the_feed_parsed_empty():
    # A transient empty parse must not wipe the cache.
    state.store_resolution(cache_entry('a', 1, 'a', 'A').resolution)
    state.store_game(cache_entry('a', 1, 'a', 'A').game)
    state.game_index = {}
    state.prune_igdb_cache()
    assert (set(state.resolutions), set(state.games)) == ({'a'}, {1})


# ── The sweep: questions, then each game's data ──────────────────────────────

_EXPIRED = '2000-01-01T00:00:00'


def _sweep(cached, by_id=None):
    """Run the background sweep over Chrono Trigger's appearance with `cached`
    (a function of the appearance) in the cache; returns the two IGDB mocks."""
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: cached(appearance)})
    with patch('resolver.fetch_by_id', return_value=by_id) as by_id_mock, \
         patch('resolver.fetch_by_name', return_value=_igdb_hit('Chrono Trigger')) as by_name, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.schedule_resolve()
    return by_id_mock, by_name, question_for(game, appearance.episode).key


def test_an_expired_game_is_renewed_by_id_not_searched_again(tmp_corrections):
    # Asking again could land on a same-name game IGDB added since, undoing an
    # answer that was right; the known id can't.
    from igdb import IgdbResult
    expired_child = lambda a: cache_entry(   # noqa: E731
        a.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger', {'metacritic': 90},
        is_child=True, at=_EXPIRED, method='search')
    by_id, by_name, key = _sweep(expired_child, IgdbResult(
        id=1, name='Chrono Trigger', slug='chrono-trigger', data={'metacritic': 93},
        is_child=False))
    by_id.assert_called_once_with(1, canonical=False)
    by_name.assert_not_called()
    assert state.games[1].data['metacritic'] == 93
    assert state.resolutions[key].is_child   # still ranks as the DLC/version it was resolved from


def test_a_game_igdb_dropped_is_asked_again(tmp_corrections):
    expired = lambda a: cache_entry(   # noqa: E731
        a.podcast_slug, 1, 'chrono-trigger', 'Chrono Trigger', at=_EXPIRED)
    by_id, by_name, key = _sweep(expired, by_id=None)
    by_id.assert_called_once_with(1, canonical=False)
    assert key not in state.resolutions and 1 not in state.games
    assert resolver.count_pending() == 1          # the next sweep asks it again


def test_an_open_question_is_looked_at_again_once_expired(tmp_corrections):
    miss = lambda at: lambda a: cache_entry(a.podcast_slug, None, None, None, at=at)  # noqa: E731
    by_id, by_name, _ = _sweep(miss(utcnow().isoformat()))
    by_name.assert_not_called()
    by_id, by_name, key = _sweep(miss(_EXPIRED))
    by_id.assert_not_called()
    by_name.assert_called_once()
    assert state.resolutions[key].igdb_id == 7


def test_a_shipped_search_correction_searches_its_query(tmp_corrections):
    import corrections
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: _fresh_entry(appearance)})   # answered…
    tmp_corrections.write_text('{"corrections": [{"podcast_name": "Chrono Trigger", '
                               '"search_name": "Chrono Trigger SNES"}]}', encoding='utf-8')
    corrections.load()                                                 # …then a fix ships
    question = question_for(game, appearance.episode)
    assert question.key.startswith('search|chrono-trigger-snes|')
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Chrono Trigger')) as by_name, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.schedule_resolve()
    assert by_name.call_args.args == ('Chrono Trigger SNES', question.window)
    assert state.resolutions[question.key].method == 'pin'      # a curator's search
    state.prune_igdb_cache()
    assert set(state.resolutions) == {question.key}             # the old question is gone


def test_a_settled_appearance_on_a_fresh_game_costs_nothing(tmp_corrections):
    by_id, by_name, _ = _sweep(_fresh_entry)
    by_id.assert_not_called()
    by_name.assert_not_called()


def test_an_igdb_error_is_retried_after_a_backoff_not_every_sweep(tmp_corrections):
    game, appearance = _single_soj_game()
    question = question_for(game, appearance.episode)
    with patch('resolver.fetch_by_name', side_effect=OSError('IGDB down')):
        resolver.resolve(question)
    failed = state.resolutions[question.key]
    assert (failed.igdb_id, failed.attempts, failed.last_error) == (None, 1, 'IGDB down')
    assert failed.retry_at > utcnow().isoformat()
    assert resolver.count_pending() == 0                   # waiting out its backoff

    state.resolutions[question.key] = replace(failed, retry_at=_EXPIRED)
    assert resolver.count_pending() == 1                   # due again
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Chrono Trigger')), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        resolver.resolve(question)
    settled = state.resolutions[question.key]
    assert (settled.igdb_id, settled.attempts, settled.retry_at) == (7, 0, None)


def test_a_failed_retry_keeps_serving_the_previous_answer(tmp_corrections):
    game, appearance = _single_soj_game()
    set_cache({appearance.podcast_slug: _fresh_entry(appearance)})
    with patch('resolver.fetch_by_name', side_effect=OSError('IGDB down')):
        resolver.resolve(question_for(game, appearance.episode))
    entry = state.entries()[appearance.podcast_slug]
    assert (entry.igdb_slug, entry.resolution.attempts) == ('chrono-trigger', 1)


# ── Admin: search and corrections (who may call them: test_auth) ─────────────

from conftest import admin_header   # noqa: E402


def test_igdb_search_requires_a_query(client):
    r = client.get('/games/igdb-search', headers=admin_header())
    assert_contract(r, GAMES['igdb_search']['bad_request'])


def test_igdb_search_returns_results(client):
    rows = [{'id': 1, 'name': 'Chrono Trigger', 'slug': 'chrono-trigger',
             'released': '1995', 'coverImageId': 'co1'}]
    with patch('games.search_games', return_value=rows):
        r = client.get('/games/igdb-search?q=chrono', headers=admin_header())
    assert_contract(r, GAMES['igdb_search']['success'])
    assert r.get_json()['results'] == rows


@pytest.mark.parametrize('body', [
    {'igdbId': 1, 'podcastId': 'nope'},       # an unknown podcast
    {},                                        # neither a pin nor a name
    {'igdbId': 'nope'},                        # a pin that isn't an id
])
def test_a_correction_that_says_nothing_valid_is_refused(client, tmp_corrections, body):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.put('/games/corrections', headers=admin_header(),
                   json={'nameSlug': make_slug('Silent Hill 2'), **body})
    assert_contract(r, GAMES['corrections']['bad_request'])


def test_correction_rejects_an_unknown_game(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.put('/games/corrections', headers=admin_header(),
                   json={'nameSlug': 'no-such-game', 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['not_found'])


def test_correction_write_pins_purges_and_reresolves(client, tmp_corrections):
    import json as _json
    from igdb import IgdbResult
    ns = make_slug('Silent Hill 2')
    # Start from a wrong resolution, as the FDG date-window bug produced.
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 9, 'astrobotanica', 'Astrobotanica'),
    })
    fixed = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2',
                       data={'released': '2001'}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=fixed), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['success'])
    body = r.get_json()
    assert body['slug'] == 'silent-hill-2'
    assert body['igdb']['released'] == '2001'
    assert body['corrected'] is True
    # The stale 'astrobotanica' cache row is gone…
    assert state.entries()[f'{ns}-original'].igdb_slug == 'silent-hill-2'
    # …and the pin landed in the git-tracked file, keyed on the feed's wording.
    written = _json.loads(tmp_corrections.read_text())['corrections']
    assert written == [{'podcast_name': 'Silent Hill 2', 'igdb_id': 1}]


def test_correction_scoped_to_one_podcast_leaves_the_other_alone(client, tmp_corrections):
    from igdb import IgdbResult
    ns  = make_slug('Chrono Trigger')
    soj = _parse_feed(_SOJ_RSS, extractor=PODCAST_BY_ID['silence-on-joue'].extractor,
                      podcast_id='silence-on-joue')
    fdg = _parse_feed(_FDG_RSS, extractor=PODCAST_BY_ID['fin-du-game'].extractor,
                      podcast_id='fin-du-game')
    episodes = soj + fdg
    _assign_url_slugs(episodes)
    episode_index, game_index = feeds.build_indexes(episodes)
    state.episodes = episodes
    state.episode_index   = episode_index
    state.game_index      = game_index
    set_cache({
        f'{ns}-soj1': _entry(f'{ns}-soj1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
        f'{ns}-fdg1': _entry(f'{ns}-fdg1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
    })
    state.data_version += 1

    fixed = IgdbResult(id=1, name='Chrono Trigger', slug='chrono-trigger',
                       data={'released': '1995'}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=fixed), \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1, 'podcastId': 'fin-du-game'})
    assert r.status_code == 200
    # Only the FDG appearance moved; the SOJ one keeps its own resolution — the
    # split the per-appearance grouping exists to allow.
    assert state.entries()[f'{ns}-fdg1'].igdb_slug == 'chrono-trigger'
    assert state.entries()[f'{ns}-soj1'].igdb_slug == 'chrono-trigger--3'
    assert [e['slug'] for e in r.get_json()['episodes']] == ['fdg1']


def test_delete_correction_reverts_to_the_name_search(client, tmp_corrections):
    import corrections
    from igdb import IgdbResult
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})
    corrections.upsert('Silent Hill 2', igdb_id=1)

    searched = IgdbResult(id=7, name='Silent Hill 2', slug='silent-hill-2',
                          data={'released': '2001'}, is_child=False)
    with patch('resolver.fetch_by_name', return_value=searched) as by_name, \
         patch('resolver.fetch_by_id') as by_id, \
         patch('resolver.metacritic.fetch_metascore', return_value=None), \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.delete('/games/corrections', headers=admin_header(),
                          json={'nameSlug': ns})
    assert r.status_code == 200
    by_id.assert_not_called()      # no longer pinned
    assert by_name.called
    assert corrections.CORRECTIONS == []


def test_delete_correction_that_does_not_exist_404s(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    r = client.delete('/games/corrections', headers=admin_header(),
                      json={'nameSlug': make_slug('Silent Hill 2')})
    assert_contract(r, GAMES['corrections']['not_found'])


def test_corrections_write_is_refused_when_the_file_is_read_only(client, tmp_corrections):
    # Stands in for prod, where corrections.json ships in the read-only image layer.
    _seed(_TWO_EPISODES_SAME_NAME, {})
    with patch('corrections.is_writable', return_value=False):
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': make_slug('Silent Hill 2'), 'igdbId': 1})
    assert_contract(r, GAMES['corrections']['read_only'])
    assert 'dev' in r.get_json()['error']


def test_podcast_igdb_refresh_purges_only_that_podcast(client):
    ns  = make_slug('Chrono Trigger')
    soj = _parse_feed(_SOJ_RSS, extractor=PODCAST_BY_ID['silence-on-joue'].extractor,
                      podcast_id='silence-on-joue')
    fdg = _parse_feed(_FDG_RSS, extractor=PODCAST_BY_ID['fin-du-game'].extractor,
                      podcast_id='fin-du-game')
    _, game_index = feeds.build_indexes(soj + fdg)
    state.game_index = game_index
    set_cache({
        f'{ns}-soj1': _entry(f'{ns}-soj1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
        f'{ns}-fdg1': _entry(f'{ns}-fdg1', 5, 'chrono-trigger--3', 'Chrono Trigger'),
    })
    with patch('resolver.schedule_resolve') as sched:
        r = client.post('/games/podcasts/fin-du-game/igdb-refresh',
                        headers=admin_header())
    assert_contract(r, GAMES['podcast_igdb_refresh']['success'])
    assert r.get_json()['purged'] == 1
    soj_q, fdg_q = (question_for(game_index[ns], a.episode).key
                    for a in sorted(game_index[ns].appearances,
                                    key=lambda a: a.episode.podcast_id != 'silence-on-joue'))
    assert fdg_q not in state.resolutions            # purged
    assert soj_q in state.resolutions                # untouched
    sched.assert_called_once()


def test_podcast_igdb_refresh_unknown_podcast_404s(client):
    r = client.post('/games/podcasts/nope/igdb-refresh', headers=admin_header())
    assert_contract(r, GAMES['podcast_igdb_refresh']['not_found'])


def test_resolution_stats_shape(client):
    # The console's content is a dev tool's: only its shape is held.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {f'{ns}-remake': _entry(f'{ns}-remake', 9, 'astrobotanica', 'Astrobotanica')})
    assert_contract(client.get('/games/resolution-stats', headers=admin_header()),
                    GAMES['resolution_stats']['success'])


def test_detail_reports_whether_a_correction_applies_at_its_scope(client, tmp_corrections):
    # A correction scoped to a podcast this entry has no episodes from must not
    # light up the "remove the correction" affordance.
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {})          # seeded as silence-on-joue
    assert serializers.load_game(ns)['corrected'] is False
    corrections.upsert('Silent Hill 2', 'fin-du-game', igdb_id=1)
    assert serializers.load_game(ns)['corrected'] is False
    corrections.upsert('Silent Hill 2', igdb_id=1)
    assert serializers.load_game(ns)['corrected'] is True


def test_stats_reports_read_only_deployments(client, tmp_corrections):
    _seed(_TWO_EPISODES_SAME_NAME, {})
    with patch('corrections.is_writable', return_value=False):
        body = client.get('/games/resolution-stats', headers=admin_header()).get_json()
    assert body['writable'] is False


# ── Display-name edits ────────────────────────────────────────────────────────

def test_catalog_applies_a_podcast_scoped_display_name(tmp_corrections):
    # group_display_name must look the correction up at the appearance's own
    # podcast scope, or a podcast_id-scoped rename would show in the admin
    # console (which passes podcast_id) but never in the catalog.
    import corrections
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 2, 'silent-hill-2-remake', 'Silent Hill 2 Remake'),
    })
    corrections.upsert('Silent Hill 2', 'silence-on-joue',
                       display_name='Silent Hill 2 (renommé)')
    names = {g['slug']: g['name'] for g in serializers.build_catalog()}
    assert names['silent-hill-2-remake'] == 'Silent Hill 2 (renommé)'


def test_renaming_does_not_re_resolve(client, tmp_corrections):
    # display_name is applied at response time, so a rename must not burn a round
    # of IGDB + Metacritic + HLTB calls to arrive at the same entry.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 1, 'silent-hill-2', 'Silent Hill 2'),
    })
    before = state.data_version
    with patch('resolver.fetch_by_id') as by_id, patch('resolver.fetch_by_name') as by_name:
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'displayName': 'Silent Hill 2 (2001)'})
    assert_contract(r, GAMES['corrections']['success'])
    by_id.assert_not_called()
    by_name.assert_not_called()
    # The cached resolution survives…
    assert state.entries()[f'{ns}-original'].igdb_slug == 'silent-hill-2'
    # …but the derived caches are invalidated so the new name is served.
    assert state.data_version > before
    assert r.get_json()['name'] == 'Silent Hill 2 (2001)'


def test_a_game_is_scraped_once_for_all_its_episodes():
    # Metacritic and HowLongToBeat take ~1–10 s a game: a second question landing
    # on the same game (another year's episodes) reuses its figures.
    ts_2024, ts_2025 = 1_705_000_000, 1_736_000_000
    with patch('resolver.fetch_by_name', return_value=_igdb_hit('Zelda')), \
         patch('resolver.metacritic.fetch_metascore', return_value=91) as mc, \
         patch('resolver.hltb.fetch_time_to_beat', return_value=40) as hl:
        resolver.resolve(_ask('Zelda', ts_2024), use_llm=False)
        resolver.resolve(_ask('Zelda', ts_2025), use_llm=False)
    assert len(state.resolutions) == 2
    assert mc.call_count == hl.call_count == 1
    assert state.games[7].enriched
    assert (state.games[7].data['metacritic'], state.games[7].data['timeToBeatHours']) == (91, 40)


def test_a_correction_moving_onto_a_cached_game_reuses_its_data(client, tmp_corrections):
    # Pinning re-decides which game this is; that game's data is already here.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-original': _entry(f'{ns}-original', 9, 'astrobotanica', 'Astrobotanica'),
        f'{ns}-remake':   _entry(f'{ns}-remake', 1, 'silent-hill-2', 'Silent Hill 2',
                                 metacritic=89),
    })
    from igdb import IgdbResult
    pinned = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2',
                        data={}, is_child=False)
    with patch('resolver.fetch_by_id', return_value=pinned), \
         patch('resolver.metacritic.fetch_metascore') as mc:
        r = client.put('/games/corrections', headers=admin_header(),
                       json={'nameSlug': ns, 'igdbId': 1})
    mc.assert_not_called()
    assert r.get_json()['igdb']['metacritic'] == 89
    assert state.entries()[f'{ns}-original'].igdb_slug == 'silent-hill-2'


def test_an_explicit_igdb_refresh_fetches_the_games_data_again(client):
    # The one way to get a fresh Metacritic score before the TTL.
    ns = make_slug('Silent Hill 2')
    _seed(_TWO_EPISODES_SAME_NAME, {
        f'{ns}-remake': _entry(f'{ns}-remake', 1, 'silent-hill-2', 'Silent Hill 2',
                               metacritic=80),
    })
    from igdb import IgdbResult
    same = IgdbResult(id=1, name='Silent Hill 2', slug='silent-hill-2', data={}, is_child=False)
    with patch('resolver.fetch_by_name', return_value=same), \
         patch('resolver.metacritic.fetch_metascore', return_value=89) as mc, \
         patch('resolver.hltb.fetch_time_to_beat', return_value=None), \
         patch('resolver.fetch_time_to_beat', return_value=None):
        r = client.post('/games/silent-hill-2/igdb-refresh', headers=auth_header())
    assert r.status_code == 200
    mc.assert_called_once()
    assert state.games[1].data['metacritic'] == 89


# ── A test's chapters ─────────────────────────────────────────────────────────

def test_every_chapter_of_a_test_carries_its_page():
    """The chapter a test starts in (at its critique, after the chapter's own
    start), the one it goes on in after an ad (the same game by name, or by page
    under another name) all carry the test's page; a chapter on another game, or
    on none, carries nothing."""
    from models import Chapter, Episode, GameMention
    pages = {'Hades II':  ('Hades II', 'hades-ii', 'co1'),
             'Hades 2':   ('Hades II', 'hades-ii', 'co1'),
             'Silksong':  ('Hollow Knight: Silksong', 'silksong', 'co2')}
    ep = Episode(title='Ep', slug='g', audio_url=None, pub_ts=None, image_url=None, description=None,
                 chapters=[Chapter('0:00', 0, 'Intro'),
                           Chapter('5:00', 300, 'Hades II, la critique'),
                           Chapter('20:00', 1200, 'Hades II, suite', game_name='Hades II'),
                           Chapter('30:00', 1800, 'Encore Hades', game_name='Hades 2'),
                           Chapter('40:00', 2400, 'News Silksong', game_name='Silksong'),
                           Chapter('50:00', 3000, 'Courrier')],
                 games=[GameMention('Hades II', '5:40', 340), GameMention('Silksong', '49:45', 2985)])
    with patch('serializers._resolution', lambda m, _ep: pages.get(m.name)):
        chapters = serializers.serialise_episode(ep)['chapters']
    # Silksong's test starts 15 s before the mail's chapter: it is that chapter's,
    # and its news chapter is its by name.
    assert [c.get('slug') for c in chapters] == [None, 'hades-ii', 'hades-ii', 'hades-ii', 'silksong', 'silksong']
    assert chapters[2]['coverImageId'] == 'co1'


# ── A podcast's own image ─────────────────────────────────────────────────────

def test_channel_image_is_the_feed_s_own():
    from rss import channel_image
    itunes = b'''<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>
      <itunes:image href="https://example.com/show.jpg"/><image><url>https://example.com/other.jpg</url></image>
      <item><itunes:image href="https://example.com/ep.jpg"/></item></channel></rss>'''
    plain = b'<rss><channel><image><url> https://example.com/show.png </url></image></channel></rss>'
    assert channel_image(itunes) == 'https://example.com/show.jpg'
    assert channel_image(plain) == 'https://example.com/show.png'
    assert channel_image(b'<rss><channel></channel></rss>') is None


def test_an_episode_s_podcast_carries_the_feed_s_image(client):
    rss = MINIMAL_RSS.replace(b'<channel>', b'<channel><image><url>https://example.com/show.jpg</url></image>', 1)
    with patch('feeds.http.get', return_value=mock_rss_response(rss)), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    ep = client.get('/games/episodes', headers=auth_header()).get_json()[0]
    assert ep['podcast']['imageUrl'] == 'https://example.com/show.jpg'
