import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createAudioEngine, setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'

let media, engine

function makeEngine() {
  media  = createFakeMedia()
  setMediaFactory(() => media)
  engine = createAudioEngine()
  return engine
}

beforeEach(() => {
  vi.useFakeTimers()
  makeEngine()
})

afterEach(() => {
  engine.destroy()
  resetMediaFactory()
  vi.useRealTimers()
})

// The healthy path must stay cheap: a resume is a play(), not a re-fetch.
describe('play on a healthy element', () => {
  it('calls play() without re-loading the source', async () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 0 }, { autoplay: true })
    media.startPlaying(0)
    engine.pause()
    media.load.mockClear()
    media.play.mockClear()

    engine.play()
    expect(media.play).toHaveBeenCalled()
    expect(media.load).not.toHaveBeenCalled()
    expect(engine.state.intent).toBe('play')
  })
})

describe('watchdog escalation', () => {
  it('reloads at the anchor when playback never starts', async () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 300 }, { autoplay: true })
    expect(engine.state.status).toBe('loading')
    media.load.mockClear()

    // The element accepts play() but never fires `playing` — the Android wedge.
    await vi.advanceTimersByTimeAsync(6000)

    expect(media.load).toHaveBeenCalledTimes(1)
    expect(media.src).toBe('https://ex.com/a.mp3#t=300')   // ranged GET at the anchor
    expect(engine.state.attempts).toBe(1)
  })

  it('gives up after MAX_RELOADS and exposes a retryable failure', async () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 10 }, { autoplay: true })

    await vi.advanceTimersByTimeAsync(6000)    // attempt 1
    await vi.advanceTimersByTimeAsync(10000)   // attempt 2
    await vi.advanceTimersByTimeAsync(14000)   // no attempts left

    expect(engine.state.status).toBe('failed')
    expect(engine.state.intent).toBe('pause')

    media.load.mockClear()
    engine.retry()
    expect(media.load).toHaveBeenCalledTimes(1)
    expect(engine.state.status).toBe('loading')
    expect(engine.state.intent).toBe('play')
  })

  it('stops escalating once playback actually starts', async () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 0 }, { autoplay: true })
    await vi.advanceTimersByTimeAsync(6000)    // one recovery reload
    expect(engine.state.attempts).toBe(1)

    media.startPlaying(5)
    media.load.mockClear()
    await vi.advanceTimersByTimeAsync(60000)

    expect(engine.state.status).toBe('playing')
    expect(engine.state.attempts).toBe(0)
    expect(media.load).not.toHaveBeenCalled()
  })
})

describe('autoplay refusal', () => {
  it('falls back to paused instead of reloading (a reload cannot supply a gesture)', async () => {
    media.playRejection = Object.assign(new Error('nope'), { name: 'NotAllowedError' })
    engine.load({ url: 'https://ex.com/a.mp3', at: 0 }, { autoplay: true })
    await vi.advanceTimersByTimeAsync(0)

    expect(engine.state.status).toBe('paused')
    expect(engine.state.intent).toBe('pause')

    media.load.mockClear()
    await vi.advanceTimersByTimeAsync(30000)
    expect(media.load).not.toHaveBeenCalled()
  })
})

describe('anchor integrity', () => {
  it('ignores the reset-to-0 a reload reports while a seek is pending', () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 600 }, { autoplay: true })
    media.emit('timeupdate', { currentTime: 0 })      // element rewound by load()
    expect(engine.state.anchor).toBe(600)

    media.emit('timeupdate', { currentTime: 601 })    // real playback progress
    expect(engine.state.anchor).toBe(601)
  })

  it('seeks to the target from loadedmetadata when #t= did not land', () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 600 }, { autoplay: true })
    media.emit('loadedmetadata', { duration: 3600, currentTime: 0 })
    expect(media.currentTime).toBe(600)
    expect(engine.state.duration).toBe(3600)
  })
})

describe('error and ambient recovery', () => {
  it('reloads on a media error while playback is intended', () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 0 }, { autoplay: true })
    media.load.mockClear()
    media.emit('error', { error: { code: 2 } })
    expect(media.load).toHaveBeenCalledTimes(1)
  })

  it('does not reload on an error while paused', () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 0 }, { autoplay: false })
    media.load.mockClear()
    media.emit('error', { error: { code: 2 } })
    expect(media.load).not.toHaveBeenCalled()
  })

  it('recovers a wedged element when the tab returns to the foreground', () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 120 }, { autoplay: true })
    media.startPlaying(120)
    media.emit('pause', { paused: true })    // Android released the resource
    media.load.mockClear()

    document.dispatchEvent(new Event('visibilitychange'))   // visibilityState is 'visible'
    expect(media.load).toHaveBeenCalledTimes(1)
    expect(media.src).toBe('https://ex.com/a.mp3#t=120')
  })
})

describe('pause and stop', () => {
  it('pause clears the watchdog so nothing reloads behind the user', async () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 0 }, { autoplay: true })
    engine.pause()
    media.load.mockClear()
    await vi.advanceTimersByTimeAsync(60000)
    expect(media.load).not.toHaveBeenCalled()
    expect(engine.state.intent).toBe('pause')
  })

  it('stop drops the track and leaves the engine idle', () => {
    engine.load({ url: 'https://ex.com/a.mp3', at: 30 }, { autoplay: true })
    engine.stop()
    expect(engine.state.status).toBe('idle')
    expect(engine.state.anchor).toBe(0)
    engine.play()                       // no track → no-op, never throws
    expect(engine.state.status).toBe('idle')
  })
})
