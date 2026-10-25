import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import EpisodesFeed from '../../src/components/EpisodesFeed.vue'
import { byTest, button } from '../helpers/find.js'
import { useGamesStore } from '../../src/stores/games.js'
import { usePlayerStore } from '../../src/stores/player.js'

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
  { slug: 'e', urlSlug: 'e', title: 'Star Wars et Dawnwalker', pubTs: -1, audioUrl: 'https://example.com/e.mp3', imageUrl: 'e.jpg',
    games: [
      { name: 'Star Wars Galactic Racer', slug: 'racer', timestamp: '20:00', timestampSeconds: 1200, coverImageId: 'c1' },
      { name: 'The Blood of Dawnwalker', slug: 'dawn', timestamp: '40:00', timestampSeconds: 2400, coverImageId: 'c2' },
    ],
    podcast: { id: 'origami', name: "ORIGAMI L'Hebdo" } },
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

// The feed reads the store's episodes (App loads them); the cards are stubbed.
async function mountFeed({ phone = false } = {}) {
  vi.stubGlobal('matchMedia', () => ({ matches: phone, addEventListener() {}, removeEventListener() {} }))
  await useGamesStore().loadEpisodes()
  const w = mount(EpisodesFeed, {
    global: {
      plugins: [pinia],
      stubs: {
        TestCard:   { props: { item: Object, featured: Boolean }, template: '<div data-test="card" :data-featured="featured ? 1 : 0">{{ item.test.name }}</div>' },
      },
    },
  })
  await flushPromises()
  return w
}
const cards = w => byTest(w, 'card').map(e => e.text())

// The top of the Ludothèque: the newest test large on a wide screen, nothing on
// a phone — the games below, newest first, already show the new tests.
describe('EpisodesFeed', () => {
  it('shows the newest test large on a wide screen, and no row of tests', async () => {
    const w = await mountFeed({ phone: false })
    expect(cards(w)).toEqual(['Zelda'])
    expect(byTest(w, 'card')[0].attributes('data-featured')).toBe('1')
  })

  it('shows no test on a phone: it would repeat the first game below', async () => {
    const w = await mountFeed({ phone: true })
    expect(cards(w)).toEqual([])
  })
})

// « Reprendre » tells an episode left partway by what it resumes on: the test at
// the saved position, not the game the listening was started for; × forgets it.
describe('EpisodesFeed’s « Reprendre »', () => {
  const leftInDawnwalker = () => localStorage.setItem('soj-progress', JSON.stringify({
    'e|1200': { currentTime: 2600, chapterEnd: 3600, gameSlug: 'racer', ts: 1200, savedAt: Date.now() },
  }))

  it('names the test at the saved position, and resumes it there', async () => {
    leftInDawnwalker()
    const w = await mountFeed({ phone: true })
    const player = usePlayerStore()
    const play = vi.spyOn(player, 'play').mockImplementation(() => {})
    await button(w, 'Reprendre The Blood of Dawnwalker').trigger('click')
    expect(play).toHaveBeenCalledWith(expect.objectContaining({ game: 'The Blood of Dawnwalker', ts: 2600, episodeSlug: 'e' }))
  })

  it('shows the episode’s image when left outside a test', async () => {
    localStorage.setItem('soj-progress', JSON.stringify({
      'e|0': { currentTime: 300, chapterEnd: 3600, ts: 0, savedAt: Date.now() },
    }))
    const w = await mountFeed({ phone: true })
    expect(byTest(w, 'resume')[0].find('img').attributes('src')).toBe('e.jpg')
    expect(button(w, 'Reprendre Star Wars et Dawnwalker').exists()).toBe(true)
  })

  it('shows the three most recent, and unfolds the others with « Tous · n »', async () => {
    const now = Date.now()
    localStorage.setItem('soj-progress', JSON.stringify(Object.fromEntries(['a', 'b', 'c', 'd', 'e'].map((slug, i) =>
      [`${slug}|0`, { currentTime: 600, chapterEnd: 1200, ts: 0, savedAt: now - i }]))))
    const w = await mountFeed({ phone: true })
    expect(byTest(w, 'resume')).toHaveLength(3)
    await button(w, 'Tous · 5').trigger('click')
    expect(byTest(w, 'resume')).toHaveLength(5)
    expect(button(w, 'Moins').exists()).toBe(true)
  })

  it('forgets a listening with ×, everywhere', async () => {
    leftInDawnwalker()
    const w = await mountFeed({ phone: true })
    await button(w, 'Oublier l’écoute de The Blood of Dawnwalker').trigger('click')
    expect(byTest(w, 'resume')).toHaveLength(0)
    expect(usePlayerStore().resumeEntryFor('e')).toBeNull()
  })
})
