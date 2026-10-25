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
     'kind': 'review', 'votes': ['positive', 'enthusiastic', 'mixed'], 'pros': ['Surreal Manhattan'],
     'cons': ['Slow start'], 'verdict_s': 1800},
    {'title': 'Gears of War: E-DAY', 'game': 'Gears of War: E-DAY', 'start_s': 1860,
     'end_s': 2750, 'kind': 'review', 'votes': ['positive'], 'pros': ['Beautiful'], 'cons': [], 'verdict_s': 2000},
    {'title': 'A Normal Golf Game', 'game': 'A Normal Golf Game', 'start_s': 2750,
     'end_s': 2840, 'kind': 'mention'}]}                   # named in passing
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
    answer = MagicMock(status_code=200)
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
    (['enthusiastic', 'positive', 'negative', 'positive'], 'mixed'),      # 1.5: a tie
    (['positive', 'negative'], 'mixed'),                                  # 1.0
    (['mixed', 'negative'], 'mixed'),            # 0.5: a split goes to «mixed»
    (['positive', 'enthusiastic'], 'positive'),  # «enthusiastic» is shown as «positive»
    (['enthusiastic', 'enthusiastic', 'mixed'], 'positive'),             # 1.67
    (['negative'], 'negative'),
    (['Patrick: mixed', 'Marius: Negative'], 'mixed'),   # a host's name is dropped
    (['great', 'meh'], None),                    # not on the scale
    ([], None),
])
def test_the_verdict_is_the_hosts_average(votes, expected):
    assert llm.verdict(votes) == expected


def test_a_game_section_is_described_whatever_its_kind():
    sections = llm._sections({'sections': [
        {'title': 'News', 'game': 'GTA VI', 'kind': 'news', 'start_s': 600, 'end_s': 1200,
         'votes': ['negative'], 'verdict_s': 700},
        {'title': 'Still playing', 'game': 'Saros', 'kind': 'impressions', 'start_s': 1200,
         'end_s': 2000, 'votes': [], 'pros': ['Tight combat'], 'verdict_s': 1900},
        {'title': 'Odd', 'game': 'Halo', 'kind': 'rumour', 'start_s': 2000, 'end_s': 2100},
        {'title': 'Intro', 'game': None, 'kind': 'review', 'start_s': 0, 'end_s': 600},
        {'title': 'Broken', 'start_s': 'x', 'end_s': 1},
    ]})
    assert [(s['title'], s['kind'], s['opinion'] and s['opinion']['verdict']) for s in sections] == [
        ('Intro', None, None),                     # not a game: no kind, no opinion
        ('News', 'news', 'negative'),
        ('Still playing', 'impressions', None),    # no one concludes
        ('Odd', 'mention', None)]                  # a kind off the list is a mention


@pytest.mark.parametrize('kind, listed', [
    ('review', True), ('impressions', True), ('ranking', True),
    ('news', False), ('recommendation', False), ('mention', False)])
def test_the_catalog_lists_the_games_its_hosts_critique(kind, listed):
    sections = llm._sections({'sections': [
        {'title': 'x', 'game': 'Fire Emblem Awakening', 'kind': kind, 'start_s': 3000,
         'end_s': 3060, 'votes': ['enthusiastic']}]})
    assert feeds._read_games(sections) == (['Fire Emblem Awakening'] if listed else [])


