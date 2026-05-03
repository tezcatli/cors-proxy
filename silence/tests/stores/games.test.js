import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGamesStore } from '../../src/stores/games.js'

vi.mock('../../src/lib/games.js', () => ({
  fetchCatalog:  vi.fn(),
  refreshCatalog: vi.fn(),
  fetchIgdb:     vi.fn(),
}))
import { fetchCatalog, refreshCatalog, fetchIgdb } from '../../src/lib/games.js'

const GAMES = [
  { name: 'Zelda',         latestPubTs: 1717200000, episodeCount: 3, igdb: { metacritic: 90 } },
  { name: 'Mario',         latestPubTs: 1704067200, episodeCount: 1, igdb: null },
  { name: 'Hollow Knight', latestPubTs: 1709251200, episodeCount: 2, igdb: { metacritic: 85 } },
]

beforeEach(() => {
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
    refreshCatalog.mockResolvedValue(GAMES)
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
    fetchCatalog.mockResolvedValue(GAMES)
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

  it('sets loading=true while fetching', async () => {
    let resolve
    fetchCatalog.mockReturnValue(new Promise(r => { resolve = r }))
    const store = useGamesStore()
    const promise = store.load()
    expect(store.loading).toBe(true)
    resolve(GAMES)
    await promise
    expect(store.loading).toBe(false)
  })
})

// ── queueIgdb ─────────────────────────────────────────────────────────────

describe('queueIgdb', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('patches store entry with full igdb after batch resolves', async () => {
    fetchCatalog.mockResolvedValue(GAMES)
    fetchIgdb.mockResolvedValue({
      Zelda: { coverImageId: 'abc123', metacritic: 90 },
    })
    const store = useGamesStore()
    await store.load()
    store.queueIgdb('Zelda')
    // flush the debounce timer
    await vi.runAllTimersAsync()
    const zelda = store.all.find(g => g.name === 'Zelda')
    expect(zelda.igdb.coverImageId).toBe('abc123')
  })

  it('deduplicates names in the same batch', async () => {
    fetchCatalog.mockResolvedValue(GAMES)
    fetchIgdb.mockResolvedValue({})
    const store = useGamesStore()
    await store.load()
    store.queueIgdb('Zelda')
    store.queueIgdb('Zelda')
    store.queueIgdb('Mario')
    await vi.runAllTimersAsync()
    const [calledNames] = fetchIgdb.mock.calls[0]
    expect(calledNames.filter(n => n === 'Zelda')).toHaveLength(1)
  })
})
