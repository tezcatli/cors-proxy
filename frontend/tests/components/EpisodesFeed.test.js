import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import EpisodesFeed from '../../src/components/EpisodesFeed.vue'
import { byTest } from '../helpers/find.js'
import { useGamesStore } from '../../src/stores/games.js'

// jsdom has no IntersectionObserver; the rows' infinite scroll constructs one.
class NoopIO {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const EPISODES = [
  { slug: 'a', urlSlug: 'a', title: 'Zelda chez SoJ',   pubTs: 3, games: [{ name: 'Zelda' }],
    podcast: { id: 'silence-on-joue', name: 'Silence on Joue' } },
  { slug: 'b', urlSlug: 'b', title: 'Chrono chez FDG',  pubTs: 2, games: [{ name: 'Chrono Trigger' }],
    podcast: { id: 'fin-du-game', name: 'Fin du Game' } },
  { slug: 'c', urlSlug: 'c', title: 'Mario chez SoJ',   pubTs: 1, games: [{ name: 'Mario' }],
    podcast: { id: 'silence-on-joue', name: 'Silence on Joue' } },
  { slug: 'd', urlSlug: 'd', title: 'Bande-annonce : Zelda arrive', pubTs: 0, games: [],
    podcast: { id: 'silence-on-joue', name: 'Silence on Joue' } },
]

vi.mock('../../src/lib/games.js', () => ({
  fetchEpisodes: vi.fn(() => Promise.resolve(EPISODES)),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), RouterLink: { template: '<a><slot /></a>' } }))

let pinia
beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', NoopIO)
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => { vi.unstubAllGlobals() })

// The feed reads the store's episodes (App loads them); the cards and rows are stubbed.
async function mountFeed(searchQuery = '', { phone = false } = {}) {
  vi.stubGlobal('matchMedia', () => ({ matches: phone, addEventListener() {}, removeEventListener() {} }))
  await useGamesStore().loadEpisodes()
  const w = mount(EpisodesFeed, {
    props: { searchQuery },
    global: {
      plugins: [pinia],
      stubs: {
        TestCard:   { props: { item: Object, featured: Boolean }, template: '<div data-test="card" :data-featured="featured ? 1 : 0">{{ item.test.name }}</div>' },
        EpisodeRow: { props: ['ep'], template: '<div data-test="episode">{{ ep.title }}</div>' },
      },
    },
  })
  await flushPromises()
  return w
}
const cards = w => byTest(w, 'card').map(e => e.text())
const rows  = w => byTest(w, 'episode').map(e => e.text())

describe('EpisodesFeed', () => {
  it('shows every podcast’s tests, one card each; an episode without a test has none', async () => {
    const w = await mountFeed('', { phone: true })
    expect(cards(w)).toEqual(['Zelda', 'Chrono Trigger', 'Mario'])
    expect(rows(w)).toEqual([])
  })

  it('searches the tests by their game, and the episodes by their title', async () => {
    const w = await mountFeed('zelda')
    expect(cards(w)).toEqual(['Zelda'])
    // The episode that tests nothing is found by its title.
    expect(rows(w)).toEqual(['Zelda chez SoJ', 'Bande-annonce : Zelda arrive'])
  })

  it('finds an episode by its title though none of its tests matches', async () => {
    const w = await mountFeed('chez fdg')
    expect(cards(w)).toEqual([])
    expect(rows(w)).toEqual(['Chrono chez FDG'])
  })
})

describe('EpisodesFeed on a phone', () => {
  it('shows the newest test large on a wide screen', async () => {
    const w = await mountFeed('', { phone: false })
    expect(byTest(w, 'card').map(e => e.attributes('data-featured'))).toEqual(['1', '0', '0'])
  })

  it('drops the showcase on a phone: the row starts with the newest test', async () => {
    const w = await mountFeed('', { phone: true })
    expect(byTest(w, 'card').map(e => e.attributes('data-featured'))).toEqual(['0', '0', '0'])
  })
})

describe('EpisodesFeed’s row of new tests', () => {
  it('holds the 30 newest tests; the rest of the history is reached by its games and podcasts', async () => {
    const { fetchEpisodes } = await import('../../src/lib/games.js')
    const many = Array.from({ length: 40 }, (_, i) => ({
      slug: `e${i}`, urlSlug: `e${i}`, title: `Ep ${i}`, pubTs: 100 - i, games: [{ name: `G${i}` }],
      podcast: { id: 'silence-on-joue', name: 'Silence on Joue' },
    }))
    fetchEpisodes.mockResolvedValueOnce(many)
    const w = await mountFeed('', { phone: true })
    expect(byTest(w, 'card')).toHaveLength(30)
  })
})
