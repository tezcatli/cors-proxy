import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from '../../src/stores/player.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'
import { createRouter, createMemoryHistory } from 'vue-router'
import { button } from '../helpers/find.js'
import AudioPlayer from '../../src/components/AudioPlayer.vue'

beforeEach(() => {
  localStorage.clear()
  setMediaFactory(() => createFakeMedia())
  setActivePinia(createPinia())
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })   // a phone
})
afterEach(() => { vi.useRealTimers(); resetMediaFactory() })

const Page = { template: '<div />' }

// The player on a phone, over a game's page, 10 minutes into an episode.
async function mountPlayer() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/game/:slug', '/episode/:slug', '/podcast/:id'].map(path => ({ path, component: Page })),
  })
  router.push('/game/x')
  await router.isReady()
  const player = usePlayerStore()
  player.play({ game: 'x', episode: 'S04E06', episodeSlug: 's04e06', url: 'e.mp3', ts: 600, chapters: [{ timestampSeconds: 0, title: 'Sommaire' }] })
  const w = mount(AudioPlayer, { global: { plugins: [router], stubs: { teleport: true } }, attachTo: document.body })
  await flushPromises()
  return { w, player, router }
}

// The full player, open.
async function openSheet() {
  const mounted = await mountPlayer()
  await button(mounted.w, /^En lecture/).trigger('click')
  await flushPromises()
  return mounted
}

const sheet = w => w.find('[role="dialog"]')

// A finger moving by (dx, dy) over half a second (no flick), from the middle of `el`.
async function swipe(el, dx, dy) {
  const at = (x, y) => [{ clientX: 200 + x, clientY: 400 + y }]
  const fire = (type, touches, ms = 0) => {
    const e = new Event(type, { bubbles: true, cancelable: true })
    Object.defineProperty(e, 'touches', { value: touches })
    Object.defineProperty(e, 'timeStamp', { value: 1000 + ms })
    el.dispatchEvent(e)
  }
  fire('touchstart', at(0, 0))
  for (let i = 1; i <= 10; i++) fire('touchmove', at(dx * i / 10, dy * i / 10), i * 50)
  fire('touchend', [])
  await flushPromises()
}

describe('the full player', () => {
  it('adds up quick taps on ↺: three taps go back three minutes, and say so', async () => {
    vi.useFakeTimers()
    const { w, player } = await openSheet()
    for (let i = 0; i < 3; i++) await button(w, 'Reculer d’une minute').trigger('click')
    expect(player.currentTime).toBe(420)
    expect(w.text()).toContain('−3 min')
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(w.text()).not.toContain('−3 min')
  })
})

// DECISIONS (frontend): the full player is a step of the way — back closes it —
// pulled down it shrinks, and the mini player is swiped aside to close it.
describe('the full player, a step of the way', () => {
  it('closes on back, to the page under it', async () => {
    const { w, router } = await openSheet()
    expect(sheet(w).exists()).toBe(true)
    router.back()
    await flushPromises()
    expect(sheet(w).exists()).toBe(false)
    expect(router.currentRoute.value.fullPath).toBe('/game/x')
  })

  it('leaves no entry of its own behind when it leads to the episode', async () => {
    const { w, router } = await openSheet()
    await button(w, /^L'épisode/).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/episode/s04e06')
    router.back()
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/game/x')
  })

  it('shrinks when pulled down far enough, and stays when barely pulled', async () => {
    const { w } = await openSheet()
    await swipe(sheet(w).element, 0, 40)
    expect(sheet(w).exists()).toBe(true)
    await swipe(sheet(w).element, 0, 400)
    expect(sheet(w).exists()).toBe(false)
  })
})

describe('the mini player', () => {
  it('closes when swiped aside', async () => {
    const { w, player } = await mountPlayer()
    vi.useFakeTimers()
    await swipe(button(w, /^En lecture/).element, -800, 0)
    vi.advanceTimersByTime(200)
    expect(player.visible).toBe(false)
  })

  it('opens the full player when swiped up', async () => {
    const { w } = await mountPlayer()
    await swipe(button(w, /^En lecture/).element, 0, -80)
    expect(sheet(w).exists()).toBe(true)
  })
})
