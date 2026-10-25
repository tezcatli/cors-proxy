import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SearchResults from '../../src/components/SearchResults.vue'
import { buttons, button, byTest } from '../helpers/find.js'
import { useGamesStore } from '../../src/stores/games.js'

// jsdom has no IntersectionObserver; the lists' infinite scroll constructs one.
class NoopIO {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const EPISODES = [
  { slug: 'a', urlSlug: 'a', title: 'Zelda chez SoJ',  pubTs: 3, games: [{ name: 'Zelda' }],
    podcast: { id: 'silence-on-joue', name: 'Silence on Joue' } },
  { slug: 'b', urlSlug: 'b', title: 'Chrono chez FDG', pubTs: 2, games: [{ name: 'Chrono Trigger' }],
    podcast: { id: 'fin-du-game', name: 'Fin du Game' } },
  { slug: 'd', urlSlug: 'd', title: 'Bande-annonce : Zelda arrive', pubTs: 0, games: [],
    podcast: { id: 'silence-on-joue', name: 'Silence on Joue' } },
]

vi.mock('../../src/lib/games.js', () => ({
  fetchEpisodes: vi.fn(() => Promise.resolve(EPISODES)),
}))

let pinia
beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', NoopIO)
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => { vi.unstubAllGlobals() })

// App searches the catalog and hands over its games; the episodes are the store's.
async function mountResults(query, { games = [], scope = null } = {}) {
  await useGamesStore().loadEpisodes()
  const w = mount(SearchResults, {
    props: { query, games, scope },
    global: {
      plugins: [pinia],
      stubs: {
        GameGrid:   { props: ['games'], template: '<div><div v-for="g in games" data-test="game">{{ g.name }}</div></div>' },
        EpisodeRow: { props: ['ep'], template: '<div data-test="episode">{{ ep.title }}</div>' },
        TestCard:   { template: '<div data-test="card" />' },
      },
    },
  })
  await flushPromises()
  return w
}
const shown    = w => buttons(w).find(b => b.attributes('aria-selected') === 'true').text()
const games    = w => byTest(w, 'game').map(e => e.text())
const episodes = w => byTest(w, 'episode').map(e => e.text())

describe('SearchResults', () => {
  it('shows the games first, one list, no test cards; each scope tells its count', async () => {
    const w = await mountResults('zelda', { games: [{ slug: 'zelda', name: 'Zelda' }] })
    expect(shown(w)).toMatch(/^Jeux\s+1$/)
    expect(button(w, 'Épisodes').text()).toMatch(/2$/)
    expect(games(w)).toEqual(['Zelda'])
    expect(episodes(w)).toEqual([])
    expect(byTest(w, 'card')).toHaveLength(0)
  })

  it('finds the episodes by their title, those that test nothing included', async () => {
    const w = await mountResults('zelda', { games: [{ slug: 'zelda', name: 'Zelda' }], scope: 'episodes' })
    expect(episodes(w)).toEqual(['Zelda chez SoJ', 'Bande-annonce : Zelda arrive'])
    expect(games(w)).toEqual([])
  })

  it('shows the episodes when no game matches', async () => {
    const w = await mountResults('chez fdg')
    expect(shown(w)).toMatch(/^Épisodes/)
    expect(episodes(w)).toEqual(['Chrono chez FDG'])
  })

  it('keeps the scope the listener chose, though it finds nothing', async () => {
    const w = await mountResults('chez fdg', { scope: 'jeux' })
    expect(shown(w)).toMatch(/^Jeux\s+0$/)
    await button(w, 'Épisodes').trigger('click')
    expect(w.emitted('update:scope')).toEqual([['episodes']])
  })
})
