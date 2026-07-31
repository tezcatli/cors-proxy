import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePlayerStore } from '../../src/stores/player.js'
import { useMediaSession } from '../../src/composables/useMediaSession.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'

let handlers, media

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  media = createFakeMedia()
  setMediaFactory(() => media)
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
afterEach(() => { vi.unstubAllGlobals(); resetMediaFactory() })

describe('useMediaSession', () => {
  it('setMSState updates the playbackState', () => {
    const store = usePlayerStore()
    const { setMSState } = useMediaSession(store)
    setMSState('playing')
    expect(navigator.mediaSession.playbackState).toBe('playing')
  })

  it('initMediaSession sets metadata and wires play/pause handlers', () => {
    const store = usePlayerStore()
    store.play({ game: 'Zelda', episode: 'Ep 1', url: 'u', chapters: [] })
    const { initMediaSession } = useMediaSession(store)

    initMediaSession(store.current)
    expect(navigator.mediaSession.metadata.title).toBe('Ep 1')

    handlers.pause()
    expect(store.paused).toBe(true)
    handlers.play()
    expect(store.paused).toBe(false)
  })

  // The lock-screen button is a resume like any other: it must go through the
  // store, so a wedged element gets the engine's recovery ladder.
  it('routes the lock-screen play action through the store command', () => {
    const store = usePlayerStore()
    store.play({ game: 'Zelda', episode: 'Ep 1', url: 'u', chapters: [] })
    store.pauseAudio()
    const { initMediaSession } = useMediaSession(store)

    initMediaSession(store.current)
    media.play.mockClear()
    handlers.play()

    expect(store.paused).toBe(false)
    expect(media.play).toHaveBeenCalled()
  })

  it('seeks chapters through the store rather than the element', () => {
    const store = usePlayerStore()
    store.play({
      game: 'Multi', episode: 'Ep 1', url: 'u',
      chapters: [
        { title: 'A', timestampSeconds: 0,   slug: 'a' },
        { title: 'B', timestampSeconds: 100, slug: 'b' },
      ],
    })
    const { initMediaSession } = useMediaSession(store)
    initMediaSession(store.current)

    handlers.nexttrack()
    expect(store.currentTime).toBe(100)
    handlers.previoustrack()
    expect(store.currentTime).toBe(0)     // at the chapter start → jump to the previous one
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
    const { initMediaSession, syncMediaSessionMeta } =
      useMediaSession(store)

    initMediaSession(store.current)
    media.emit('timeupdate', { currentTime: 120 })          // now in chapter B (no dedicated cover)
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
    const { syncMediaSessionMeta } =
      useMediaSession(store)

    media.emit('timeupdate', { currentTime: 10 })
    syncMediaSessionMeta()

    const meta = navigator.mediaSession.metadata
    expect(meta.title).toBe('Chapter A')
    expect(meta.artwork[0].src).toContain('111')
  })

  it('updatePositionState reports the mirrored engine position', () => {
    const store = usePlayerStore()
    store.play({ game: 'Zelda', episode: 'Ep 1', url: 'u', chapters: [] })
    const { updatePositionState } = useMediaSession(store)

    media.emit('durationchange', { duration: 120 })
    media.emit('timeupdate', { currentTime: 30 })
    updatePositionState()
    expect(navigator.mediaSession.setPositionState).toHaveBeenCalledWith({
      duration: 120, playbackRate: 1, position: 30,
    })
  })
})
