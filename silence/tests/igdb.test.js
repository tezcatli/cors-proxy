import { describe, it, expect, beforeEach, vi } from 'vitest';
import { normKey } from '../src/lib/utils.js';
import { ensureIgdbData, clearCache, getCachedMeta, getCachedData, hasCachedEntry, igdbCacheVersion } from '../src/lib/igdb.js';
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

// ── ensureIgdbData ────────────────────────────────────────────────────────

const SAMPLE_DATA = {
  coverImageId:  'abc123',
  bgImageId:     'bg456',
  screenshotIds: ['sc789'],
  metacritic:    85,
  developer:     'Test Studio',
  publisher:     'Test Publisher',
  modes:         ['Single player'],
  steamUrl:      'https://store.steampowered.com/app/123',
  genres:        ['Action'],
  released:      '2021',
  platforms:     ['PC'],
  rating:        80,
  esrb:          'T',
  description:   'A great game.',
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

  it('year param is passed to API but does not affect cache key', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    await ensureIgdbData('Test Game', 2021);
    await ensureIgdbData('Test Game');
    expect(apiFetch).toHaveBeenCalledOnce();
    expect(apiFetch.mock.calls[0][0]).toContain('year=2021');
  });

  it('increments igdbCacheVersion on each fetch', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    const before = igdbCacheVersion.value;
    await ensureIgdbData('Test Game');
    expect(igdbCacheVersion.value).toBe(before + 1);
  });

  it('caches null for not-found games', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.not_found, null));
    const data = await ensureIgdbData('Unknown Game');
    expect(data).toBeNull();
    await ensureIgdbData('Unknown Game');
    expect(apiFetch).toHaveBeenCalledOnce();
  });

  it('concurrent calls share one in-flight request', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    const [a, b] = await Promise.all([
      ensureIgdbData('Test Game'),
      ensureIgdbData('Test Game'),
    ]);
    expect(apiFetch).toHaveBeenCalledOnce();
    expect(a).toEqual(SAMPLE_DATA);
    expect(b).toEqual(SAMPLE_DATA);
  });

  it('removes in-flight entry on error so next call retries', async () => {
    apiFetch.mockRejectedValueOnce(new Error('network error'));
    await expect(ensureIgdbData('Test Game')).rejects.toThrow();
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    const data = await ensureIgdbData('Test Game');
    expect(data).toEqual(SAMPLE_DATA);
    expect(apiFetch).toHaveBeenCalledTimes(2);
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

describe('hasCachedEntry', () => {
  it('returns false before any fetch', () => {
    expect(hasCachedEntry('Test Game')).toBe(false);
  });

  it('returns true after a successful fetch', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.success, SAMPLE_DATA));
    await ensureIgdbData('Test Game');
    expect(hasCachedEntry('Test Game')).toBe(true);
  });

  it('returns true for not-found games (null cached)', async () => {
    apiFetch.mockResolvedValue(mockResponse(IGDB.game.not_found, null));
    await ensureIgdbData('Unknown Game');
    expect(hasCachedEntry('Unknown Game')).toBe(true);
  });

  it('returns false after a failed fetch (no cache entry written)', async () => {
    apiFetch.mockRejectedValue(new Error('network error'));
    await expect(ensureIgdbData('Test Game')).rejects.toThrow();
    expect(hasCachedEntry('Test Game')).toBe(false);
  });
});
