"""Reading a feed (`rss.py`): the names a title proposes, an item, its HTML, the channel's image."""
from dataclasses import replace
from html import escape

import pytest

from utils import make_slug
from rss import extract_game_names as _extract_game_names, extract_legacy_names as _extract_legacy_names, extract_fdg_names as _extract_fdg_names, parse_feed as _parse_feed, sanitize_html as _sanitize_html
from catalog_fixtures import MINIMAL_RSS


def test_extract_game_names_guillemets():
    names = _extract_game_names('On a joué à «Zelda» et «Mario»')
    assert names == ['Zelda', 'Mario']


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


def test_a_feed_item_becomes_an_episode():
    episodes = _parse_feed(MINIMAL_RSS)
    assert len(episodes) == 2                                  # one without a game too
    ep, other = episodes
    assert (ep.slug, ep.audio_url, other.slug) == ('ep1guid', 'https://example.com/ep1.mp3', 'ep2guid')
    assert ep.pub_ts == 1_705_276_800                          # Mon, 15 Jan 2024 00:00 UTC
    assert [(g.name, g.timestamp, g.timestamp_seconds) for g in ep.games] == [
        ('Zelda', '00:30', 30), ('Mario Kart', '01:00', 60)]
    assert (other.title, other.games) == ('Quelle est la meilleure plateforme ?', [])


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


def test_parse_feed_guid_fallback_to_enclosure():
    rss = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>No Guid Here</title>
    <enclosure url="https://example.com/x.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate><description></description></item>
</channel></rss>"""
    ep = _parse_feed(rss)[0]
    assert ep.slug == make_slug('https://example.com/x.mp3')


def test_channel_image_is_the_feed_s_own():
    from rss import channel_image
    itunes = b'''<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>
      <itunes:image href="https://example.com/show.jpg"/><image><url>https://example.com/other.jpg</url></image>
      <item><itunes:image href="https://example.com/ep.jpg"/></item></channel></rss>'''
    plain = b'<rss><channel><image><url> https://example.com/show.png </url></image></channel></rss>'
    assert channel_image(itunes) == 'https://example.com/show.jpg'
    assert channel_image(plain) == 'https://example.com/show.png'
    assert channel_image(b'<rss><channel></channel></rss>') is None


def _item_chapters(description_html):
    rss = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><item>
      <title>Episode</title><guid>g1</guid><enclosure url="https://example.com/a.mp3" type="audio/mpeg" length="0" />
      <description>{escape(description_html)}</description></item></channel></rss>""".encode()
    (episode,) = _parse_feed(rss, extractor=lambda _title: [])
    return [(c.timestamp, c.timestamp_seconds, c.title) for c in episode.chapters]


@pytest.mark.parametrize('description,expected', [
    # A timecode at a line's start, then the title; the separator isn't part of it.
    ('<p>03:00 - Gears of War: Judgment<br>29:30 -- Luigi\'s Mansion: Dark Moon</p>',
     [('03:00', 180, 'Gears of War: Judgment'), ('29:30', 1770, "Luigi's Mansion: Dark Moon")]),
    # In brackets (ORIGAMI), with an hour.
    ('<p>(00:00) Sommaire</p><br><p>(46:33) Critique Planet Zoo 2</p><p>[1:21:39] Critique Final Fantasy Resonance</p>',
     [('00:00', 0, 'Sommaire'), ('46:33', 2793, 'Critique Planet Zoo 2'),
      ('1:21:39', 4899, 'Critique Final Fantasy Resonance')]),
    # A list item is a line of its own (ZQSD, The Game Informer Show).
    ('<ul><li>07:30 : La Blizzcon</li><li>37:00 : Critique 1 : Silent Hill f</li></ul>',
     [('07:30', 450, 'La Blizzcon'), ('37:00', 2220, 'Critique 1 : Silent Hill f')]),
    # A time inside a sentence, or glued to its title, opens no chapter.
    ('<p>Rendez-vous à 21:00 pour le live.</p><p>1:37:02Halloween</p>', []),
])
def test_a_description_lists_its_chapters(description, expected):
    assert _item_chapters(description) == expected
