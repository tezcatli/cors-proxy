import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useGamesStore } from '../../src/stores/games.js'
import { usePlayerStore } from '../../src/stores/player.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'
import { button, byTest, links } from '../helpers/find.js'
import PodcastView from '../../src/components/PodcastView.vue'
import PodcastsRow from '../../src/components/PodcastsRow.vue'
import EpisodeRow from '../../src/components/EpisodeRow.vue'

class NoopIO { observe() {} unobserve() {} disconnect() {} }

const zqsd = { id: 'zqsd', name: 'ZQSD', imageUrl: 'zqsd.jpg' }
const soj  = { id: 'silence-on-joue', name: 'Silence on Joue', imageUrl: 'soj.jpg' }
const EPISODES = [
  { slug: 'z3', urlSlug: 'z3', title: 'ZQSD #115', pubTs: 1791000000, audioUrl: 'z3.mp3', games: [{ name: 'Rivage', slug: 'rivage' }], podcast: zqsd },
  { slug: 's1', urlSlug: 's1', title: 'S20E07',     pubTs: 1790500000, audioUrl: 's1.mp3', games: [{ name: 'TOEM 2' }], podcast: soj },
  { slug: 'z1', urlSlug: 'z1', title: 'ZQSD #113',  pubTs: 1720000000, audioUrl: 'z1.mp3', games: [], podcast: zqsd },
  { slug: 'z2', urlSlug: 'z2', title: 'ZQSDeux #59', pubTs: 1750000000, audioUrl: 'z2.mp3', games: [{ name: 'Star Fox' }, { name: 'Rhythm Paradise' }], podcast: zqsd },
]

vi.mock('../../src/lib/games.js', () => ({
  fetchEpisodes:      vi.fn(() => Promise.resolve(EPISODES)),
  fetchCatalog:       vi.fn(() => Promise.resolve({ games: [] })),
  refreshCatalog:     vi.fn(),
  fetchEpisodeDetail: vi.fn(() => Promise.reject(new Error('not here'))),
}))
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute:  () => ({ params: { id: 'zqsd' }, query: {} }),
  useRouter: () => ({ push, back: vi.fn(), options: { history: { state: {} } } }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

let pinia, media
beforeEach(async () => {
  vi.stubGlobal('IntersectionObserver', NoopIO)
  localStorage.clear()
  media = createFakeMedia()
  setMediaFactory(() => media)
  pinia = createPinia()
  setActivePinia(pinia)
  await useGamesStore().loadEpisodes()
})
afterEach(() => { vi.unstubAllGlobals(); resetMediaFactory() })

const RouterLink = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const opts = stubs => ({ global: { plugins: [pinia], stubs: { BackBar: true, GameCard: true, RouterLink, ...stubs } } })

describe('PodcastView', () => {
  it('lists every episode of its podcast, those without a test included, newest first, by year', async () => {
    const w = mount(PodcastView, opts({ EpisodeRow: { props: ['ep'], template: '<div data-test="episode">{{ ep.title }}</div>' } }))
    await flushPromises()
    expect(byTest(w, 'episode').map(e => e.text())).toEqual(['ZQSD #115', 'ZQSDeux #59', 'ZQSD #113'])
    expect(w.findAll('[aria-labelledby="h-pod-eps"] section').map(y => y.attributes('aria-label')))
      .toEqual(['2026', '2025', '2024'])
    expect(w.text()).toContain('3 épisodes · 3 tests')
  })

  it('plays the newest episode from its start', async () => {
    const w = mount(PodcastView, opts({ EpisodeRow: true }))
    await flushPromises()
    const main = button(w, 'Écouter le dernier épisode')
    await main.trigger('click')
    expect(usePlayerStore().current).toMatchObject({ episodeSlug: 'z3', ts: 0, url: 'z3.mp3' })
  })

  it('offers to resume an episode of its podcast left partway', async () => {
    localStorage.setItem('soj-progress', JSON.stringify({
      'z2|0': { currentTime: 600, ts: 0, chapterEnd: 3000, episodeSlug: 'z2', savedAt: Date.now() },
    }))
    setActivePinia(pinia = createPinia())
    await useGamesStore().loadEpisodes()
    const w = mount(PodcastView, opts({ EpisodeRow: true }))
    await flushPromises()
    expect(button(w, 'Reprendre à 10:00')).toBeDefined()
    expect(links(w, 'ZQSDeux #59')[0].attributes('href')).toMatch(/^\/episode\//)
  })
})

describe('EpisodeRow', () => {
  it('plays the whole episode from its start', async () => {
    const w = mount(EpisodeRow, { props: { ep: EPISODES[2] }, ...opts() })
    await w.find('button').trigger('click')
    expect(usePlayerStore().current).toMatchObject({ episodeSlug: 'z1', ts: 0, slug: 'ZQSD #113' })
  })

  it('shows the covers of its tests, four at most', async () => {
    const many = { ...EPISODES[0], games: Array.from({ length: 6 }, (_, i) => ({ name: `G${i}` })) }
    const w = mount(EpisodeRow, { props: { ep: many }, ...opts() })
    expect(byTest(w, 'cover')).toHaveLength(4)
    expect(w.find('[aria-label="6 tests"]').text()).toBe('+2')
  })
})

describe('PodcastsRow', () => {
  it('has a tile per podcast, newest episode first, leading to its page', async () => {
    const w = mount(PodcastsRow, opts())
    await flushPromises()
    expect(links(w).map(t => t.attributes('href'))).toEqual(['/podcast/zqsd', '/podcast/silence-on-joue'])
    expect(links(w, 'nouvel épisode')).toHaveLength(0)   // first sight: nothing is new
  })

  it('marks a podcast whose newest episode came out since its page was seen', async () => {
    localStorage.setItem('ludo.podcastsSeen', JSON.stringify({ zqsd: 1750000000, 'silence-on-joue': 1790500000 }))
    vi.resetModules()
    const { default: Row } = await import('../../src/components/PodcastsRow.vue')
    const w = mount(Row, opts())
    await flushPromises()
    expect(links(w, 'nouvel épisode').map(t => t.attributes('href'))).toEqual(['/podcast/zqsd'])
  })
})
