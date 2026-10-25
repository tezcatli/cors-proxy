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

// A dev tool: what it shows isn't held, only that it can't write where the
// corrections can't be written.
describe('resolution console', () => {
  it('offers a correction where the file is writable, and none where it is read-only', async () => {
    const corrige = w => w.findAll('button[aria-label="Corriger cette résolution"]')
    expect(corrige(await mountPage()).length).toBeGreaterThan(0)
    fetchResolutionStats.mockResolvedValueOnce({ ...structuredClone(STATS), writable: false })
    expect(corrige(await mountPage())).toHaveLength(0)
  })
})
