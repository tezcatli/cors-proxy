import { describe, it, expect } from 'vitest';
import {
  formatDate, progressPct, formatTime, formatDuration, testHref,
} from '../src/lib/utils.js';

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

describe('testHref', () => {
  it('opens the game’s page', () => {
    expect(testHref({ ep: { slug: 'g/1', urlSlug: 'ep-1' }, test: { slug: 'zelda' } })).toBe('/game/zelda')
  })

  it('opens the episode when the game has no page', () => {
    expect(testHref({ ep: { slug: 'g/1', urlSlug: 'ep-1' }, test: { name: 'Inconnu' } })).toBe('/episode/ep-1')
  })
})

describe('formatDuration', () => {
  it('says minutes, then hours and minutes past an hour', () => {
    expect(formatDuration(20)).toBe('1 min');
    expect(formatDuration(1110)).toBe('19 min');
    expect(formatDuration(3900)).toBe('1 h 05');
  });
  it('says nothing for an unknown length', () => {
    expect(formatDuration(null)).toBe('');
    expect(formatDuration(undefined)).toBe('');
    expect(formatDuration(0)).toBe('');
  });
});
