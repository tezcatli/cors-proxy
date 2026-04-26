import { describe, it, expect, beforeEach, vi } from 'vitest';
import { normKey } from '../src/lib/utils.js';
import { correct } from '../src/lib/corrections.js';
import { ensureIgdbData, clearCache, getCachedMeta, getCachedData } from '../src/lib/igdb.js';
import { IGDB, mockResponse } from './contract.js';

// ── normKey ───────────────────────────────────────────────────────────────

describe('normKey', () => {
  it('lowercases', () => {
    expect(normKey('ZELDA')).toBe('zelda');
  });
  it('strips accents', () => {
    expect(normKey('Élodie')).toBe('elodie');
    expect(normKey('Château')).toBe('chateau');
  });
  it('removes non-alphanumeric characters and spaces', () => {
    expect(normKey('Zelda: Breath of the Wild')).toBe('zeldabreathofthewild');
    expect(normKey("Mario's World")).toBe('mariosworld');
  });
  it('handles empty string', () => {
    expect(normKey('')).toBe('');
  });
});

// ── correct ───────────────────────────────────────────────────────────────

describe('correct', () => {
  it('returns canonical name for known misspelling', () => {
    expect(correct('Artic Eggs')).toBe('Arctic Eggs');
  });
  it('is case-insensitive', () => {
    expect(correct('ARTIC EGGS')).toBe('Arctic Eggs');
    expect(correct('artic eggs')).toBe('Arctic Eggs');
  });
  it('returns original name when no correction found', () => {
    expect(correct('Elden Ring')).toBe('Elden Ring');
  });
});

// ── ensureIgdbData ────────────────────────────────────────────────────────

const SAMPLE_DATA = {
  url: 'https://images.igdb.com/igdb/image/upload/t_cover_big_2x/abc123.jpg',
  metacritic: 85,
  developer: 'Test Studio',
  genres: ['Action'],
  released: '2021',
  platforms: ['PC'],
  rating: 80,
  esrb: 'T',
  description: 'A great game.',
};

vi.mock('../src/lib/auth.js', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../src/lib/auth.js';

beforeEach(() => {
  clearCache();
  vi.resetAllMocks();
});

describe('ensureIgdbData', () => {
  it('fetches and returns data on cache miss', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    const data = await ensureIgdbData('Test Game');
    expect(data).toEqual(SAMPLE_DATA);
    expect(apiFetch).toHaveBeenCalledOnce();
  });

  it('returns cached result on second call without re-fetching', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    await ensureIgdbData('Test Game');
    await ensureIgdbData('Test Game');
    expect(apiFetch).toHaveBeenCalledOnce();
  });

  it('cache key is case-insensitive', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    await ensureIgdbData('Test Game');
    await ensureIgdbData('test game');
    expect(apiFetch).toHaveBeenCalledOnce();
  });

  it('caches null for not-found games', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.not_found, null));
    const data = await ensureIgdbData('Unknown Game');
    expect(data).toBeNull();
    await ensureIgdbData('Unknown Game');
    expect(apiFetch).toHaveBeenCalledOnce();
  });
});

// ── getCachedMeta / getCachedData ─────────────────────────────────────────

describe('getCachedMeta', () => {
  it('returns null before any fetch', () => {
    expect(getCachedMeta('Test Game')).toBeNull();
  });

  it('returns metacritic score after fetch', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    await ensureIgdbData('Test Game');
    expect(getCachedMeta('Test Game')).toBe(85);
  });
});

describe('getCachedData', () => {
  it('returns null before any fetch', () => {
    expect(getCachedData('Test Game')).toBeNull();
  });

  it('returns full data object after fetch', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    await ensureIgdbData('Test Game');
    expect(getCachedData('Test Game')).toEqual(SAMPLE_DATA);
  });
});
