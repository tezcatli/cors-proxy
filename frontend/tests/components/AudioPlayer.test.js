import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from '../../src/stores/player.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'
import { button } from '../helpers/find.js'
import AudioPlayer from '../../src/components/AudioPlayer.vue'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

beforeEach(() => {
  localStorage.clear()
  setMediaFactory(() => createFakeMedia())
  setActivePinia(createPinia())
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })   // a phone
})
afterEach(() => { vi.useRealTimers(); resetMediaFactory() })

// The full player, open on a phone, 10 minutes into an episode.
async function openSheet() {
  const player = usePlayerStore()
  player.play({ game: 'x', episode: 'S04E06', url: 'e.mp3', ts: 600, chapters: [{ timestampSeconds: 0, title: 'Sommaire' }] })
  const w = mount(AudioPlayer, { global: { stubs: { teleport: true } } })
  await flushPromises()
  await button(w, /^En lecture/).trigger('click')
  return { w, player }
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
