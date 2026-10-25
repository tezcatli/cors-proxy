import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useGamesStore } from '../../src/stores/games.js'
import { usePlayerStore } from '../../src/stores/player.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'
import DetailView from '../../src/components/DetailView.vue'
import { button, links } from '../helpers/find.js'

// Control Resonant's journal, two of its tests: one read, one whose start is unknown.
const EPISODES = [
  { slug: 'tc', urlSlug: 'triple-play', title: 'Triple Play: Control Resonant', pubTs: 1792600000, audioUrl: 'tc.mp3',
    timestamp: '02:32', timestampSeconds: 152, durationSeconds: 1110, podcast: { id: 'triple-click', name: 'Triple Click' },
    critique: { verdict: 'mixed', pros: ['Striking visuals'], cons: ['Hard combat'] }, games: [], chapters: [] },
  { slug: 'ori', urlSlug: 's04e03', title: 'S04E03 - Ace Combat 8', pubTs: 1791100000, audioUrl: 'ori.mp3',
    timestamp: null, timestampSeconds: 0, podcast: { id: 'origami', name: "ORIGAMI L'Hebdo" },
    critique: null, games: [], chapters: [] },
]

vi.mock('../../src/lib/games.js', () => ({
  fetchGameDetail:  vi.fn(async () => ({ episodes: EPISODES, nameSlugs: ['control-resonant'] })),
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
// A test's row, its toggle (« L'avis de … »), its ▶ (« Écouter … »).
const rows   = w => w.findAll('article[data-test]')
const toggle = row => button(row, /^L'avis de/)
const play   = row => button(row, /^Écouter/)
const UNREAD = 'Pas encore de lecture de ce test'     // the opinion of a test not read yet

describe('the journal of tests', () => {
  it('arrives with every test folded, and opens one’s opinion from anywhere on its row', async () => {
    const w = await mountPage()
    expect(rows(w).map(r => toggle(r)?.attributes('aria-expanded') ?? 'false')).not.toContain('true')
    await toggle(rows(w)[1]).trigger('click')
    expect(toggle(rows(w)[1]).attributes('aria-expanded')).toBe('true')
    expect(rows(w)[1].text()).toContain(UNREAD)
  })

  it('plays with ▶, which never reaches the opinion’s toggle under it', async () => {
    const w = await mountPage()
    await toggle(rows(w)[1]).trigger('click')       // open
    await play(rows(w)[1]).trigger('click')         // play: the toggle would close it
    expect(usePlayerStore().current).toMatchObject({ url: 'ori.mp3' })
    expect(rows(w)[1].text()).toContain(UNREAD)
  })

  it('leads to the episode’s page, this game named', async () => {
    const w = await mountPage()
    const toEpisode = links(rows(w)[0]).find(a => a.attributes('href').startsWith('/episode/'))
    expect(toEpisode.attributes('href')).toBe('/episode/triple-play?game=control-resonant--1')
  })

  it('says how long a test lasts, and nothing for one it does not know', async () => {
    const w = await mountPage()
    expect(rows(w)[0].text()).toContain('19 min')
    expect(rows(w)[1].text()).not.toMatch(/\d+ min/)
    expect(play(rows(w)[1]).attributes('aria-label')).toBe("Écouter l'épisode de ORIGAMI L'Hebdo")
  })
})