def test_pros_and_cons_are_kept_to_three():
    [section] = llm._sections({'sections': [
        {'title': 'Saros', 'game': 'Saros', 'start_s': 0, 'end_s': 900, 'kind': 'review',
         'votes': ['positive'],
         'pros': ['a', 'b', 'c', 'd'], 'cons': ['', 'e'], 'verdict_s': 850}]})
    assert section['opinion'] == {'verdict': 'positive', 'pros': ['a', 'b', 'c'],
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



# ── Sending a big episode in parts ────────────────────────────────────────────

# MPEG-1 layer III, 44.1 kHz: 128 kbps frames are 417 bytes, 192 kbps 626; each
# holds 1152 samples (26.1 ms). Their bodies are zeros: no false frame sync.
_F128, _F192, _FRAME_S = b'\xff\xfb\x90\x00' + bytes(413), b'\xff\xfb\xb0\x00' + bytes(622), 1152 / 44100


def _id3_tag(size=200):
    """An ID3v2 tag of `size` bytes, its body full of 0xFF (a cover) that must not
    be taken for frames."""
    n = size - 10
    return b'ID3\x03\x00\x00' + bytes([n >> 21 & 127, n >> 14 & 127, n >> 7 & 127, n & 127]) + b'\xff' * n


@contextlib.contextmanager
def _parted(audio: bytes, monkeypatch, part_bytes=10_000, whole_bytes=20_000):
    """Mock the download of `audio` and DeepInfra answering each part with one
    segment at 1 s, as long as it is; yields the parts sent."""
    monkeypatch.setattr(transcribe, '_PART_BYTES', part_bytes)
    monkeypatch.setattr(transcribe, '_WHOLE_BYTES', whole_bytes)
    download = MagicMock()
    download.__enter__.return_value = download
    download.iter_content.return_value = [audio]
    sent = []

    def upload(*_a, data=None, **_kw):
        body = data.read()
        part = body[body.index(b'octet-stream\r\n\r\n') + 16:body.rindex(b'\r\n--')]
        sent.append(part)
        seconds = len(list(transcribe._frames(part))) * _FRAME_S
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'segments': [{'start': 1.0, 'end': 2.0, 'text': f' part {len(sent)}'}],
                                    'duration': seconds, 'inference_status': {'cost': 0.01}}
        return answer
    with patch('transcribe._http.get', return_value=download), \
         patch('transcribe._http.post', side_effect=upload):
        yield sent


def test_a_small_episode_is_sent_whole(keys, monkeypatch):
    audio = _id3_tag() + _F128 * 40
    with _parted(audio, monkeypatch) as sent:
        transcribe.transcribe('https://example.com/a.mp3', 'fr')
    assert sent == [audio]


