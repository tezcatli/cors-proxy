import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  extractGameNamesFromTitle,
  extractChapters,
  isNonGameChapter,
  findTimestampForGame,
  parseFeed,
} from '../src/lib/rss.js';

// ── extractGameNamesFromTitle ─────────────────────────────────────────────

describe('extractGameNamesFromTitle', () => {
  it('extracts one game', () => {
    expect(extractGameNamesFromTitle('On a joué à «Zelda»')).toEqual(['Zelda']);
  });
  it('extracts multiple games', () => {
    expect(extractGameNamesFromTitle('«Mario» et «Zelda»')).toEqual(['Mario', 'Zelda']);
  });
  it('returns empty array when no guillemets', () => {
    expect(extractGameNamesFromTitle('Juste un titre')).toEqual([]);
  });
  it('returns empty array for falsy input', () => {
    expect(extractGameNamesFromTitle(null)).toEqual([]);
    expect(extractGameNamesFromTitle('')).toEqual([]);
  });
  it('trims game names', () => {
    expect(extractGameNamesFromTitle('«  Zelda  »')).toEqual(['Zelda']);
  });
  it('ignores single-character matches', () => {
    const result = extractGameNamesFromTitle('«A» et «Zelda»');
    expect(result).not.toContain('A');
    expect(result).toContain('Zelda');
  });
});

// ── extractChapters ───────────────────────────────────────────────────────

describe('extractChapters', () => {
  it('parses MM:SS timestamp lines', () => {
    const text = '00:30 Zelda\n01:00 Mario';
    const chapters = extractChapters(text);
    expect(chapters).toHaveLength(2);
    expect(chapters[0]).toEqual({ timestampSeconds: 30, timestamp: '00:30', title: 'Zelda' });
    expect(chapters[1]).toEqual({ timestampSeconds: 60, timestamp: '01:00', title: 'Mario' });
  });
  it('parses HH:MM:SS timestamp lines', () => {
    const chapters = extractChapters('1:00:00 Some Game');
    expect(chapters[0].timestampSeconds).toBe(3600);
  });
  it('ignores lines without a timestamp', () => {
    const chapters = extractChapters('Just some text\n00:30 Zelda');
    expect(chapters).toHaveLength(1);
  });
  it('returns empty array for empty text', () => {
    expect(extractChapters('')).toEqual([]);
  });
});

// ── isNonGameChapter ──────────────────────────────────────────────────────

describe('isNonGameChapter', () => {
  it.each([
    'intro', 'Intro', 'INTRO',
    'les news', 'Le News',
    'com des coms',
    'outro', 'Outro',
    'générique',
    'bande-annonce', 'bande annonce',
  ])('"%s" is a non-game chapter', title => {
    expect(isNonGameChapter(title)).toBe(true);
  });
  it.each([
    'Zelda',
    'Mario Kart 8',
    'Hollow Knight',
  ])('"%s" is not a non-game chapter', title => {
    expect(isNonGameChapter(title)).toBe(false);
  });
});

// ── findTimestampForGame ──────────────────────────────────────────────────

describe('findTimestampForGame', () => {
  const chapters = [
    { timestampSeconds: 30,  timestamp: '00:30', title: 'Intro' },
    { timestampSeconds: 90,  timestamp: '01:30', title: 'Zelda Breath of the Wild' },
    { timestampSeconds: 180, timestamp: '03:00', title: 'Mario Kart' },
    { timestampSeconds: 270, timestamp: '04:30', title: 'Outro' },
  ];

  it('finds an exact match (ignoring non-game chapters)', () => {
    const ts = findTimestampForGame('Mario Kart', chapters);
    expect(ts).toEqual({ timestamp: '03:00', timestampSeconds: 180 });
  });
  it('finds a partial match by word overlap', () => {
    const ts = findTimestampForGame('Zelda', chapters);
    expect(ts).not.toBeNull();
    expect(ts.timestamp).toBe('01:30');
  });
  it('returns null when no match above threshold', () => {
    expect(findTimestampForGame('Halo', chapters)).toBeNull();
  });
  it('skips non-game chapters (Intro, Outro)', () => {
    const ts = findTimestampForGame('Intro', chapters);
    expect(ts).toBeNull();
  });
});

// ── parseFeed (integration) ───────────────────────────────────────────────

const MINIMAL_RSS = `<rss version="2.0"><channel>
  <item>
    <title>On a joué à «Zelda» et «Mario Kart»</title>
    <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 15 Jan 2024 00:00:00 +0000</pubDate>
    <description>00:30 Zelda
01:00 Mario Kart
01:30 Outro</description>
  </item>
  <item>
    <title>Quelle est la meilleure plateforme ?</title>
    <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="0" />
    <pubDate>Mon, 08 Jan 2024 00:00:00 +0000</pubDate>
    <description>No games here</description>
  </item>
</channel></rss>`;

describe('parseFeed', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(MINIMAL_RSS),
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('returns one entry per unique game name', async () => {
    const games = await parseFeed();
    const names = games.map(g => g.name);
    expect(names).toContain('Zelda');
    expect(names).toContain('Mario Kart');
  });
  it('filters out non-game episodes (Quelle…)', async () => {
    const games = await parseFeed();
    expect(games).toHaveLength(2);
  });
  it('sets the audio URL', async () => {
    const games = await parseFeed();
    const zelda = games.find(g => g.name === 'Zelda');
    expect(zelda.episodes[0].audioUrl).toBe('https://example.com/ep1.mp3');
  });
  it('resolves timestamps from chapter list', async () => {
    const games = await parseFeed();
    const zelda = games.find(g => g.name === 'Zelda');
    expect(zelda.episodes[0].timestamp).toBe('00:30');
    expect(zelda.episodes[0].timestampSeconds).toBe(30);
  });
  it('sorts games alphabetically', async () => {
    const games = await parseFeed();
    expect(games[0].name.localeCompare(games[1].name, 'fr', { sensitivity: 'base' })).toBeLessThanOrEqual(0);
  });
});
