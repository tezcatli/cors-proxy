import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePlayerStore } from '../../src/stores/player.js'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('initial state', () => {
  it('starts with no current episode', () => {
    const store = usePlayerStore()
    expect(store.current).toBeNull()
    expect(store.visible).toBe(false)
    expect(store.paused).toBe(true)
  })
})

describe('play', () => {
  it('sets current, makes visible, marks playing', () => {
    const store = usePlayerStore()
    store.play({ game: 'Zelda', episode: 'Ep 1', url: 'https://ex.com/ep1.mp3', ts: 90, timestamp: '1:30' })
    expect(store.current).toEqual({
      game: 'Zelda', episode: 'Ep 1', url: 'https://ex.com/ep1.mp3', ts: 90, timestamp: '1:30', coverImageId: null,
    })
    expect(store.visible).toBe(true)
    expect(store.paused).toBe(false)
  })

  it('defaults ts to 0 and timestamp to null when omitted', () => {
    const store = usePlayerStore()
    store.play({ game: 'Mario', episode: 'Ep 2', url: 'https://ex.com/ep2.mp3' })
    expect(store.current.ts).toBe(0)
    expect(store.current.timestamp).toBeNull()
  })

  it('replaces current episode when called again', () => {
    const store = usePlayerStore()
    store.play({ game: 'Zelda', episode: 'Ep 1', url: 'url1' })
    store.play({ game: 'Mario', episode: 'Ep 2', url: 'url2' })
    expect(store.current.game).toBe('Mario')
  })
})

describe('close', () => {
  it('clears current, hides player, marks paused', () => {
    const store = usePlayerStore()
    store.play({ game: 'Zelda', episode: 'Ep 1', url: 'url1' })
    store.close()
    expect(store.current).toBeNull()
    expect(store.visible).toBe(false)
    expect(store.paused).toBe(true)
  })
})

describe('setPaused', () => {
  it('updates paused flag', () => {
    const store = usePlayerStore()
    store.play({ game: 'Zelda', episode: 'Ep 1', url: 'url1' })
    store.setPaused(true)
    expect(store.paused).toBe(true)
    store.setPaused(false)
    expect(store.paused).toBe(false)
  })
})
