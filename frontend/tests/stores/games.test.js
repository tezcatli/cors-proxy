import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGamesStore } from '../../src/stores/games.js'

vi.mock('../../src/lib/games.js', () => ({
  fetchCatalog:         vi.fn(),
  refreshCatalog:       vi.fn(),
  fetchEpisodes:        vi.fn(),
}))
import { fetchCatalog, refreshCatalog, fetchEpisodes } from '../../src/lib/games.js'

const GAMES = [
  { name: 'Zelda',         slug: 'zelda',         latestPubTs: 1717200000, episodeCount: 3, igdb: { metacritic: 90 } },
  { name: 'Mario',         slug: 'mario',         latestPubTs: 1704067200, episodeCount: 1, igdb: null },
  { name: 'Hollow Knight', slug: 'hollow-knight', latestPubTs: 1709251200, episodeCount: 2, igdb: { metacritic: 85 } },
]

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

// ── filtered ──────────────────────────────────────────────────────────────

describe('filtered', () => {
  it('returns all games when query is empty', () => {
    const store = useGamesStore()
    store.all = GAMES
    expect(store.filtered('')).toHaveLength(3)
  })

  it('filters by name case-insensitively', () => {
    const store = useGamesStore()
    store.all = GAMES
    expect(store.filtered('zelda')).toHaveLength(1)
    expect(store.filtered('ZELDA')[0].name).toBe('Zelda')
  })

  it('returns empty array when no match', () => {
    const store = useGamesStore()
    store.all = GAMES
    expect(store.filtered('halo')).toHaveLength(0)
  })
})

// ── podcast filter ──────────────────────────────────────────────────────────

const MULTI = [
  { name: 'Zelda',  slug: 'zelda',  podcasts: ['silence-on-joue', 'fin-du-game'], igdb: null },
  { name: 'Mario',  slug: 'mario',  podcasts: ['silence-on-joue'],                igdb: null },
  { name: 'Balatro', slug: 'balatro', podcasts: ['fin-du-game'],                  igdb: null },
]

// A podcast's page narrows the catalog to its games; the Ludothèque shows them all.
describe("a podcast's games", () => {
  it('are every game without a podcast', () => {
    const store = useGamesStore()
    store.all = MULTI
    expect(store.filtered('')).toHaveLength(3)
  })

  it("are the games a podcast tested, on its page", () => {
    const store = useGamesStore()
    store.all = MULTI
    const names = store.filtered('', 'fin-du-game').map(g => g.name).sort()
    expect(names).toEqual(['Balatro', 'Zelda'])   // Zelda is in both → still included
  })

  it('combine with a name query', () => {
    const store = useGamesStore()
    store.all = MULTI
    expect(store.filtered('zelda', 'silence-on-joue')).toHaveLength(1)
    expect(store.filtered('balatro', 'silence-on-joue')).toHaveLength(0)
  })
})

describe('episodes', () => {
  it('load once for every reader, and keep the list on a failed reload', async () => {
    const store = useGamesStore()
    fetchEpisodes.mockResolvedValueOnce([{ slug: 'a' }])
    await Promise.all([store.loadEpisodes(), store.loadEpisodes()])
    expect(fetchEpisodes).toHaveBeenCalledTimes(1)
    expect(store.episodesLoaded).toBe(true)

    fetchEpisodes.mockRejectedValueOnce(new Error('down'))
    await store.loadEpisodes()
    expect(store.episodes).toEqual([{ slug: 'a' }])
    expect(store.episodesError).toBe('down')
    expect(store.episodesLoading).toBe(false)
  })
})

// ── sorting ───────────────────────────────────────────────────────────────
// GAMES: Zelda (June 2024, 90), Hollow Knight (March 2024, 85), Mario (Jan 2024, no score).

describe('sorting', () => {
  it('defaults to the newest tests first', () => {
    const store = useGamesStore()
    store.all = GAMES
    expect([store.sortMode, store.sortAsc]).toEqual(['date', false])
    expect(store.filtered('').map(g => g.name)).toEqual(['Zelda', 'Hollow Knight', 'Mario'])
  })

  // A mode comes with its own direction; choosing it again flips it.
  it.each([
    [['date'],           ['Mario', 'Hollow Knight', 'Zelda']],
    [['alpha'],          ['Hollow Knight', 'Mario', 'Zelda']],
    [['alpha', 'alpha'], ['Zelda', 'Mario', 'Hollow Knight']],
    [['meta'],           ['Zelda', 'Hollow Knight', 'Mario']],     // no score: last
  ])('sorts by %j', (modes, order) => {
    const store = useGamesStore()
    store.all = GAMES
    modes.forEach(m => store.setSort(m))
    expect(store.filtered('').map(g => g.name)).toEqual(order)
  })
})

// ── refresh ───────────────────────────────────────────────────────────────

describe('refresh', () => {
  it('populates all via refreshCatalog on success', async () => {
    refreshCatalog.mockResolvedValue({ games: GAMES })
    const store = useGamesStore()
    await store.refresh()
    expect(store.all).toHaveLength(3)
    expect(store.lastFetch).not.toBeNull()
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('sets error on failure', async () => {
    refreshCatalog.mockRejectedValue(new Error('upstream error'))
    const store = useGamesStore()
    await store.refresh()
    expect(store.error).toBe('upstream error')
    expect(store.loading).toBe(false)
  })
})

// ── load ──────────────────────────────────────────────────────────────────

describe('load', () => {
  it('populates all and sets lastFetch on success', async () => {
    fetchCatalog.mockResolvedValue({ games: GAMES })
    const store = useGamesStore()
    await store.load()
    expect(store.all).toHaveLength(3)
    expect(store.lastFetch).not.toBeNull()
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('sets error on failure, keeps all empty', async () => {
    fetchCatalog.mockRejectedValue(new Error('Network error'))
    const store = useGamesStore()
    await store.load()
    expect(store.error).toBe('Network error')
    expect(store.all).toHaveLength(0)
    expect(store.loading).toBe(false)
  })

  it('coalesces concurrent load() calls into a single fetch (in-flight dedup)', async () => {
    let resolve
    fetchCatalog.mockReturnValue(new Promise(r => { resolve = r }))
    const store = useGamesStore()
    const p1 = store.load()
    const p2 = store.load()
    expect(fetchCatalog).toHaveBeenCalledTimes(1)
    resolve({ games: GAMES })
    await Promise.all([p1, p2])
    expect(fetchCatalog).toHaveBeenCalledTimes(1)
  })

  it('sets loading=true while fetching', async () => {
    let resolve
    fetchCatalog.mockReturnValue(new Promise(r => { resolve = r }))
    const store = useGamesStore()
    const promise = store.load()
    expect(store.loading).toBe(true)
    resolve({ games: GAMES })
    await promise
    expect(store.loading).toBe(false)
  })
})
