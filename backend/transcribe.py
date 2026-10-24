"""Transcribing an episode (Whisper on DeepInfra), and the `transcripts` table.

Off when `DEEPINFRA_API_KEY` is unset. An episode is transcribed once: its
transcript is kept under its guid and never asked for again — a new prompt
re-reads it (`llm.read_transcript`), it doesn't re-transcribe it.

The audio goes through the server: DeepInfra takes a file, not a URL (its JSON
`audio` field is base64). Prod has little memory to spare and a long episode is
180 MB, so the audio is streamed to a temporary file and from it, never held
whole. DeepInfra refuses a file over 200 MiB ("Maximum file size exceeded"), and
answered a 199 MiB one with a 500: a bigger episode is sent in parts (`_parts`),
cut between MP3 frames, each part's timecodes shifted by the duration of the
frames before it — counted, not taken from DeepInfra or a header. No Whisper `initial_prompt`: with one, DeepInfra dropped 60 % of an
episode's words; names are fixed when the transcript is read.

Not sped up, deliberately: DeepInfra bills the duration sent, and at ×1.5 an
episode kept 99 % of its words and read the same for a third less — but that is
~6 $ once and ~1.5 $ a year, against ffmpeg in the image and a CPU minute per
episode on a shared 2-vCPU host (at ×2, 10 % of the words were lost).
"""
import io
import json
import logging
import math
import mmap
import os
import tempfile
import uuid
from dataclasses import dataclass

import requests

from config import Config
from db import get_db, utcnow
from models import Episode
from podcasts import PODCAST_BY_ID
from utils import backoff, plain_text

logger = logging.getLogger(__name__)

_API       = 'https://api.deepinfra.com/v1/inference/'
_CHUNK     = 1 << 20
_MAX_BYTES = 600 << 20       # ~10 h of podcast audio: anything bigger isn't an episode
# (connect, read). The first also bounds every socket write of the upload, not just
# the connect: at 10 s, DeepInfra pausing its reads for a moment in a 180 MB upload
# aborted it ("The write operation timed out"), every half hour in prod. The read
# covers the transcription itself: a 3-hour episode takes ~90 s.
_TIMEOUT   = (60, 900)
# Above `_WHOLE_BYTES` an episode is sent in equal parts of at most `_PART_BYTES`
# and `_PART_SECONDS` — well inside what DeepInfra has taken whole (3.6 h).
_WHOLE_BYTES  = 190 << 20
_PART_BYTES   = 100 << 20
_PART_SECONDS = 2 * 3600

_http = requests.Session()

# DeepInfra itself is failing: a key refused, out of credit, a quota — or a 5xx.
_PROVIDER_DOWN = {401, 402, 403, 429}


def enabled() -> bool:
    return bool(Config.DEEPINFRA_API_KEY)


class Unavailable(Exception):
    """DeepInfra failed the transcription: the provider is at fault — no credit
    left, a key refused, an outage — not the episode."""


@dataclass
class Transcript:
    model:    str
    segments: list           # [[start_s, end_s, text]]
    duration: float          # seconds of audio
    cost:     float | None   # USD, as DeepInfra billed it


# ── Transcribing ──────────────────────────────────────────────────────────────

class _Multipart:
    """A multipart/form-data body that reads its file part as it is sent.
    `requests` sends an object with `read` and a length as is, under its
    Content-Length, rather than building the whole body in memory."""

    def __init__(self, fields: dict[str, str], file, size: int | None = None):
        boundary = uuid.uuid4().hex
        self.content_type = f'multipart/form-data; boundary={boundary}'
        head = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                       f'{value}\r\n' for name, value in fields.items())
        head += (f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; '
                 f'filename="audio"\r\nContent-Type: application/octet-stream\r\n\r\n')
        tail = f'\r\n--{boundary}--\r\n'
        self._parts = [io.BytesIO(head.encode()), file, io.BytesIO(tail.encode())]
        if size is None:
            size = os.fstat(file.fileno()).st_size
        self._length = len(head.encode()) + size + len(tail)

    def __len__(self) -> int:
        return self._length

    def read(self, size: int = -1) -> bytes:
        out = b''
        while self._parts and (size < 0 or len(out) < size):
            chunk = self._parts[0].read(-1 if size < 0 else size - len(out))
            if chunk:
                out += chunk
            else:
                self._parts.pop(0)
        return out


class _Range:
    """`size` bytes of `file` from `start`, read as a file."""

    def __init__(self, file, start: int, size: int):
        self._file, self._pos, self._left = file, start, size

    def read(self, size: int = -1) -> bytes:
        self._file.seek(self._pos)
        out = self._file.read(self._left if size < 0 else min(size, self._left))
        self._pos += len(out)
        self._left -= len(out)
        return out


# MPEG audio layer III: (MPEG-1?) → kbps by index; version → sample rates.
_KBPS  = {True:  (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0),
          False: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)}