def test_a_big_episode_is_sent_in_equal_parts_cut_between_frames(keys, monkeypatch):
    audio = _id3_tag() + _F128 * 100                       # 41 900 bytes of audio
    with _parted(audio, monkeypatch) as sent:
        t = transcribe.transcribe('https://example.com/a.mp3', 'fr')
    assert [len(p) // len(_F128) for p in sent] == [20, 20, 20, 20, 20]
    assert b''.join(sent) == _F128 * 100                   # every frame once, the tag in none
    starts = [s[0] for s in t.segments]                    # shifted by the frames before
    assert starts == [round(1 + 20 * k * _FRAME_S, 2) for k in range(5)]
    assert t.duration == pytest.approx(100 * _FRAME_S)
    assert t.cost == pytest.approx(0.05)


def test_the_shift_counts_frames_not_bytes(keys, monkeypatch):
    # Variable bitrate: the first half's frames are bigger, the parts' timecodes
    # still follow the frames' durations.
    audio = _F192 * 30 + _F128 * 30
    with _parted(audio, monkeypatch, part_bytes=15_000, whole_bytes=10_000) as sent:
        t = transcribe.transcribe('https://example.com/a.mp3', 'fr')
    frames = [len(list(transcribe._frames(p))) for p in sent]
    assert sum(frames) == 60 and len(set(frames)) == 1
    assert [s[0] for s in t.segments] == [round(1 + k * frames[0] * _FRAME_S, 2) for k in range(len(sent))]


def test_what_is_not_a_frame_is_skipped_and_takes_no_time():
    # An ID3 tag mid-file, bytes an ad insertion left, a Xing header first.
    xing = b'\xff\xfb\x90\x00' + bytes(32) + b'Xing' + bytes(377)
    audio = _id3_tag() + xing + _F128 * 10 + _id3_tag(500) + b'\x12\xff\x34' * 300 + _F128 * 10 + b'TAG' + bytes(125)
    frames = list(transcribe._frames(audio))
    assert len(frames) == 20 and sum(s for _, s in frames) == pytest.approx(20 * _FRAME_S)
    assert frames[0][0] == 200 + len(xing)                 # the tag and the Xing header aren't audio


def test_what_isnt_an_mp3_is_sent_whole(keys, monkeypatch):
    audio = b'\x00\x00\x00\x20ftypM4A ' + bytes(30_000)
    with _parted(audio, monkeypatch) as sent:
        transcribe.transcribe('https://example.com/a.m4a', 'fr')
    assert sent == [audio]                                 # DeepInfra says whether it takes it
    assert transcribe._parts(audio) is None


def test_a_part_refused_fails_the_whole_episode(keys, monkeypatch):
    import requests
    monkeypatch.setattr(transcribe, '_PART_BYTES', 10_000)
    monkeypatch.setattr(transcribe, '_WHOLE_BYTES', 20_000)
    download = MagicMock()
    download.__enter__.return_value = download
    download.iter_content.return_value = [_F128 * 100]
    ok = MagicMock(status_code=200)
    ok.json.return_value = {'segments': [{'start': 0, 'end': 1, 'text': 'a'}], 'duration': 1}
    refused = MagicMock(status_code=400, text='{"detail":"Invalid or unsupported audio file."}')
    refused.raise_for_status.side_effect = requests.HTTPError('400 Client Error')
    with patch('transcribe._http.get', return_value=download), \
         patch('transcribe._http.post', side_effect=[ok, refused, ok, ok, ok]), \
         pytest.raises(requests.HTTPError):
        transcribe.transcribe('https://example.com/a.mp3', 'fr')

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
        ('Control Resonant', 240), ('Gears of War: E-DAY', 1860)]   # not the golf game named in passing
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
         'end_s': 3338, 'kind': 'review', 'votes': ['positive'], 'verdict_s': 3097}]})
    feeds._apply_readings([ep], {'soj-1': sections})
    assert [c.title for c in ep.chapters] == ['Super Mario RPG']
    assert ep.games[0].critique['verdict'] == 'positive'
    # A test starts where its critique does — the reading's section, not the chapter.
    assert (ep.games[0].timestamp_seconds, ep.games[0].critique['at']) == (2227, 3097)


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
     'end_s': 5057, 'kind': 'review', 'votes': ['negative'], 'verdict_s': 4900},
    {'title': 'GTA VI trailer', 'game': 'GTA VI', 'start_s': 5057, 'end_s': 5600,
     'kind': 'news', 'votes': ['negative']},
    {'title': 'KarmaZoo', 'game': 'KarmaZoo', 'start_s': 9365, 'end_s': 10629,
     'kind': 'review', 'votes': ['positive'], 'verdict_s': 10400}]})


def test_a_reading_adds_the_games_the_title_doesnt_name():
    ep = _soj_episode()
    for _ in range(2):                      # a rebuild replaces, never piles up
        feeds._apply_readings([ep], {'soj-16': _S17E16})
    assert [(g.name, g.timestamp_seconds, g.read, g.critique['verdict']) for g in ep.games] == [
        ('Karmazoo', 9365, False, 'positive'),                 # the title's, from its critique
        ('Goldorak : Le Festin des Loups', 3755, True, 'negative')]   # not the trailer in the news


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


# ── DeepInfra failing ─────────────────────────────────────────────────────────

@pytest.fixture
def no_pause(monkeypatch):
    monkeypatch.setattr(ingest, '_failures', 0)
    monkeypatch.setattr(ingest, '_paused_until', 0.0)


def _deepinfra_refuses(status=402):
    import requests
    audio = MagicMock()
    audio.__enter__.return_value = audio
    audio.iter_content.return_value = [b'audio']
    refused = MagicMock(status_code=status, text='refused')
    refused.raise_for_status.side_effect = requests.HTTPError(f'{status} Client Error')
    return patch('transcribe._http.get', return_value=audio), \
        patch('transcribe._http.post', return_value=refused)


