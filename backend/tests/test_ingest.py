"""Transcribing episodes and reading their transcripts. DeepInfra and the LLM are
always mocked: `_deepinfra` stands in for the download and the transcription,
`_reads` for OpenRouter, answering by episode title."""
import contextlib
import json
from unittest.mock import MagicMock, patch

import pytest

import catalog_state as state
import feeds
import ingest
import llm
import transcribe
from config import Config
from db import get_db
from podcasts import PODCAST_BY_ID

_RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
  <item><title>Control Resonant Rewards Your Patience</title><guid>bes-control</guid>
    <enclosure url="https://example.com/control.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 02 Oct 2026 09:00:00 +0000</pubDate>
    <description>Plus, we talk about Gears of War: E-DAY.</description></item>
  <item><title>Listener Mail</title><guid>bes-mail</guid>
    <enclosure url="https://example.com/mail.mp3" type="audio/mpeg" length="0" />
    <pubDate>Fri, 25 Sep 2026 09:00:00 +0000</pubDate><description>Your questions.</description></item>
</channel></rss>"""

_SEGMENTS = [{'start': 0.0, 'end': 240.0, 'text': ' Welcome to the Besties.'},
             {'start': 240.0, 'end': 1860.0, 'text': ' Control Resonant is great.'},
             {'start': 1860.0, 'end': 2750.0, 'text': ' Gears of War E-Day looks amazing.'},
             {'start': 2750.0, 'end': 2840.0, 'text': ' A normal golf game, by the way.'}]

_CONTROL = {'sections': [
    {'title': 'Welcome', 'game': None, 'start_s': 0, 'end_s': 240},
    {'title': 'Control Resonant', 'game': 'Control Resonant', 'start_s': 240, 'end_s': 1860,
     'votes': ['positive', 'enthusiastic', 'mixed'], 'pros': ['Surreal Manhattan'],
     'cons': ['Slow start'], 'verdict_s': 1800},
    {'title': 'Gears of War: E-DAY', 'game': 'Gears of War: E-DAY', 'start_s': 1860,
     'end_s': 2750, 'votes': ['positive'], 'pros': ['Beautiful'], 'cons': [], 'verdict_s': 2000},
    {'title': 'A Normal Golf Game', 'game': 'A Normal Golf Game', 'start_s': 2750,
     'end_s': 2840, 'votes': ['positive'], 'pros': [], 'cons': [], 'verdict_s': 2800}]}
_MAIL = {'sections': [{'title': 'Listener mail', 'game': None, 'start_s': 0, 'end_s': 2840}]}


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(Config, 'DEEPINFRA_API_KEY', 'test-deepinfra')
    monkeypatch.setattr(Config, 'OPENROUTER_API_KEY', 'test-openrouter')


@pytest.fixture
def besties():
    r = MagicMock(status_code=200, content=_RSS, headers={})
    r.raise_for_status.return_value = None
    with patch.object(feeds, 'PODCASTS', [PODCAST_BY_ID['the-besties']]), \
         patch('feeds.http.get', return_value=r):
        # Fetched, not built: until read, the show has no episode in the catalog.
        feeds._fetch_feed(PODCAST_BY_ID['the-besties'])
        yield


@contextlib.contextmanager
def _deepinfra(segments=_SEGMENTS, cost=0.0118):
    """Mock the audio download and DeepInfra's transcription; yields the two
    mocks and the bodies sent, read as the upload would."""
    audio = MagicMock()
    audio.__enter__.return_value = audio
    audio.iter_content.return_value = [b'ID3', b'audio']
    answer = MagicMock()
    answer.json.return_value = {'segments': segments, 'duration': 2840.0,
                                'inference_status': {'cost': cost}}
    bodies = []

    def upload(*_a, data=None, **_kw):
        bodies.append(data.read())
        return answer
    with patch('transcribe._http.get', return_value=audio) as get, \
         patch('transcribe._http.post', side_effect=upload) as post:
        yield get, post, bodies


def _reads(answers: dict):
    """A mock for `llm.http.post` reading transcripts, answering by episode title."""
    def reply(*_a, json=None, **_kw):
        message = json['messages'][1]['content']
        title = message.split('\n')[1].removeprefix('Title: ')
        r = MagicMock()
        r.raise_for_status.return_value = None
        r.json.return_value = {'choices': [{'message': {'content':
                                            __import__('json').dumps(answers[title])}}]}
        return r
    return patch('llm.http.post', side_effect=reply)


def _episode(guid):
    return next(ep for ep in feeds.all_episodes() if ep.slug == guid)


# ── Averaging the hosts' verdicts ─────────────────────────────────────────────

@pytest.mark.parametrize('votes, expected', [
    (['enthusiastic', 'positive', 'negative', 'positive'], 'positive'),   # 1.75
    (['positive', 'negative'], 'mixed'),                                  # 1.0
    (['mixed', 'negative'], 'mixed'),            # 0.5: a split goes to «mixed»
    (['positive', 'enthusiastic'], 'positive'),  # 2.5: the step nearer «mixed»
    (['negative'], 'negative'),
    (['Patrick: mixed', 'Marius: Negative'], 'mixed'),   # a host's name is dropped
    (['great', 'meh'], None),                    # not on the scale
    ([], None),
])
def test_the_verdict_is_the_hosts_average(votes, expected):
    assert llm.verdict(votes) == expected


def test_a_section_without_a_verdict_has_no_critique():
    sections = llm._sections({'sections': [
        {'title': 'News', 'game': 'Dredge', 'start_s': 600, 'end_s': 900, 'votes': []},
        {'title': 'Intro', 'game': None, 'start_s': 0, 'end_s': 600, 'votes': ['positive']},
        {'title': 'Broken', 'start_s': 'x', 'end_s': 1},
    ]})
    assert [(s['title'], s['critique']) for s in sections] == [('Intro', None), ('News', None)]


def test_pros_and_cons_are_kept_to_three():
    [section] = llm._sections({'sections': [
        {'title': 'Saros', 'game': 'Saros', 'start_s': 0, 'end_s': 900, 'votes': ['positive'],
         'pros': ['a', 'b', 'c', 'd'], 'cons': ['', 'e'], 'verdict_s': 850}]})
    assert section['critique'] == {'verdict': 'positive', 'pros': ['a', 'b', 'c'],
                                   'cons': ['e'], 'at': 850}


# ── Transcribing ──────────────────────────────────────────────────────────────

def test_the_upload_is_a_multipart_body_read_as_it_is_sent(tmp_path):
    path = tmp_path / 'audio'
    path.write_bytes(b'x' * 5000)
    with path.open('rb') as f:
        body = transcribe._Multipart({'language': 'en'}, f)
        sent = b''
        while chunk := body.read(1000):
            assert len(chunk) <= 1000
            sent += chunk
    assert len(sent) == len(body)
    boundary = body.content_type.split('boundary=')[1]
    assert sent.startswith(f'--{boundary}\r\nContent-Disposition: form-data; name="language"'
                           f'\r\n\r\nen\r\n'.encode())
    assert b'name="audio"; filename="audio"' in sent
    assert sent.endswith(b'x' * 5000 + f'\r\n--{boundary}--\r\n'.encode())


def test_a_transcription_keeps_the_segments_and_what_it_cost(keys):
    with _deepinfra() as (get, post, bodies):
        t = transcribe.transcribe('https://example.com/a.mp3', 'fr')
    assert get.call_args.kwargs['stream'] is True
    sent = post.call_args.kwargs
    assert isinstance(sent['data'], transcribe._Multipart)      # streamed, not built in memory
    assert sent['headers']['Content-Type'] == sent['data'].content_type
    assert b'name="language"\r\n\r\nfr\r\n' in bodies[0]
    assert bodies[0].count(b'ID3audio') == 1
    assert t.segments[0] == [0.0, 240.0, 'Welcome to the Besties.']
    assert (t.model, t.duration, t.cost) == (Config.TRANSCRIBE_MODEL, 2840.0, 0.0118)


def test_a_transcript_without_speech_is_a_failure(keys):
    with _deepinfra(segments=[{'start': 0, 'end': 5, 'text': '  '}]), \
         pytest.raises(ValueError):
        transcribe.transcribe('https://example.com/a.mp3', 'en')


# ── What is left to do ────────────────────────────────────────────────────────

def test_nothing_is_pending_without_the_keys(besties):
    assert ingest.pending() == []


def test_every_episode_is_pending_newest_first(keys, besties):
    assert [ep.slug for ep in ingest.pending()] == ['bes-control', 'bes-mail']


def test_an_episode_is_transcribed_once_and_read(keys, besties):
    with _deepinfra() as (_, post, _), _reads({'Control Resonant Rewards Your Patience': _CONTROL}):
        assert ingest.ingest(_episode('bes-control')) is True
    assert post.call_count == 1
    assert [ep.slug for ep in ingest.pending()] == ['bes-mail']
    assert transcribe.totals() == {'hours': 0.8, 'cost': 0.01}


def test_the_reading_sends_the_transcript_but_caches_only_what_identifies_it(keys, besties):
    with _deepinfra(), _reads({'Control Resonant Rewards Your Patience': _CONTROL}) as read:
        ingest.ingest(_episode('bes-control'))
    message = read.call_args.kwargs['json']['messages'][1]['content']
    assert 'Write every title, pro and con in English.' in message
    assert '[240s - 1860s] Control Resonant is great.' in message
    assert 'Plus, we talk about Gears of War: E-DAY.' in message      # its spelling wins
    with get_db() as conn:
        cached = json.loads(conn.execute("SELECT input FROM llm_cache WHERE task = 'transcript'")
                            .fetchone()['input'])
    assert cached['guid'] == 'bes-control' and 'Control Resonant is great' not in json.dumps(cached)


def test_a_failed_transcription_waits_out_a_delay(keys, besties):
    with patch('transcribe._http.get', side_effect=OSError('feed host down')):
        assert ingest.ingest(_episode('bes-control')) is False
    row = transcribe.rows()['bes-control']
    assert (row.model, row.attempts, row.last_error) == (None, 1, 'OSError: feed host down')
    assert [ep.slug for ep in ingest.pending()] == ['bes-mail']


def test_a_failed_reading_keeps_the_transcript(keys, besties):
    with _deepinfra(), patch('llm.http.post', side_effect=OSError('down')):
        assert ingest.ingest(_episode('bes-control')) is False
    assert transcribe.load('bes-control') is not None
    with get_db() as conn:
        conn.execute("UPDATE transcripts SET retry_at = '2000-01-01'")
    with _deepinfra() as (_, post, _), _reads({'Control Resonant Rewards Your Patience': _CONTROL}):
        assert ingest.ingest(_episode('bes-control')) is True
    post.assert_not_called()                              # not transcribed twice
    assert transcribe.rows()['bes-control'].retry_at is None


def test_a_new_prompt_reads_again_without_transcribing_again(keys, besties, monkeypatch):
    with _deepinfra(), _reads({'Control Resonant Rewards Your Patience': _CONTROL}):
        ingest.ingest(_episode('bes-control'))
    monkeypatch.setattr(llm, '_TRANSCRIPT_V', llm._TRANSCRIPT_V + 1)
    assert 'bes-control' in [ep.slug for ep in ingest.pending()]
    with _deepinfra() as (_, post, _), _reads({'Control Resonant Rewards Your Patience': _CONTROL}):
        assert ingest.ingest(_episode('bes-control')) is True
    post.assert_not_called()


# ── What the catalog gets from a reading ──────────────────────────────────────

def _ingest_all():
    with _deepinfra(), _reads({'Control Resonant Rewards Your Patience': _CONTROL,
                               'Listener Mail': _MAIL}):
        for ep in ingest.pending():
            ingest.ingest(ep)
    feeds.rebuild()


def test_a_read_episode_is_about_the_games_of_its_long_sections(keys, besties):
    _ingest_all()
    [ep] = state.episodes                       # the mail is about no game: left out
    assert [(g.name, g.timestamp_seconds) for g in ep.games] == [
        ('Control Resonant', 240), ('Gears of War: E-DAY', 1860)]   # not the 90-s golf aside
    assert [c.title for c in ep.chapters] == [
        'Welcome', 'Control Resonant', 'Gears of War: E-DAY', 'A Normal Golf Game']


def test_each_game_gets_the_verdict_of_its_section(keys, besties):
    _ingest_all()
    control, gears = state.episodes[0].games
    assert control.critique == {'verdict': 'positive', 'pros': ['Surreal Manhattan'],
                                'cons': ['Slow start'], 'at': 1800}
    assert gears.critique['verdict'] == 'positive'


def test_a_reading_wins_over_the_description_read(keys, besties):
    with patch('feeds.llm.reviewed_games', return_value=['Control Resonant']):
        _ingest_all()
    assert [g.name for g in state.episodes[0].games] == ['Control Resonant', 'Gears of War: E-DAY']


def test_an_episode_s_own_chapters_win_over_its_reading(keys):
    from models import Chapter, Episode, GameMention
    ep = Episode(title='S17E16 - «Super Mario RPG»', slug='soj-1', audio_url=None, pub_ts=None,
                 image_url=None, description='',
                 chapters=[Chapter('37:06', 2226, 'Super Mario RPG')],
                 games=[GameMention('Super Mario RPG', '37:06', 2226)],
                 podcast_id='silence-on-joue')
    sections = llm._sections({'sections': [
        {'title': 'Intro', 'game': None, 'start_s': 0, 'end_s': 2227},
        {'title': 'Super Mario RPG', 'game': 'Super Mario RPG', 'start_s': 2227,
         'end_s': 3338, 'votes': ['positive'], 'verdict_s': 3097}]})
    feeds._apply_readings([ep], {'soj-1': sections})
    assert [c.title for c in ep.chapters] == ['Super Mario RPG']
    assert ep.games[0].critique['verdict'] == 'positive'
    assert (ep.games[0].timestamp_seconds, ep.games[0].critique['at']) == (2226, 3097)


def _soj_episode():
    from models import Chapter, Episode, GameMention
    return Episode(title='S17E16 - «Karmazoo» et les «jeux» de Microids', slug='soj-16',
                   audio_url=None, pub_ts=None, image_url=None, description='',
                   chapters=[Chapter('2:34:54', 9294, 'Karmazoo')],
                   games=[GameMention('Karmazoo', '2:34:54', 9294)],
                   podcast_id='silence-on-joue')


_S17E16 = llm._sections({'sections': [
    {'title': 'Intro', 'game': None, 'start_s': 0, 'end_s': 3755},
    {'title': 'Goldorak', 'game': 'Goldorak : Le Festin des Loups', 'start_s': 3755,
     'end_s': 5057, 'votes': ['negative'], 'verdict_s': 4900},
    {'title': 'Dredge (news)', 'game': 'Dredge', 'start_s': 5057, 'end_s': 5100,
     'votes': ['mixed']},
    {'title': 'KarmaZoo', 'game': 'KarmaZoo', 'start_s': 9365, 'end_s': 10629,
     'votes': ['positive'], 'verdict_s': 10400}]})


def test_a_reading_adds_the_games_the_title_doesnt_name():
    ep = _soj_episode()
    for _ in range(2):                      # a rebuild replaces, never piles up
        feeds._apply_readings([ep], {'soj-16': _S17E16})
    assert [(g.name, g.timestamp_seconds, g.read, g.critique['verdict']) for g in ep.games] == [
        ('Karmazoo', 9294, False, 'positive'),                 # the title's, with its verdict
        ('Goldorak : Le Festin des Loups', 3755, True, 'negative')]   # not the 43-s aside


def test_what_a_reading_added_goes_when_it_does():
    ep = _soj_episode()
    feeds._apply_readings([ep], {'soj-16': _S17E16})
    feeds._apply_readings([ep], {})
    assert [(g.name, g.critique) for g in ep.games] == [('Karmazoo', None)]


def test_ads_are_not_chapters():
    from models import Episode
    ep = Episode(title='t', slug='bes-1', audio_url=None, pub_ts=None, image_url=None,
                 description='', chapters=[], games=[], podcast_id='the-besties')
    sections = llm._sections({'sections': [
        {'title': 'Welcome', 'game': None, 'start_s': 0, 'end_s': 300},
        {'title': 'Ad break', 'game': None, 'ad': True, 'start_s': 300, 'end_s': 380},
        {'title': 'Mail', 'game': None, 'start_s': 380, 'end_s': 900}]})
    feeds._apply_readings([ep], {'bes-1': sections})
    assert [c.title for c in ep.chapters] == ['Welcome', 'Mail']
