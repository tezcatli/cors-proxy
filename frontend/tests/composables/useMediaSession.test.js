import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'
import { usePlayerStore } from '../../src/stores/player.js'
import { useMediaSession } from '../../src/composables/useMediaSession.js'

let handlers

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  handlers = {}
  globalThis.MediaMetadata = class { constructor(init) { Object.assign(this, init) } }
  vi.stubGlobal('navigator', {
    mediaSession: {
      metadata: null,
      playbackState: 'none',
      setActionHandler: vi.fn((action, fn) => { handlers[action] = fn }),
      setPositionState: vi.fn(),
    },
  })
})
afterEach(() => { vi.unstubAllGlobals() })

describe('useMediaSession', () => {
  it('setMSState updates the playbackState', () => {
    const store = usePlayerStore()
    const { setMSState } = useMediaSession(store, ref(null), { safePlay: vi.fn(), safePause: vi.fn() })
    setMSState('playing')
    expect(navigator.mediaSession.playbackState).toBe('playing')
  })

  it('initMediaSession sets metadata and wires play/pause handlers', () => {
    const store = usePlayerStore()
    store.play({ game: 'Zelda', episode: 'Ep 1', url: 'u', chapters: [] })
    const safePlay = vi.fn()
    const safePause = vi.fn()
    const audioEl = ref({ duration: 100, currentTime: 0, playbackRate: 1 })
    const { initMediaSession } = useMediaSession(store, audioEl, { safePlay, safePause })

    initMediaSession(store.current)
    expect(navigator.mediaSession.metadata.title).toBe('Ep 1')

    handlers.play()
    expect(safePlay).toHaveBeenCalled()
    handlers.pause()
    expect(safePause).toHaveBeenCalled()
  })

  it('updatePositionState reports the audio element position', () => {
    const store = usePlayerStore()
    const audioEl = ref({ duration: 120, currentTime: 30, playbackRate: 1 })
    const { updatePositionState } = useMediaSession(store, audioEl, { safePlay: vi.fn(), safePause: vi.fn() })

    updatePositionState()
    expect(navigator.mediaSession.setPositionState).toHaveBeenCalledWith({
      duration: 120, playbackRate: 1, position: 30,
    })
  })
})
