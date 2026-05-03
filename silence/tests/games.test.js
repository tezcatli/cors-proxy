import { describe, it, expect, vi } from 'vitest';
import { fetchCatalog } from '../src/lib/games.js';

vi.mock('../src/lib/auth.js', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../src/lib/auth.js';

describe('fetchCatalog', () => {
  it('calls /games and returns parsed JSON', async () => {
    const games = [{ name: 'Zelda', episodes: [] }];
    apiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(games) });
    const result = await fetchCatalog();
    expect(apiFetch).toHaveBeenCalledWith('/games');
    expect(result).toEqual(games);
  });
});