_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def _frame(buf, pos: int) -> tuple[int, float] | None:
    """(length in bytes, seconds) of the layer III frame whose header is at `pos`."""
    if pos + 4 > len(buf) or buf[pos] != 0xFF or buf[pos + 1] & 0xE0 != 0xE0:
        return None
    version, layer = buf[pos + 1] >> 3 & 3, buf[pos + 1] >> 1 & 3
    kbps_index, rate_index, padding = buf[pos + 2] >> 4, buf[pos + 2] >> 2 & 3, buf[pos + 2] >> 1 & 1
    if version == 1 or layer != 1 or rate_index == 3:
        return None
    kbps, rate = _KBPS[version == 3][kbps_index], _RATES[version][rate_index]
    if not kbps:                                    # free format or invalid
        return None
    samples = 1152 if version == 3 else 576
    return samples // 8 * kbps * 1000 // rate + padding, samples / rate


def _id3(buf, pos: int) -> int:
    """The length of the ID3v2 tag at `pos`, 0 if there is none."""
    if buf[pos:pos + 3] != b'ID3' or pos + 10 > len(buf):
        return 0
    s = buf[pos + 6:pos + 10]
    return 10 + (s[0] << 21 | s[1] << 14 | s[2] << 7 | s[3]) + (10 if buf[pos + 5] & 0x10 else 0)


def _frames(buf):
    """(offset, seconds) of each audio frame. A header counts only when the next
    frame's (or a tag, or the file's end) follows it, so a 0xFF in a tag or a cover isn't
    taken for one; anything else — an ID3 tag mid-file, bytes an ad insertion
    left — is skipped to the next frame. The Xing/Info/VBRI frame, a header
    holding no audio that decoders skip, isn't one."""
    pos, first = _id3(buf, 0), True
    while pos + 4 <= len(buf):
        frame = _frame(buf, pos)
        after = pos + frame[0] if frame else 0
        if frame and (after + 4 > len(buf) or _frame(buf, after) or buf[after:after + 3] in (b'ID3', b'TAG')):
            if not (first and any(tag in buf[pos + 4:pos + 40] for tag in (b'Xing', b'Info', b'VBRI'))):
                yield pos, frame[1]
            first = False
            pos += frame[0]
        elif tag := _id3(buf, pos):
            pos += tag
        else:
            pos = buf.find(b'\xff', pos + 1)
            if pos < 0:
                return


def _parts(buf) -> list[tuple[int, int, float]] | None:
    """The parts to send of an MP3 too big to send whole: (start, end, seconds
    before it), equal in duration, cut between frames. None when it isn't an MP3."""
    frames, seconds = 0, 0.0
    for _, length in _frames(buf):
        frames, seconds = frames + 1, seconds + length
    if not frames:
        return None
    end = len(buf)
    count = max(math.ceil((end - _id3(buf, 0)) / _PART_BYTES), math.ceil(seconds / _PART_SECONDS))
    parts, at = [], 0.0
    for offset, length in _frames(buf):
        # A part starts at the frame nearest its share of the duration.
        if not parts or (len(parts) < count and at + length / 2 > seconds * len(parts) / count):
            parts.append([offset, None, at])
        at += length
    for part, after in zip(parts, parts[1:]):
        part[1] = after[0]
    parts[-1][1] = end
    return [tuple(p) for p in parts]


def _send(audio, start: int, size: int, language: str) -> dict:
    """DeepInfra's answer for `size` bytes of `audio` from `start`."""
    body = _Multipart({'language': language, 'chunk_level': 'segment'},
                      _Range(audio, start, size), size)
    try:
        resp = _http.post(_API + Config.TRANSCRIBE_MODEL, data=body, timeout=_TIMEOUT, headers={
            'Authorization': f'Bearer {Config.DEEPINFRA_API_KEY}',
            'Content-Type':  body.content_type,
        })
    except requests.RequestException as exc:
        raise Unavailable(f'DeepInfra: {exc}') from exc
    if resp.status_code in _PROVIDER_DOWN or resp.status_code >= 500:
        raise Unavailable(f'DeepInfra: HTTP {resp.status_code} {resp.text[:200]}')
    # Any other refusal is about this file (400: not audio it can read; 413: too
    # big): the episode's failure, not the provider's — the others go on.
    if resp.status_code >= 400:
        logger.warning('DeepInfra refused the audio: HTTP %s %s', resp.status_code, resp.text[:200])
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as exc:
        raise Unavailable(f'DeepInfra: unreadable answer: {exc}') from exc


