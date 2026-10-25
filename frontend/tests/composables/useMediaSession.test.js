import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { usePlayerStore } from '../../src/stores/player.js'
import { useMediaSession } from '../../src/composables/useMediaSession.js'
import { setMediaFactory, resetMediaFactory } from '../../src/lib/audioEngine.js'
import { createFakeMedia } from '../helpers/fakeMedia.js'

const detail = vi.hoisted(() => ({ value: null }))
vi.mock('../../src/lib/games.js', () => ({
  fetchEpisodeDetail: vi.fn(async () => { if (!detail.value) throw new Error('none'); return detail.value }),
}))

let handlers, media

beforeEach(() => {
  detail.value = null
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
      game: 'Multi', episode: 'Ep 1', url: 'u', podcast: { id: 'soj', name: 'Silence on Joue', imageUrl: 'show.jpg' },
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
    expect(meta.artist).toBe('Silence on Joue') // the podcast on Android's second line
    expect(meta.album).toBe('Ep 1')
    expect(meta.artwork[0].src).toBe('show.jpg')  // the podcast's image
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

  // What is on air follows the position, whatever started the track
  // (DECISIONS.md, « Interface »): the test's cover in every chapter of it, the
  // podcast's image elsewhere — an ad cut included.
  describe('what is on air', () => {
    const A = { name: 'Hades II', resolvedName: 'Hades II', slug: 'hades', coverImageId: 'coA', timestamp: '1:40', timestampSeconds: 100 }
    const B = { name: 'Silksong', resolvedName: 'Hollow Knight: Silksong', slug: 'silk', coverImageId: 'coB', timestamp: '6:40', timestampSeconds: 400 }
    const chapters = [
      { title: 'Intro',          timestampSeconds: 0 },
      { title: 'Hades II',       timestampSeconds: 100, slug: 'hades', coverImageId: 'coA' },
      { title: 'Le courrier',    timestampSeconds: 200 },
      { title: 'Hades II, suite', timestampSeconds: 300, slug: 'hades', coverImageId: 'coA' },
      { title: 'Silksong',       timestampSeconds: 400, slug: 'silk', coverImageId: 'coB' },
    ]
    const podcast = { id: 'silence-on-joue', name: 'Silence on Joue', imageUrl: 'show.jpg' }
    const track = extra => ({ game: 'Ep 1', episode: 'Ep 1', url: 'u', podcast, tests: [A, B], ...extra })
    const art   = () => navigator.mediaSession.metadata.artwork[0].src
    const at    = async t => { media.emit('timeupdate', { currentTime: t }); await nextTick() }

    it('goes podcast, test A, podcast, A again, test B through a whole episode', async () => {
      const store = usePlayerStore()
      store.play(track({ chapters }))
      useMediaSession(store).initMediaSession(store.current)
      const seen = []
      for (const t of [10, 150, 250, 350, 450]) {
        await at(t)
        seen.push([art().includes('coA') ? 'A' : art().includes('coB') ? 'B' : art(), navigator.mediaSession.metadata.title])
      }
      expect(seen).toEqual([
        ['show.jpg', 'Intro'], ['A', 'Hades II'], ['show.jpg', 'Le courrier'],
        ['A', 'Hades II'], ['B', 'Hollow Knight: Silksong'],
      ])
      expect(navigator.mediaSession.metadata.artist).toBe('Silence on Joue')
      expect(navigator.mediaSession.metadata.album).toBe('Ep 1')
    })

    it('shows test A when the track started at test B is taken back to A', async () => {
      const store = usePlayerStore()
      store.play(track({ chapters, game: 'Silksong', slug: 'silk', coverImageId: 'coB', ts: 400 }))
      useMediaSession(store).initMediaSession(store.current)
      await at(120)
      expect(art()).toContain('coA')
      expect(store.onAir.title).toBe('Hades II')
    })

    it('never shows the game the track was started for outside its test', async () => {
      const store = usePlayerStore()
      store.play(track({ chapters, game: 'Silksong', slug: 'silk', coverImageId: 'coB', ts: 400, episodeImageUrl: 'ep.jpg' }))
      useMediaSession(store).initMediaSession(store.current)
      await at(10)
      expect(art()).toBe('ep.jpg')       // the episode's own image, before its podcast's
    })

    it('loads the chapters of a track started from a list', async () => {
      detail.value = { chapters, games: [A, B] }
      const store = usePlayerStore()
      store.play(track({ chapters: [], episodeUrlSlug: 'ep-1' }))
      await vi.waitFor(() => expect(store.current.chapters).toHaveLength(5))
      useMediaSession(store).initMediaSession(store.current)
      await at(250)
      expect(art()).toBe('show.jpg')     // the mail, between the two parts of A
    })

    it('shows a test that starts within a chapter of the feed (its critique, after the chapter start)', async () => {
      const store = usePlayerStore()
      const feedChapters = [
        { title: 'Jeux de société', timestampSeconds: 0 },
        { title: 'Hades II',        timestampSeconds: 90 },          // the feed's own chapter, no page
        { title: 'La minute culturelle', timestampSeconds: 300 },
      ]
      store.play(track({ chapters: feedChapters, tests: [A] }))      // A starts at 100
      useMediaSession(store).initMediaSession(store.current)
      await at(150)
      expect(art()).toContain('coA')
      await at(310)
      expect(art()).toBe('show.jpg')
    })

    it('never puts on air a test whose start is unknown', async () => {
      const store = usePlayerStore()
      store.play(track({ chapters: [], tests: [{ ...A, timestamp: null, timestampSeconds: 0 }] }))
      useMediaSession(store).initMediaSession(store.current)
      await at(250)
      expect(art()).toBe('show.jpg')
    })

    it('falls back to the last test started in an episode without chapters', async () => {
      const store = usePlayerStore()
      store.play(track({ chapters: [] }))
      useMediaSession(store).initMediaSession(store.current)
      await at(250)
      expect(art()).toContain('coA')
      await at(50)
      expect(art()).toBe('show.jpg')
    })
  })
})
