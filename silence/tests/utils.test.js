import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  stripHtml, timestampToSeconds, normalizeForMatch,
  formatDate, timeAgo, escHtml, latestDate, getScoreClass,
} from '../js/utils.js';

// ── stripHtml ──────────────────────────────────────────────────────────────

describe('stripHtml', () => {
  it('returns empty string for falsy input', () => {
    expect(stripHtml('')).toBe('');
    expect(stripHtml(null)).toBe('');
  });
  it('removes HTML tags', () => {
    expect(stripHtml('<b>hello</b>')).toBe('hello');
    expect(stripHtml('<div><p>text</p></div>')).toBe('text');
  });
  it('converts </p> and <br> to newlines', () => {
    const result = stripHtml('line1<br>line2</p>line3');
    expect(result).toContain('\n');
  });
  it('decodes common HTML entities', () => {
    expect(stripHtml('a &amp; b')).toBe('a & b');
    expect(stripHtml('&lt;tag&gt;')).toBe('<tag>');
    expect(stripHtml('say &quot;hi&quot;')).toBe('say "hi"');
    expect(stripHtml("it&#39;s")).toBe("it's");
  });
  it('collapses multiple spaces', () => {
    expect(stripHtml('a   b')).toBe('a b');
  });
});

// ── timestampToSeconds ────────────────────────────────────────────────────

describe('timestampToSeconds', () => {
  it('returns 0 for falsy input', () => {
    expect(timestampToSeconds('')).toBe(0);
    expect(timestampToSeconds(null)).toBe(0);
  });
  it('parses MM:SS', () => {
    expect(timestampToSeconds('1:30')).toBe(90);
    expect(timestampToSeconds('00:00')).toBe(0);
    expect(timestampToSeconds('59:59')).toBe(3599);
  });
  it('parses HH:MM:SS', () => {
    expect(timestampToSeconds('1:30:00')).toBe(5400);
    expect(timestampToSeconds('2:00:30')).toBe(7230);
  });
  it('parses bare Nh format', () => {
    expect(timestampToSeconds('1h30')).toBe(5400);
    expect(timestampToSeconds('2h15')).toBe(8100);
  });
});

// ── normalizeForMatch ──────────────────────────────────────────────────────

describe('normalizeForMatch', () => {
  it('lowercases', () => {
    expect(normalizeForMatch('ZELDA')).toBe('zelda');
  });
  it('strips guillemets and punctuation', () => {
    expect(normalizeForMatch('«Zelda: Breath»')).toBe('zelda breath');
  });
  it('collapses whitespace', () => {
    expect(normalizeForMatch('a  b')).toBe('a b');
  });
});

// ── escHtml ───────────────────────────────────────────────────────────────

describe('escHtml', () => {
  it('escapes all dangerous characters', () => {
    expect(escHtml('<script>alert("xss")&foo</script>')).toBe(
      '&lt;script&gt;alert(&quot;xss&quot;)&amp;foo&lt;/script&gt;'
    );
  });
  it('leaves safe strings untouched', () => {
    expect(escHtml('hello world')).toBe('hello world');
  });
  it('coerces non-strings', () => {
    expect(escHtml(42)).toBe('42');
  });
});

// ── getScoreClass ─────────────────────────────────────────────────────────

describe('getScoreClass', () => {
  it('returns score-high for >= 75', () => {
    expect(getScoreClass(75)).toBe('score-high');
    expect(getScoreClass(100)).toBe('score-high');
  });
  it('returns score-mid for 50–74', () => {
    expect(getScoreClass(74)).toBe('score-mid');
    expect(getScoreClass(50)).toBe('score-mid');
  });
  it('returns score-low for < 50', () => {
    expect(getScoreClass(49)).toBe('score-low');
    expect(getScoreClass(0)).toBe('score-low');
  });
});

// ── latestDate ────────────────────────────────────────────────────────────

describe('latestDate', () => {
  it('returns 0 for a game with no episodes', () => {
    expect(latestDate({ episodes: [] })).toBe(0);
  });
  it('returns the most recent episode timestamp', () => {
    const game = {
      episodes: [
        { pubDate: '2024-01-01T00:00:00Z' },
        { pubDate: '2024-06-15T00:00:00Z' },
        { pubDate: '2024-03-10T00:00:00Z' },
      ],
    };
    const expected = +new Date('2024-06-15T00:00:00Z');
    expect(latestDate(game)).toBe(expected);
  });
  it('ignores episodes without pubDate', () => {
    const game = { episodes: [{ pubDate: null }, { pubDate: '2024-01-01T00:00:00Z' }] };
    expect(latestDate(game)).toBe(+new Date('2024-01-01T00:00:00Z'));
  });
});

// ── timeAgo ───────────────────────────────────────────────────────────────

describe('timeAgo', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('returns "à l\'instant" for < 2 minutes', () => {
    vi.setSystemTime(new Date('2024-01-01T12:01:00Z'));
    expect(timeAgo('2024-01-01T12:00:30Z')).toBe("à l'instant");
  });
  it('returns minutes for < 1 hour', () => {
    vi.setSystemTime(new Date('2024-01-01T12:10:00Z'));
    expect(timeAgo('2024-01-01T12:00:00Z')).toBe('il y a 10 min');
  });
  it('returns hours for < 24 hours', () => {
    vi.setSystemTime(new Date('2024-01-01T15:00:00Z'));
    expect(timeAgo('2024-01-01T12:00:00Z')).toBe('il y a 3h');
  });
  it('returns days for >= 24 hours', () => {
    vi.setSystemTime(new Date('2024-01-03T12:00:00Z'));
    expect(timeAgo('2024-01-01T12:00:00Z')).toBe('il y a 2 jours');
  });
  it('returns empty string for falsy input', () => {
    expect(timeAgo('')).toBe('');
    expect(timeAgo(null)).toBe('');
  });
});

// ── formatDate ────────────────────────────────────────────────────────────

describe('formatDate', () => {
  it('returns empty string for falsy input', () => {
    expect(formatDate('')).toBe('');
    expect(formatDate(null)).toBe('');
  });
  it('returns a non-empty string for a valid date', () => {
    const result = formatDate('2024-01-15');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });
});
