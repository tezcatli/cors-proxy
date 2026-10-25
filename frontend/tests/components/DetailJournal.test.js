import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useGamesStore } from '../../src/stores/games.js'
import { usePlayerStore } from '../../src/stores/player.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'
import DetailView from '../../src/components/DetailView.vue'

// Control Resonant's journal, two of its tests: one read, one whose start is unknown.
const EPISODES = [
  { slug: 'tc', urlSlug: 'triple-play', title: 'Triple Play: Control Resonant', pubTs: 1792600000, audioUrl: 'tc.mp3',
    timestamp: '02:32', timestampSeconds: 152, podcast: { id: 'triple-click', name: 'Triple Click' },
    critique: { verdict: 'mixed', pros: ['Striking visuals'], cons: ['Hard combat'] }, games: [], chapters: [] },
  { slug: 'ori', urlSlug: 's04e03', title: 'S04E03 - Ace Combat 8', pubTs: 1791100000, audioUrl: 'ori.mp3',
    timestamp: null, timestampSeconds: 0, podcast: { id: 'origami', name: "ORIGAMI L'Hebdo" },
    critique: null, games: [], chapters: [] },
]

vi.mock('../../src/lib/games.js', () => ({
  fetchGameDetail:  vi.fn(async () => ({ episodes: EPISODES, nameSlugs: ['control-resonant'] })),
  refreshGameIgdb:  vi.fn(),
  fetchEpisodeDetail: vi.fn(() => Promise.reject(new Error('not here'))),
}))
vi.mock('../../src/lib/auth.js', async orig => ({ ...(await orig()), isAdmin: () => false }))
vi.mock('../../src/lib/flipTransition.js', () => ({ playInto: () => {}, captureSource: () => {} }))
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute:  () => ({ params: { slug: 'control-resonant--1' }, query: { test: '' } }),
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), options: { history: { state: {} } } }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

let pinia
beforeEach(() => {
  localStorage.clear()
  setMediaFactory(() => createFakeMedia())
  pinia = createPinia()
  setActivePinia(pinia)
  useGamesStore().all = [{ slug: 'control-resonant--1', name: 'Control Resonant', igdb: {}, podcasts: [], episodeCount: 2 }]
})
afterEach(() => resetMediaFactory())

async function mountPage() {
  const w = mount(DetailView, { global: { plugins: [pinia], stubs: { BackBar: true, MediaViewer: true, IgdbPickerModal: true, RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
  await flushPromises()
  return w
}
const rows = w => w.findAll('.test')

describe('the journal of tests', () => {
  it('opens a test’s opinion from anywhere on its row, the chevron turned', async () => {
    const w = await mountPage()
    const toggle = rows(w)[1].find('.test__toggle')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(rows(w)[1].classes()).toContain('is-open')
    expect(rows(w)[1].find('.test__toggle').attributes('aria-expanded')).toBe('true')
  })

  it('plays with ▶, which never reaches the opinion’s toggle under it', async () => {
    const w = await mountPage()
    await rows(w)[1].find('.test__toggle').trigger('click')       // open
    await rows(w)[1].find('.test__play').trigger('click')         // play: the toggle would close it
    expect(usePlayerStore().current).toMatchObject({ url: 'ori.mp3' })
    expect(rows(w)[1].classes()).toContain('is-open')
  })

  it('leads to the episode’s page, this game named', async () => {
    const w = await mountPage()
    expect(rows(w)[0].find('a.test__ep').attributes('href')).toBe('/episode/triple-play?game=control-resonant--1')
  })

  it('says a start it knows, and a dash for one it does not', async () => {
    const w = await mountPage()
    expect(rows(w).map(r => r.find('.test__at').text())).toEqual(['2:32', '—'])
    expect(rows(w)[1].find('.test__play').attributes('aria-label')).toBe("Écouter l'épisode de ORIGAMI L'Hebdo")
  })
})
