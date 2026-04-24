import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGamesStore } from '../../src/stores/games.js'

vi.mock('../../src/lib/rss.js', () => ({ parseFeed: vi.fn() }))
import { parseFeed } from '../../src/lib/rss.js'

const GAMES = [
  { name: 'Zelda',        episodes: [{ pubDate: '2024-06-01T00:00:00Z' }] },
  { name: 'Mario',        episodes: [{ pubDate: '2024-01-01T00:00:00Z' }] },
  { name: 'Hollow Knight', episodes: [{ pubDate: '2024-03-01T00:00:00Z' }] },
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

  it('meta sort falls back to alpha when no scores cached', () => {
    const store = useGamesStore()
    store.all = GAMES
    store.setSort('meta')
    const result = store.filtered('')
    expect(result.map(g => g.name)).toEqual(['Hollow Knight', 'Mario', 'Zelda'])
  })
})

// ── load ──────────────────────────────────────────────────────────────────

describe('load', () => {
  it('populates all and sets lastFetch on success', async () => {
    parseFeed.mockResolvedValue(GAMES)
    const store = useGamesStore()
    await store.load()
    expect(store.all).toHaveLength(3)
    expect(store.lastFetch).not.toBeNull()
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('sets error on failure, keeps all empty', async () => {
    parseFeed.mockRejectedValue(new Error('Network error'))
    const store = useGamesStore()
    await store.load()
    expect(store.error).toBe('Network error')
    expect(store.all).toHaveLength(0)
    expect(store.loading).toBe(false)
  })

  it('sets loading=true while fetching', async () => {
    let resolve
    parseFeed.mockReturnValue(new Promise(r => { resolve = r }))
    const store = useGamesStore()
    const promise = store.load()
    expect(store.loading).toBe(true)
    resolve(GAMES)
    await promise
    expect(store.loading).toBe(false)
  })
})
