import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { normName, rankResults, simplifyPlatform, fetchImage, clearCache } from '../js/rawg.js';
import { RAWG, mockResponse } from './contract.js';

beforeEach(() => clearCache());

// ── normName ──────────────────────────────────────────────────────────────

describe('normName', () => {
  it('lowercases', () => {
    expect(normName('ZELDA')).toBe('zelda');
  });
  it('strips accents', () => {
    expect(normName('Élodie')).toBe('elodie');
    expect(normName('Château')).toBe('chateau');
  });
  it('removes all non-alphanumeric characters', () => {
    expect(normName('Zelda: Breath of the Wild')).toBe('zeldabreathofthewild');
    expect(normName("Mario's World")).toBe('mariosworld');
  });
  it('handles empty string', () => {
    expect(normName('')).toBe('');
  });
});

// ── simplifyPlatform ──────────────────────────────────────────────────────

describe('simplifyPlatform', () => {
  it.each([
    ['PlayStation 4', 'PlayStation'],
    ['PlayStation 5', 'PlayStation'],
    ['Xbox One', 'Xbox'],
    ['Xbox Series X', 'Xbox'],
    ['Nintendo Switch', 'Switch'],
    ['PC', 'PC'],
    ['macOS', 'Mac'],
    ['iOS', 'iOS'],
    ['iPhone', 'iOS'],
    ['Android', 'Android'],
  ])('%s → %s', (input, expected) => {
    expect(simplifyPlatform(input)).toBe(expected);
  });
  it('returns null for unknown platforms', () => {
    expect(simplifyPlatform('Atari 2600')).toBeNull();
    expect(simplifyPlatform('Commodore 64')).toBeNull();
  });
});

// ── rankResults ───────────────────────────────────────────────────────────

describe('rankResults', () => {
  it('exact match scores highest', () => {
    const results = [
      { name: 'Breath of the Wild' },
      { name: 'Zelda: Breath of the Wild' },
    ];
    const ranked = rankResults(results, 'Zelda: Breath of the Wild');
    expect(ranked[0].name).toBe('Zelda: Breath of the Wild');
  });

  it('base name (before colon) scores second', () => {
    const results = [
      { name: 'Unrelated Game' },
      { name: 'Zelda' },
    ];
    const ranked = rankResults(results, 'Zelda: Breath of the Wild');
    expect(ranked[0].name).toBe('Zelda');
  });

  it('prefix match scores above no match', () => {
    const results = [
      { name: 'Unrelated' },
      { name: 'Zelda Adventures' },
    ];
    const ranked = rankResults(results, 'Zelda');
    expect(ranked[0].name).toBe('Zelda Adventures');
  });

  it('does not mutate the original array', () => {
    const results = [{ name: 'A' }, { name: 'B' }];
    const copy = [...results];
    rankResults(results, 'A');
    expect(results).toEqual(copy);
  });

  it('handles empty results array', () => {
    expect(rankResults([], 'Zelda')).toEqual([]);
  });
});

// ── fetchImage (public API with contract-shaped mocks) ────────────────────

describe('fetchImage', () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it('returns the background_image URL on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(RAWG.games.success, {
        results: [{ name: 'Zelda', background_image: 'https://img.example.com/zelda.jpg', slug: null }],
      })
    ));
    const url = await fetchImage('Zelda');
    expect(url).toBe('https://img.example.com/zelda.jpg');
  });

  it('returns cached result on second call (fetch not called again)', async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockResponse(RAWG.games.success, {
        results: [{ name: 'Mario', background_image: 'https://img.example.com/mario.jpg', slug: null }],
      })
    );
    vi.stubGlobal('fetch', mockFetch);
    await fetchImage('Mario');
    await fetchImage('Mario');
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('returns null when upstream returns no results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(RAWG.games.success, { results: [] })
    ));
    const url = await fetchImage('UnknownGame42');
    expect(url).toBeNull();
  });
});
