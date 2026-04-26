import { describe, it, expect, vi } from 'vitest';
import { parseFeed } from '../src/lib/rss.js';

vi.mock('../src/lib/auth.js', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../src/lib/auth.js';

describe('parseFeed', () => {
  it('calls /rss/games and returns parsed JSON', async () => {
    const games = [{ name: 'Zelda', episodes: [] }];
    apiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(games) });
    const result = await parseFeed();
    expect(apiFetch).toHaveBeenCalledWith('/rss/games');
    expect(result).toEqual(games);
  });

  it('throws on non-ok response', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 502 });
    await expect(parseFeed()).rejects.toThrow('RSS 502');
  });
});
