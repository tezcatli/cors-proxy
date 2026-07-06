import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGamesStore } from '../../src/stores/games.js'

vi.mock('../../src/lib/games.js', () => ({
  fetchCatalog:         vi.fn(),
  refreshCatalog:       vi.fn(),
  openResolutionStream: vi.fn(),
}))
import { fetchCatalog, refreshCatalog, openResolutionStream } from '../../src/lib/games.js'

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

describe('podcast filter', () => {
  it('defaults to all podcasts', () => {
    const store = useGamesStore()
    store.all = MULTI
    expect(store.selectedPodcast).toBe('all')
    expect(store.filtered('')).toHaveLength(3)
  })

  it('filters to a single podcast', () => {
    const store = useGamesStore()
    store.all = MULTI
    store.setPodcast('fin-du-game')
    const names = store.filtered('').map(g => g.name).sort()
    expect(names).toEqual(['Balatro', 'Zelda'])   // Zelda is in both → still included
  })

  it('combines podcast filter with a name query', () => {
    const store = useGamesStore()
    store.all = MULTI
    store.setPodcast('silence-on-joue')
    expect(store.filtered('zelda')).toHaveLength(1)
    expect(store.filtered('balatro')).toHaveLength(0)   // FDG-only, excluded by SoJ filter
  })

  it('persists the selection to localStorage', () => {
    const store = useGamesStore()
    store.setPodcast('fin-du-game')
    expect(localStorage.getItem('soj-podcast-filter')).toBe('fin-du-game')
  })
})

// ── setSort ───────────────────────────────────────────────────────────────

describe('setSort', () => {
  it('switches to a new mode with its default direction', () => {
    const store = useGamesStore()
    store.setSort('date')
    expect(store.sortMode).toBe('date')
    expect(store.sortAsc).toBe(false)   // date defaults to descending
  })

  it('toggles direction when same mode is selected again', () => {
    const store = useGamesStore()
    expect(store.sortAsc).toBe(true)    // alpha default = ascending
    store.setSort('alpha')
    expect(store.sortAsc).toBe(false)
    store.setSort('alpha')
    expect(store.sortAsc).toBe(true)
  })
})

// ── sorting ───────────────────────────────────────────────────────────────

describe('sorting', () => {
  it('sorts alphabetically ascending by default', () => {
    const store = useGamesStore()
    store.all = GAMES
    const result = store.filtered('')
    expect(result.map(g => g.name)).toEqual(['Hollow Knight', 'Mario', 'Zelda'])
  })

  it('sorts alphabetically descending when toggled', () => {
    const store = useGamesStore()
    store.all = GAMES
    store.setSort('alpha')              // toggles asc→desc
    const result = store.filtered('')
    expect(result.map(g => g.name)).toEqual(['Zelda', 'Mario', 'Hollow Knight'])
  })

  it('sorts by date descending (newest first)', () => {
    const store = useGamesStore()
    store.all = GAMES
    store.setSort('date')
    const result = store.filtered('')
    expect(result[0].name).toBe('Zelda')        // June 2024 — newest
    expect(result[2].name).toBe('Mario')        // Jan 2024  — oldest
  })

  it('sorts by date ascending when toggled', () => {
    const store = useGamesStore()
    store.all = GAMES
    store.setSort('date')
    store.setSort('date')               // toggle → ascending
    const result = store.filtered('')
    expect(result[0].name).toBe('Mario')        // oldest first
  })

  it('meta sort ranks by metacritic descending, nulls last', () => {
    const store = useGamesStore()
    store.all = GAMES
    store.setSort('meta')
    const result = store.filtered('')
    expect(result[0].name).toBe('Zelda')        // 90 — highest
    expect(result[1].name).toBe('Hollow Knight') // 85
    expect(result[2].name).toBe('Mario')         // null — last
  })
})

// ── refresh ───────────────────────────────────────────────────────────────

describe('refresh', () => {
  it('populates all via refreshCatalog on success', async () => {
    refreshCatalog.mockResolvedValue({ games: GAMES, pending: 0 })
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
    fetchCatalog.mockResolvedValue({ games: GAMES, pending: 0 })
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
    resolve({ games: GAMES, pending: 0 })
    await Promise.all([p1, p2])
    expect(fetchCatalog).toHaveBeenCalledTimes(1)
  })

  it('sets loading=true while fetching', async () => {
    let resolve
    fetchCatalog.mockReturnValue(new Promise(r => { resolve = r }))
    const store = useGamesStore()
    const promise = store.load()
    expect(store.loading).toBe(true)
    resolve({ games: GAMES, pending: 0 })
    await promise
    expect(store.loading).toBe(false)
  })
})

// ── SSE resolution stream ──────────────────────────────────────────────────

describe('SSE resolution', () => {
  let fakeSSE

  beforeEach(() => {
    fakeSSE = { onmessage: null, onerror: null, close: vi.fn() }
    openResolutionStream.mockReturnValue(fakeSSE)
  })

  it('opens SSE and sets resolving=true when pending > 0 after load', async () => {
    fetchCatalog.mockResolvedValue({ games: GAMES, pending: 2 })
    const store = useGamesStore()
    await store.load()
    expect(openResolutionStream).toHaveBeenCalled()
    expect(store.resolving).toBe(true)
  })

  it('does not open SSE when pending is 0', async () => {
    fetchCatalog.mockResolvedValue({ games: GAMES, pending: 0 })
    const store = useGamesStore()
    await store.load()
    expect(openResolutionStream).not.toHaveBeenCalled()
    expect(store.resolving).toBe(false)
  })

  it('patches game slug and igdb in-place on resolved event', async () => {
    fetchCatalog.mockResolvedValue({ games: GAMES, pending: 1 })
    const store = useGamesStore()
    await store.load()

    fakeSSE.onmessage({ data: JSON.stringify({
      type: 'resolved', nameSlug: 'mario', igdbSlug: 'super-mario', igdb: { metacritic: 95 },
    }) })

    const updated = store.all.find(g => g.slug === 'super-mario')
    expect(updated).toBeTruthy()
    expect(updated.igdb.metacritic).toBe(95)
  })

  it('closes SSE, clears resolving, and calls load on done event', async () => {
    fetchCatalog
      .mockResolvedValueOnce({ games: GAMES, pending: 1 })
      .mockResolvedValue({ games: GAMES, pending: 0 })
    const store = useGamesStore()
    await store.load()

    fakeSSE.onmessage({ data: JSON.stringify({ type: 'done' }) })
    await Promise.resolve()   // flush the load() promise

    expect(fakeSSE.close).toHaveBeenCalled()
    expect(store.resolving).toBe(false)
    expect(fetchCatalog).toHaveBeenCalledTimes(2)
  })

  it('does not reopen SSE on done even if pending stays > 0 (no reload loop)', async () => {
    fetchCatalog.mockResolvedValue({ games: GAMES, pending: 2 })   // always pending
    const store = useGamesStore()
    await store.load()
    expect(openResolutionStream).toHaveBeenCalledTimes(1)

    // 'done' while still pending: reconcile, but must NOT re-arm SSE (else loop).
    fakeSSE.onmessage({ data: JSON.stringify({ type: 'done' }) })
    await Promise.resolve(); await Promise.resolve()

    expect(openResolutionStream).toHaveBeenCalledTimes(1)
    expect(store.resolving).toBe(false)
  })
})
