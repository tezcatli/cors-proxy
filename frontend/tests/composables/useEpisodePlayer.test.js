import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePlayerStore } from '../../src/stores/player.js'
import { useEpisodePlayer } from '../../src/composables/useEpisodePlayer.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  setMediaFactory(() => createFakeMedia())   // jsdom's <audio> implements nothing
})

afterEach(() => resetMediaFactory())

// A chapter that starts at 100s and runs to 200s (chapterEnd).
const ep = {
  title: 'Ep 1',
  audioUrl: 'https://ex.com/ep1.mp3',
  slug: 'ep-1-guid',
  urlSlug: 'ep-1',
  timestampSeconds: 100,
  pubTs: 0,
  imageUrl: null,
  games: [{ name: 'Zelda', slug: 'zelda' }],
  chapters: [],
}

function seedProgress(currentTime) {
  localStorage.setItem('soj-progress', JSON.stringify({
    'ep-1-guid|100': { currentTime, chapterEnd: 200, gameSlug: 'zelda', ts: 100, savedAt: Date.now() },
  }))
}

// When to resume is the store's rule (`resumeTimeFor`, tested there).
describe('useEpisodePlayer · resume from saved progress', () => {
  it('starts where the store says to resume', () => {
    seedProgress(150)                       // 50% through the chapter
    const { playEp, playerStore } = useEpisodePlayer()
    playEp(ep)
    expect(playerStore.current.ts).toBe(150)
  })
})

describe('useEpisodePlayer · another game of the same episode', () => {
  const ctx = slug => ({ value: { name: slug, slug, coverImageId: null } })

  it("doesn't count the episode as playing on another game's page", () => {
    const zelda = useEpisodePlayer(ctx('zelda'))
    zelda.playEp(ep)
    const mario = useEpisodePlayer(ctx('mario'))
    expect(zelda.isEpPlaying(ep)).toBe(true)
    expect(mario.isEpPlaying(ep)).toBe(false)
  })

  it("starts the other game's review rather than resuming the first", () => {
    seedProgress(150)                       // partway through Zelda's chapter
    useEpisodePlayer(ctx('zelda')).playEp(ep)
    const { playEp, playerStore } = useEpisodePlayer(ctx('mario'))
    playEp({ ...ep, timestampSeconds: 300 })
    expect(playerStore.current.slug).toBe('mario')
    expect(playerStore.current.ts).toBe(300)
  })

  it('still counts it as playing in the feed, which has no game context', () => {
    useEpisodePlayer(ctx('zelda')).playEp(ep)
    expect(useEpisodePlayer().isEpPlaying(ep)).toBe(true)
  })
})
