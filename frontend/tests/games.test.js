import { describe, it, expect, vi } from 'vitest';
import { fetchCatalog } from '../src/lib/games.js';

vi.mock('../src/lib/auth.js', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../src/lib/auth.js';

describe('fetchCatalog', () => {
  it('calls /games and returns parsed JSON', async () => {
    const payload = { games: [{ name: 'Zelda', episodes: [] }], pending: 0 };
    apiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    const result = await fetchCatalog();
    expect(apiFetch).toHaveBeenCalledWith('/silence/games');
    expect(result).toEqual(payload);
  });
});
