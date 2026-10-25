"""The catalog's routes (`games.py`) and payloads (`serializers.py`): grouping by game, detail, episodes, ETags."""
import datetime
from dataclasses import replace
from unittest.mock import patch

import pytest

import catalog_state as state
import feeds
import serializers
from utils import make_slug
from contract import assert_contract
from conftest import auth_header, cache_entry, set_cache
from rss import parse_feed as _parse_feed
from catalog_fixtures import GAMES, MINIMAL_RSS, _TWO_EPISODES_SAME_NAME, _entry, _seed, mock_rss_response


def test_no_auth_returns_401(client):
    r = client.get('/games')
    assert_contract(r, GAMES['catalog']['unauthorized'])


def test_catalog_returns_list(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    zelda = next(a for a in state.game_index[make_slug('Zelda')].appearances)
    set_cache({zelda.podcast_slug: cache_entry('z', 1, 'zelda', 'Zelda', {'metacritic': 90, 'genres': ['x']})})
    state.data_version += 1
    r = client.get('/games', headers=auth_header())
    assert_contract(r, GAMES['catalog']['success'])      # a resolved game's igdb, slim
    assert any(g['name'] == 'Zelda' and g['igdb'] for g in r.get_json()['games'])


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


def test_episodes_returns_list_with_slim_shape(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/episodes', headers=auth_header())
    assert_contract(r, GAMES['episodes']['success'])     # slim: no description, no chapters
    assert len(r.get_json()) > 0


def test_episode_detail_returns_unified_shape(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    slug = client.get('/games/episodes', headers=auth_header()).get_json()[0]['slug']
    r = client.get(f'/games/episode?slug={slug}', headers=auth_header())
    assert_contract(r, GAMES['episode']['success'])      # the full shape


def test_episode_missing_slug_returns_400(client):
    r = client.get('/games/episode', headers=auth_header())
    assert_contract(r, GAMES['episode']['bad_request'])


def test_episode_unknown_slug_returns_404(client):
    with patch('feeds.http.get', return_value=mock_rss_response()), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    r = client.get('/games/episode?slug=does-not-exist', headers=auth_header())
    assert_contract(r, GAMES['episode']['not_found'])


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


def test_an_episode_s_podcast_carries_the_feed_s_image(client):
    rss = MINIMAL_RSS.replace(b'<channel>', b'<channel><image><url>https://example.com/show.jpg</url></image>', 1)
    with patch('feeds.http.get', return_value=mock_rss_response(rss)), \
         patch('resolver.schedule_resolve'):
        client.get('/games', headers=auth_header())
    ep = client.get('/games/episodes', headers=auth_header()).get_json()[0]
    assert ep['podcast']['imageUrl'] == 'https://example.com/show.jpg'