def transcribe(audio_url: str, language: str) -> Transcript:
    """Download the episode's audio and transcribe it. Raises `Unavailable` when
    DeepInfra fails, anything else when the episode does (its audio missing,
    no speech in it)."""
    with tempfile.TemporaryFile() as audio:
        with _http.get(audio_url, stream=True, timeout=Config.REQUEST_TIMEOUT,
                      headers={'User-Agent': 'PodcastCatalog/1.0'}) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(_CHUNK):
                audio.write(chunk)
                if audio.tell() > _MAX_BYTES:
                    raise ValueError(f'audio over {_MAX_BYTES >> 20} MB')
        size = audio.tell()
        parts = None
        if size > _WHOLE_BYTES:
            audio.flush()                       # what is still buffered, for the map
            with mmap.mmap(audio.fileno(), 0, access=mmap.ACCESS_READ) as buf:
                parts = _parts(buf)
        # Not an MP3: sent whole, DeepInfra says whether it takes it.
        parts = parts or [(0, size, 0.0)]
        answers = [(_send(audio, start, end - start, language), offset)
                   for start, end, offset in parts]
    segments = [[round(s['start'] + offset, 2), round(s['end'] + offset, 2), s['text'].strip()]
                for answer, offset in answers
                for s in answer.get('segments') or [] if s.get('text', '').strip()]
    if not segments:
        raise ValueError('no speech in the transcript')
    last, offset = answers[-1]
    costs = [c for answer, _ in answers if (c := (answer.get('inference_status') or {}).get('cost')) is not None]
    return Transcript(model=Config.TRANSCRIBE_MODEL, segments=segments,
                      duration=offset + float(last.get('duration') or segments[-1][1] - offset),
                      cost=sum(costs) if costs else None)


def reading_input(episode: Episode, model: str) -> dict:
    """What identifies the LLM's reading of an episode's transcript
    (`llm.read_transcript`): the transcript by its episode and model, plus the
    context it is read with — so an edited description is read again."""
    podcast = PODCAST_BY_ID[episode.podcast_id]
    return {'show': podcast.name, 'language': podcast.language, 'guid': episode.slug,
            'transcript': model, 'title': episode.title,
            'description': plain_text(episode.description)[:4000]}


# ── The table ─────────────────────────────────────────────────────────────────

@dataclass
class Row:
    guid:       str
    model:      str | None   # None until transcribed
    attempts:   int
    last_error: str | None
    retry_at:   str | None   # ISO-8601 UTC; None = not failing


def rows() -> dict[str, Row]:
    """Every episode the ingestion has tried, without its (large) transcript."""
    with get_db() as conn:
        return {r['guid']: Row(r['guid'], r['model'] if r['transcribed'] else None,
                               r['attempts'], r['last_error'], r['retry_at'])
                for r in conn.execute('SELECT guid, model, segments IS NOT NULL AS transcribed, '
                                      'attempts, last_error, retry_at FROM transcripts')}


def load(guid: str) -> Transcript | None:
    with get_db() as conn:
        row = conn.execute('SELECT model, segments, duration, cost FROM transcripts '
                           'WHERE guid = ? AND segments IS NOT NULL', (guid,)).fetchone()
    return Transcript(row['model'], json.loads(row['segments']), row['duration'],
                      row['cost']) if row else None


def store(guid: str, transcript: Transcript) -> None:
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO transcripts (guid, model, segments, duration, cost, created_at) '
            'VALUES (?,?,?,?,?,?)',
            (guid, transcript.model, json.dumps(transcript.segments, ensure_ascii=False),
             transcript.duration, transcript.cost, utcnow().isoformat()))


def store_failure(guid: str, error: str) -> None:
    """Record a failed step — transcribing or reading — so the episode waits out a
    growing delay instead of being retried at once, keeping any transcript."""
    with get_db() as conn:
        row = conn.execute('SELECT attempts FROM transcripts WHERE guid = ?', (guid,)).fetchone()
        attempts = (row['attempts'] if row else 0) + 1
        retry_at = (utcnow() + backoff(attempts)).isoformat()
        conn.execute(
            'INSERT INTO transcripts (guid, attempts, last_error, retry_at) VALUES (?,?,?,?) '
            'ON CONFLICT(guid) DO UPDATE SET attempts = excluded.attempts, '
            'last_error = excluded.last_error, retry_at = excluded.retry_at',
            (guid, attempts, error[:500], retry_at))
    logger.info('Ingestion of %s failed %d time(s) in a row: %s', guid, attempts, error[:200])


def clear_failure(guid: str) -> None:
    with get_db() as conn:
        conn.execute('UPDATE transcripts SET attempts = 0, last_error = NULL, retry_at = NULL '
                     'WHERE guid = ?', (guid,))


def totals() -> dict:
    """Hours transcribed and what they cost, all shows together."""
    with get_db() as conn:
        row = conn.execute('SELECT COALESCE(SUM(duration), 0) AS seconds, '
                           'COALESCE(SUM(cost), 0) AS cost FROM transcripts').fetchone()
    return {'hours': round(row['seconds'] / 3600, 1), 'cost': round(row['cost'], 2)}
