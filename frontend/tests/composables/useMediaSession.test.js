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

  it('shows the chapter title even when the chapter has no artwork', () => {
    const store = usePlayerStore()
    store.play({
      game: 'Multi', episode: 'Ep 1', url: 'u', episodeImageUrl: 'ep.jpg',
      chapters: [
        { title: 'Chapter A', timestampSeconds: 0,   slug: 'a', coverImageId: 111 },
        { title: 'Chapter B', timestampSeconds: 100, slug: 'b', coverImageId: null },
      ],
    })
    const audioEl = ref({ duration: 200, currentTime: 0, playbackRate: 1 })
    const { initMediaSession, syncMediaSessionMeta } =
      useMediaSession(store, audioEl, { safePlay: vi.fn(), safePause: vi.fn() })

    initMediaSession(store.current)
    store.setCurrentTime(120)          // now in chapter B (no dedicated cover)
    syncMediaSessionMeta()

    const meta = navigator.mediaSession.metadata
    expect(meta.title).toBe('Chapter B')        // chapter title, not the episode
    expect(meta.artist).toBe('Ep 1')
    expect(meta.artwork[0].src).toBe('ep.jpg')  // episode-image fallback
  })

  it('uses the chapter cover when the chapter has one', () => {
    const store = usePlayerStore()
    store.play({
      game: 'Multi', episode: 'Ep 1', url: 'u', episodeImageUrl: 'ep.jpg',
      chapters: [{ title: 'Chapter A', timestampSeconds: 0, slug: 'a', coverImageId: 111 }],
    })
    const audioEl = ref({ duration: 200, currentTime: 0, playbackRate: 1 })
    const { syncMediaSessionMeta } =
      useMediaSession(store, audioEl, { safePlay: vi.fn(), safePause: vi.fn() })

    store.setCurrentTime(10)
    syncMediaSessionMeta()

    const meta = navigator.mediaSession.metadata
    expect(meta.title).toBe('Chapter A')
    expect(meta.artwork[0].src).toContain('111')
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
