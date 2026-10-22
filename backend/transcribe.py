"""Transcribing an episode (Whisper on DeepInfra), and the `transcripts` table.

Off when `DEEPINFRA_API_KEY` is unset. An episode is transcribed once: its
transcript is kept under its guid and never asked for again — a new prompt
re-reads it (`llm.read_transcript`), it doesn't re-transcribe it.

The audio goes through the server: DeepInfra takes a file, not a URL (its JSON
`audio` field is base64). Prod has little memory to spare and a long episode is
180 MB, so the audio is streamed to a temporary file and from it, never held
whole. No Whisper `initial_prompt`: with one, DeepInfra dropped 60 % of an
episode's words; names are fixed when the transcript is read.
"""
import io
import json
import logging
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

_http = requests.Session()


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

    def __init__(self, fields: dict[str, str], file):
        boundary = uuid.uuid4().hex
        self.content_type = f'multipart/form-data; boundary={boundary}'
        head = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                       f'{value}\r\n' for name, value in fields.items())
        head += (f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; '
                 f'filename="audio"\r\nContent-Type: application/octet-stream\r\n\r\n')
        tail = f'\r\n--{boundary}--\r\n'
        self._parts = [io.BytesIO(head.encode()), file, io.BytesIO(tail.encode())]
        self._length = len(head.encode()) + os.fstat(file.fileno()).st_size + len(tail)

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
        audio.seek(0)
        body = _Multipart({'language': language, 'chunk_level': 'segment'}, audio)
        try:
            resp = _http.post(_API + Config.TRANSCRIBE_MODEL, data=body, timeout=_TIMEOUT, headers={
                'Authorization': f'Bearer {Config.DEEPINFRA_API_KEY}',
                'Content-Type':  body.content_type,
            })
            resp.raise_for_status()
            answer = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise Unavailable(f'DeepInfra: {exc}') from exc
    segments = [[round(s['start'], 2), round(s['end'], 2), s['text'].strip()]
                for s in answer.get('segments') or [] if s.get('text', '').strip()]
    if not segments:
        raise ValueError('no speech in the transcript')
    return Transcript(model=Config.TRANSCRIBE_MODEL, segments=segments,
                      duration=float(answer.get('duration') or segments[-1][1]),
                      cost=(answer.get('inference_status') or {}).get('cost'))


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
