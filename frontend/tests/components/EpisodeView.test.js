import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from '../../src/stores/player.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'
import { button, links, byTest } from '../helpers/find.js'
import EpisodeView from '../../src/components/EpisodeView.vue'

// SoJ S20E07's shape: the feed's chapters, the tests at their critique.
const EPISODE = {
  title: 'S20E07', slug: 'guid-7', urlSlug: 's20e07', audioUrl: 's.mp3', pubTs: 1790500000, imageUrl: 's20e07.jpg',
  podcast: { id: 'silence-on-joue', name: 'Silence on Joue', imageUrl: 'soj.jpg' },
  chapters: [
    { timestamp: '0:00',    timestampSeconds: 0,    title: 'Intro' },
    { timestamp: '33:19',   timestampSeconds: 1999, title: 'Le com des coms' },
    { timestamp: '1:07:42', timestampSeconds: 4062, title: 'Star Wars Galactic Racer' },
  ],
  games: [
    { name: 'The Blood of Dawnwalker', slug: 'dawnwalker', timestamp: '00:39:23', timestampSeconds: 2363, coverImageId: 'co1',
      critique: { verdict: 'positive', pros: ['Belle ambiance'], cons: [] } },
    { name: 'Star Wars Galactic Racer', resolvedName: 'Star Wars: Galactic Racer', slug: 'racer', timestamp: '01:08:21', timestampSeconds: 4101, coverImageId: 'co2',
      critique: { verdict: 'positive', pros: ['Des courses nerveuses'], cons: ['Circuits peu lisibles'] } },
  ],
}

vi.mock('../../src/lib/games.js', () => ({ fetchEpisodeDetail: vi.fn(async () => EPISODE) }))
let query = {}
vi.mock('vue-router', () => ({
  useRoute:  () => ({ params: { episodeSlug: 's20e07' }, query }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), options: { history: { state: {} } } }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

let media
beforeEach(() => {
  localStorage.clear()
  media = createFakeMedia()
  setMediaFactory(() => media)
  setActivePinia(createPinia())
  query = {}
})
afterEach(() => resetMediaFactory())

async function mountPage(q = {}) {
  query = q
  const w = mount(EpisodeView, { global: { stubs: { BackBar: true, RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
  await flushPromises()
  return w
}

// The moments: the buttons of the episode's programme.
const moments = w => w.findAll('[aria-labelledby="h-programme"] li > button')

describe('EpisodeView', () => {
  it('lists the moments alike — a test told by its cover, its opinion left to its game’s page', async () => {
    const w = await mountPage()
    expect(moments(w).map(m => m.attributes('title'))).toEqual(
      ['Intro', 'Le com des coms', 'The Blood of Dawnwalker', 'Star Wars: Galactic Racer'])
    expect(moments(w).filter(m => m.find('img').exists())).toHaveLength(2)
    expect(w.text()).not.toContain('Positif')
    expect(w.text()).not.toContain('Des courses nerveuses')
  })

  it('heads the page with the episode’s image, else its podcast’s — never a game’s cover', async () => {
    const w = await mountPage()
    expect(byTest(w, 'scene')[0].find('img').attributes('src')).toBe('s20e07.jpg')
    expect(w.findAll('img').filter(i => i.attributes('src') === 'soj.jpg')).toHaveLength(0)
    EPISODE.imageUrl = null
    const bare = await mountPage()
    EPISODE.imageUrl = 's20e07.jpg'
    expect(byTest(bare, 'scene')[0].find('img').attributes('src')).toBe('soj.jpg')
  })

  it('leads each test to its game’s page', async () => {
    const w = await mountPage()
    expect(links(w, 'La fiche de').map(a => a.attributes('href'))).toEqual(['/game/dawnwalker', '/game/racer'])
  })

  it('plays a moment from its start', async () => {
    const w = await mountPage()
    await moments(w)[2].trigger('click')
    expect(usePlayerStore().current).toMatchObject({ ts: 2363, slug: 'dawnwalker' })
  })

  it('offers the episode from its start, from its podcast', async () => {
    const w = await mountPage()
    expect(button(w, /^Écouter/).text()).toContain("Écouter l'épisode")
    expect(w.text()).not.toContain('Depuis le début')
  })

  it('offers the test first, from a game’s page, and the whole episode beside it', async () => {
    const w = await mountPage({ game: 'racer' })
    expect(button(w, /^Écouter/).text()).toContain('Écouter le test · 1:08:21')
    expect(w.text()).toContain('Depuis le début')
  })
})
