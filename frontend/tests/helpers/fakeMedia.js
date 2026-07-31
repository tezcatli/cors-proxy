import { vi } from 'vitest'

/**
 * A stand-in for HTMLMediaElement: jsdom implements `play`/`pause`/`load` as
 * "not implemented" stubs, so anything driving the audio engine needs this.
 *
 * Playback is manual on purpose — the engine's whole job is reacting to an
 * element that *doesn't* do what it was told, so tests fire the events.
 */
export function createFakeMedia(overrides = {}) {
  const listeners = {}

  const media = {
    src: '',
    currentSrc: '',
    currentTime: 0,
    duration: NaN,
    volume: 1,
    paused: true,
    seeking: false,
    readyState: 0,
    networkState: 0,
    error: null,
    preload: '',
    nodeType: 0,           // not a real node: skips the DOM append in ensureEl()

    // Resolves unless a test sets `playRejection`.
    playRejection: null,
    play: vi.fn(() => media.playRejection
      ? Promise.reject(media.playRejection)
      : Promise.resolve()),
    pause: vi.fn(() => { media.paused = true; media.emit('pause') }),
    load:  vi.fn(() => { media.currentSrc = media.src; media.currentTime = 0 }),

    setAttribute:    vi.fn(),
    removeAttribute: vi.fn(() => { media.src = '' }),
    addEventListener:    (type, fn) => { (listeners[type] ??= []).push(fn) },
    removeEventListener: (type, fn) => {
      listeners[type] = (listeners[type] ?? []).filter(f => f !== fn)
    },

    /** Fire a media event at the engine. */
    emit(type, patch) {
      if (patch) Object.assign(media, patch)
      for (const fn of listeners[type] ?? []) fn({ type })
    },

    /** Shorthand: the element actually starts playing at `t`. */
    startPlaying(t = media.currentTime) {
      media.paused     = false
      media.readyState = 4
      media.currentTime = t
      media.emit('playing')
    },

    ...overrides,
  }
  return media
}
