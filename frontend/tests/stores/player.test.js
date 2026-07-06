import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePlayerStore } from '../../src/stores/player.js'

beforeEach(() => {
  localStorage.clear()
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
      game: 'Zelda', slug: 'Zelda', episode: 'Ep 1', url: 'https://ex.com/ep1.mp3',
      ts: 90, timestamp: '1:30', episodeImageUrl: null, pubTs: null, episodeSlug: null, episodeUrlSlug: null, coverImageId: null, podcast: null, chapters: [],
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

describe('restored flag (resume cue)', () => {
  const saved = { current: { game: 'Zelda', slug: 'zelda', episode: 'Ep 1', url: 'url1', chapters: [] }, currentTime: 120 }

  it('is set by restore() and cleared once playback starts', () => {
    const store = usePlayerStore()
    store.restore(saved)
    expect(store.restored).toBe(true)
    expect(store.paused).toBe(true)
    expect(store.currentTime).toBe(120)

    store.setPaused(true)            // still paused → cue stays
    expect(store.restored).toBe(true)
    store.setPaused(false)           // user resumes → cue clears
    expect(store.restored).toBe(false)
  })

  it('is cleared when a new episode is played', () => {
    const store = usePlayerStore()
    store.restore(saved)
    store.play({ game: 'Mario', episode: 'Ep 2', url: 'url2' })
    expect(store.restored).toBe(false)
  })
})

describe('resumeTimeFor', () => {
  // A chapter starting at 100s, ending at 200s.
  function seed(currentTime) {
    localStorage.setItem('soj-progress', JSON.stringify({
      'ep-1|100': { currentTime, chapterEnd: 200, gameSlug: 'g', ts: 100, savedAt: Date.now() },
    }))
  }

  it('resumes the saved position when partway through', () => {
    seed(150)
    expect(usePlayerStore().resumeTimeFor('ep-1', 100)).toBe(150)
  })

  it('restarts at the start when the chapter is finished', () => {
    seed(199)
    expect(usePlayerStore().resumeTimeFor('ep-1', 100)).toBe(100)
  })

  it('restarts at the start when barely any progress', () => {
    seed(100.5)
    expect(usePlayerStore().resumeTimeFor('ep-1', 100)).toBe(100)
  })

  it('returns the start when no progress is saved', () => {
    expect(usePlayerStore().resumeTimeFor('ep-1', 100)).toBe(100)
  })
})

describe('getEpisodeLatestProgress', () => {
  it('returns the newest-savedAt entry for the episode', () => {
    const now = Date.now()
    localStorage.setItem('soj-progress', JSON.stringify({
      'ep-1|0':   { currentTime: 30,  chapterEnd: 100, gameSlug: 'g', ts: 0,   savedAt: now - 5000 },
      'ep-1|100': { currentTime: 150, chapterEnd: 200, gameSlug: 'g', ts: 100, savedAt: now - 1000 },
      'ep-2|0':   { currentTime: 10,  chapterEnd: 100, gameSlug: 'g', ts: 0,   savedAt: now },
    }))
    const latest = usePlayerStore().getEpisodeLatestProgress('ep-1')
    expect(latest.ts).toBe(100)
    expect(latest.currentTime).toBe(150)
  })

  it('returns null when the episode has no saved progress', () => {
    expect(usePlayerStore().getEpisodeLatestProgress('absent')).toBeNull()
  })
})

describe('progress map pruning (on load)', () => {
  const DAY = 24 * 3600 * 1000

  it('drops entries older than the 180-day TTL, keeps fresh ones', () => {
    const now = Date.now()
    localStorage.setItem('soj-progress', JSON.stringify({
      'fresh|0': { currentTime: 30, chapterEnd: 100, gameSlug: 'g', ts: 0, savedAt: now - DAY },
      'stale|0': { currentTime: 30, chapterEnd: 100, gameSlug: 'g', ts: 0, savedAt: now - 200 * DAY },
    }))
    const store = usePlayerStore()
    expect(store.getEpisodeProgress('fresh', 0)).not.toBeNull()
    expect(store.getEpisodeProgress('stale', 0)).toBeNull()
  })

  it('caps the map to the newest 500 entries', () => {
    const now = Date.now()
    const map = {}
    for (let i = 0; i < 600; i++) {
      map[`ep${i}|0`] = { currentTime: 10, chapterEnd: 100, gameSlug: 'g', ts: 0, savedAt: now - (600 - i) * 1000 }
    }
    // ep0 is oldest (savedAt now-600s); ep599 is newest.
    localStorage.setItem('soj-progress', JSON.stringify(map))
    const store = usePlayerStore()
    expect(store.getEpisodeProgress('ep599', 0)).not.toBeNull()  // newest kept
    expect(store.getEpisodeProgress('ep0', 0)).toBeNull()        // oldest evicted
  })
})
