import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ResolutionStatsPage from '../../src/pages/ResolutionStatsPage.vue'

// jsdom has no IntersectionObserver; the table's incremental rendering builds one.
class NoopIO { observe() {} unobserve() {} disconnect() {} }

function row(over = {}) {
  return {
    status: 'resolved', corrected: false, displayName: null,
    slug: 'x', name: 'X', nameSlug: 'x', nameSlugs: ['x'],
    igdbName: 'X', igdbSlug: 'x', coverImageId: null, released: '2020',
    podcasts: ['silence-on-joue'], episodeCount: 1, latestPubTs: 100,
    episodeSlug: 'ep-x', episodeTitle: 'Ep X',
    ...over,
  }
}

const STATS = {
  podcasts: [{ id: 'silence-on-joue', label: 'SoJ', name: 'Silence on Joue',
               appearances: 4, resolved: 2, failed: 0, pending: 0, corrected: 1 }],
  games: [
    row({ slug: 'a', name: 'Myst',     nameSlug: 'myst', igdbName: 'Myst',
          released: '1993', latestPubTs: 300, podcasts: ['fin-du-game'] }),
    row({ slug: 'b', name: 'Furax',    nameSlug: 'furax', igdbName: 'Asfalia: The Cranky Volcano',
          status: 'suspect', released: '2023', latestPubTs: 200 }),
    row({ slug: 'c', name: 'MakeWay',  nameSlug: 'makeway', igdbName: 'Make Way',
          corrected: true, displayName: 'Make Way!', latestPubTs: 100, episodeCount: 3 }),
    row({ slug: 'd', name: 'jeux',     nameSlug: 'jeux', igdbName: null, igdbSlug: null,
          status: 'unresolved', released: null, latestPubTs: 50 }),
  ],
  writable: true, pending: 0, resolving: false,
}

const fetchResolutionStats = vi.fn(() => Promise.resolve(structuredClone(STATS)))
vi.mock('../../src/lib/games.js', () => ({
  fetchResolutionStats: (...a) => fetchResolutionStats(...a),
  refreshPodcastIgdb:   vi.fn(),
  openResolutionStream: vi.fn(() => Promise.reject(new Error('no sse in tests'))),
}))
vi.mock('vue-router', () => ({
  useRouter:  () => ({ push: vi.fn() }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', NoopIO)
  localStorage.clear()
  setActivePinia(createPinia())
})
afterEach(() => { vi.unstubAllGlobals() })

async function mountPage() {
  const w = mount(ResolutionStatsPage, {
    global: { plugins: [createPinia()], stubs: { IgdbPickerModal: true, BackBar: true } },
  })
  await flushPromises()
  return w
}

const names = w => w.findAll('.rt-item .rt-name').map(e => e.text())

// The query is debounced (140ms) to keep ~1660 rows off the keystroke path.
async function search(w, q) {
  await w.find('input[type="search"]').setValue(q)
  await new Promise(r => setTimeout(r, 180))
  await flushPromises()
}

describe('resolution console', () => {
  it('lists every game, newest episode first', async () => {
    const w = await mountPage()
    expect(names(w)).toEqual(['Myst', 'Furax', 'MakeWay', 'jeux'])
  })

  it('filters by status', async () => {
    const w = await mountPage()
    await w.findAll('.tab-group')[0].findAll('.tab-pill')[2].trigger('click')  // Douteux
    expect(names(w)).toEqual(['Furax'])
  })

  it('reaches a correctly-resolved game — the whole point of the rewrite', async () => {
    const w = await mountPage()
    await w.findAll('.tab-group')[0].findAll('.tab-pill')[1].trigger('click')  // Résolus
    expect(names(w)).toEqual(['Myst', 'MakeWay'])
  })

  it('filters by podcast', async () => {
    const w = await mountPage()
    await w.findAll('.tab-group')[1].findAll('.tab-pill')[2].trigger('click')  // FDG
    expect(names(w)).toEqual(['Myst'])
  })

  it('filters to corrected rows', async () => {
    const w = await mountPage()
    await w.find('.toolbar__toggle').trigger('click')
    expect(names(w)).toEqual(['MakeWay'])
  })

  it('searches the podcast name', async () => {
    const w = await mountPage()
    await search(w, 'fura')
    expect(names(w)).toEqual(['Furax'])
  })

  it('searches the IGDB name too — you look for the wrong thing it returned', async () => {
    const w = await mountPage()
    await search(w, 'asfalia')
    expect(names(w)).toEqual(['Furax'])
  })

  it('combines a filter with a query', async () => {
    const w = await mountPage()
    await w.findAll('.tab-group')[0].findAll('.tab-pill')[1].trigger('click')  // Résolus
    await search(w, 'furax')                                                   // a suspect
    expect(names(w)).toEqual([])
  })

  it('sorts by name, and flips direction when the column is clicked again', async () => {
    const w = await mountPage()
    const nameCol = w.findAll('.rt-sort')[0]
    await nameCol.trigger('click')
    expect(names(w)).toEqual(['Furax', 'jeux', 'MakeWay', 'Myst'])
    await nameCol.trigger('click')
    expect(names(w)).toEqual(['Myst', 'MakeWay', 'jeux', 'Furax'])
  })

  it('sorts undated games last whichever way the year column points', async () => {
    const w = await mountPage()
    const yearCol = w.findAll('.rt-sort').find(b => b.text().startsWith('An'))
    await yearCol.trigger('click')
    expect(names(w).at(-1)).toBe('jeux')      // released: null
    await yearCol.trigger('click')
    expect(names(w).at(-1)).toBe('jeux')
  })

  it('resets every filter at once', async () => {
    const w = await mountPage()
    await search(w, 'myst')
    await w.find('.toolbar__reset').trigger('click')
    await flushPromises()
    expect(names(w)).toHaveLength(4)
  })

  it('links each row to its episode', async () => {
    const w = await mountPage()
    expect(w.find('.rt-actions a').attributes('href')).toBe('/episode/ep-x')
  })

  it('hides the correction controls where the file is read-only', async () => {
    fetchResolutionStats.mockResolvedValueOnce({ ...structuredClone(STATS), writable: false })
    const w = await mountPage()
    expect(w.find('.banner--muted').exists()).toBe(true)
    expect(w.findAll('.rt-actions button')).toHaveLength(0)   // no « Corriger »
  })
})