def test_deepinfra_failing_pauses_the_ingestion_not_the_episode(keys, besties, no_pause):
    get, post = _deepinfra_refuses()
    with get as download, post:
        assert ingest._step(lambda: None) > 0
        assert ingest._step(lambda: None) > 0           # paused: nothing more is tried
    assert download.call_count == 1                     # not one download per episode
    assert transcribe.rows() == {}                      # no episode is blamed
    assert [ep.slug for ep in ingest.pending()] == ['bes-control', 'bes-mail']


def test_the_pause_grows_while_deepinfra_keeps_failing(keys, besties, no_pause):
    get, post = _deepinfra_refuses()
    with get, post:
        first = ingest._step(lambda: None)
        ingest._paused_until = 0.0                      # the pause is over
        second = ingest._step(lambda: None)
    assert second == pytest.approx(2 * first)


def test_the_ingestion_resumes_once_deepinfra_answers(keys, besties, no_pause):
    get, post = _deepinfra_refuses()
    with get, post:
        ingest._step(lambda: None)
    ingest._paused_until = 0.0
    read = []
    with _deepinfra(), _reads({'Control Resonant Rewards Your Patience': _CONTROL}):
        assert ingest._step(lambda: read.append(1)) == 0
    assert read == [1] and ingest._failures == 0


def test_a_missing_episode_is_blamed_on_the_episode(keys, besties, no_pause):
    with patch('transcribe._http.get', side_effect=OSError('404')):
        assert ingest._step(lambda: None) == 0         # on to the next one
    assert transcribe.rows()['bes-control'].attempts == 1


# ── The backlog, transcribed from dev ─────────────────────────────────────────

def test_the_backlog_is_the_untranscribed_episodes_oldest_first(keys, besties):
    with _deepinfra():
        ingest.ingest(_episode('bes-control'))
    assert [ep.slug for ep in ingest.untranscribed()] == ['bes-mail']
    with get_db() as conn:
        conn.execute('DELETE FROM transcripts')
    assert [ep.slug for ep in ingest.untranscribed()] == ['bes-mail', 'bes-control']


def test_transcribing_the_backlog_skips_what_is_done_and_reads_nothing(keys, besties):
    with _deepinfra() as (_, post, _), patch('llm.http.post') as read:
        assert ingest.transcribe_all(ingest.untranscribed(), jobs=2)[0] == 2
        assert ingest.transcribe_all(ingest.untranscribed() + [_episode('bes-mail')], jobs=2)[0] == 0
    assert post.call_count == 2
    read.assert_not_called()


def test_deepinfra_failing_stops_the_backlog(keys, besties):
    get, post = _deepinfra_refuses()
    with get, post as upload:
        assert ingest.transcribe_all(ingest.untranscribed(), jobs=1)[0] == 0
    assert upload.call_count == 1                 # not one try per episode
    assert transcribe.rows() == {}                # no episode blamed


def test_a_file_deepinfra_cannot_read_is_the_episode_s_failure(keys, besties, no_pause):
    get, post = _deepinfra_refuses(400)
    with get, post:
        assert ingest._step(lambda: None) == 0           # on to the next episode, no pause
    assert transcribe.rows()['bes-control'].attempts == 1
    with get, post as upload:
        assert ingest.transcribe_all(ingest.untranscribed(), jobs=1)[0] == 0
    assert upload.call_count == 2                        # both tried: one bad file stops nothing


@pytest.mark.parametrize('status', [401, 402, 429, 503])
def test_deepinfra_refusing_us_is_the_provider_s_failure(keys, besties, no_pause, status):
    get, post = _deepinfra_refuses(status)
    with get, post:
        assert ingest._step(lambda: None) > 0             # paused
    assert transcribe.rows() == {}
