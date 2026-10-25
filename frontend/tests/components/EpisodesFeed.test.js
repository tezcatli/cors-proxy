import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import EpisodesFeed from '../../src/components/EpisodesFeed.vue'
import { useGamesStore } from '../../src/stores/games.js'

// jsdom has no IntersectionObserver; the feed's infinite scroll constructs one.
// Inert stub — every episode in these fixtures fits in the first page anyway.
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
]

vi.mock('../../src/lib/games.js', () => ({
  fetchEpisodes: vi.fn(() => Promise.resolve(EPISODES)),
}))

// The feed only needs to render titles here (one card per test); stub the card.
const mountFeed = () => mount(EpisodesFeed, {
  props: { searchQuery: '' },
  global: {
    plugins: [createPinia()],
    stubs: { TestCard: { props: ['item'], template: '<div class="ep">{{ item.ep.title }}</div>' } },
    mocks: { $router: { push: vi.fn() } },
  },
})

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', NoopIO)
  localStorage.clear()
  setActivePinia(createPinia())
})
afterEach(() => { vi.unstubAllGlobals() })

async function titlesWith(podcast) {
  const w = mountFeed()
  await flushPromises()
  useGamesStore().setPodcast(podcast)
  await flushPromises()
  return w.findAll('.ep').map(e => e.text())
}

describe('EpisodesFeed podcast filter', () => {
  it('shows every episode by default', async () => {
    const w = mountFeed()
    await flushPromises()
    expect(w.findAll('.ep')).toHaveLength(3)
  })

  it('narrows the feed to the selected podcast', async () => {
    expect(await titlesWith('fin-du-game')).toEqual(['Chrono chez FDG'])
  })

  it('shares the selection with the games tab', async () => {
    expect(await titlesWith('silence-on-joue')).toEqual(['Zelda chez SoJ', 'Mario chez SoJ'])
  })

  it('combines the podcast filter with the search query', async () => {
    const w = mount(EpisodesFeed, {
      props: { searchQuery: 'zelda' },
      global: {
        plugins: [createPinia()],
        stubs: { TestCard: { props: ['item'], template: '<div class="ep">{{ item.ep.title }}</div>' } },
      },
    })
    await flushPromises()
    useGamesStore().setPodcast('fin-du-game')
    await flushPromises()
    // Zelda is a Silence on Joue episode → excluded by the FDG filter.
    expect(w.findAll('.ep')).toHaveLength(0)
  })
})

describe('EpisodesFeed on a phone', () => {
  const mountAt = phone => {
    vi.stubGlobal('matchMedia', () => ({ matches: phone, addEventListener() {}, removeEventListener() {} }))
    return mount(EpisodesFeed, {
      props: { searchQuery: '' },
      global: {
        plugins: [createPinia()],
        stubs: { TestCard: { props: { item: Object, featured: Boolean }, template: '<div class="ep" :data-featured="featured ? 1 : 0">{{ item.ep.title }}</div>' } },
      },
    })
  }

  it('shows the newest test large on a wide screen', async () => {
    const w = mountAt(false)
    await flushPromises()
    expect(w.findAll('.ep').map(e => e.attributes('data-featured'))).toEqual(['1', '0', '0'])
  })

  it('drops the showcase on a phone: the grid starts with the newest test', async () => {
    const w = mountAt(true)
    await flushPromises()
    expect(w.findAll('.ep').map(e => e.attributes('data-featured'))).toEqual(['0', '0', '0'])
  })
})
