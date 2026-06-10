import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  formatDate, timeAgo, getScoreClass, formatEpisodeCount, progressPct, formatTime,
} from '../src/lib/utils.js';

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
  it('formats a unix timestamp as a French long date', () => {
    // 1705276800 = 2024-01-15 00:00:00 UTC
    const result = formatDate(1705276800);
    expect(result).toMatch(/janvier/i);
    expect(result).toContain('2024');
  });
});

// ── formatEpisodeCount ────────────────────────────────────────────────────

describe('formatEpisodeCount', () => {
  it('uses singular for 1', () => {
    expect(formatEpisodeCount(1)).toBe('1 épisode');
  });
  it('uses plural for 2+', () => {
    expect(formatEpisodeCount(2)).toBe('2 épisodes');
    expect(formatEpisodeCount(10)).toBe('10 épisodes');
  });
  it('handles 0', () => {
    expect(formatEpisodeCount(0)).toBe('0 épisode');
  });
});

// ── progressPct ───────────────────────────────────────────────────────────

describe('progressPct', () => {
  it('returns the listened fraction as a percentage', () => {
    expect(progressPct(150, 100, 200)).toBe(50);
    expect(progressPct(100, 100, 200)).toBe(0);
    expect(progressPct(200, 100, 200)).toBe(100);
  });
  it('clamps below 0 and above 100', () => {
    expect(progressPct(50, 100, 200)).toBe(0);
    expect(progressPct(500, 100, 200)).toBe(100);
  });
  it('returns 0 for a non-positive span', () => {
    expect(progressPct(150, 200, 200)).toBe(0);
    expect(progressPct(150, 300, 200)).toBe(0);
  });
});

describe('formatTime', () => {
  it('formats sub-hour durations as m:ss', () => {
    expect(formatTime(0)).toBe('0:00');
    expect(formatTime(9)).toBe('0:09');
    expect(formatTime(90)).toBe('1:30');
    expect(formatTime(599)).toBe('9:59');
  });
  it('widens to h:mm:ss past an hour', () => {
    expect(formatTime(3600)).toBe('1:00:00');
    expect(formatTime(3661)).toBe('1:01:01');
  });
  it('guards NaN/Infinity/negatives to 0:00', () => {
    expect(formatTime(NaN)).toBe('0:00');
    expect(formatTime(Infinity)).toBe('0:00');
    expect(formatTime(-5)).toBe('0:00');
  });
});
