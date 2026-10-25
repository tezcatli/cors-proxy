import { watch } from 'vue'
import { igdbUrl } from '../lib/igdbCdn.js'

/**
 * Wires the browser MediaSession API (lock-screen / OS media controls) to the
 * player store. All calls are feature-guarded so this is inert where
 * MediaSession is unavailable.
 *
 * Commands go through the store (and therefore the audio engine's recovery
 * ladder) — the lock-screen play button is a resume like any other, and must
 * not bypass it.
 *
 * @param playerStore  the Pinia player store.
 * @returns `{ initMediaSession, syncMediaSessionMeta, setMSState, updatePositionState }`
 */
export function useMediaSession(playerStore) {
  const hasMS = 'mediaSession' in navigator

  function imageArtwork(id, fallbackUrl) {
    if (id)          return [{ src: igdbUrl(id, 't_cover_big_2x'), sizes: '512x512', type: 'image/jpeg' }]
    if (fallbackUrl) return [{ src: fallbackUrl,                   sizes: '512x512', type: 'image/jpeg' }]
    return []
  }

  // What is on air (the store's `onAir`): the test's cover, else the podcast's
  // image — the same as the player's.
  function currentArtwork() {
    const air = playerStore.onAir
    return imageArtwork(air.coverImageId, air.imageUrl)
  }

  function setMSState(state) {
    if (hasMS) navigator.mediaSession.playbackState = state
  }

  function updatePositionState() {
    const duration = playerStore.audioDuration
    if (!hasMS || !isFinite(duration) || duration <= 0) return
    try {
      navigator.mediaSession.setPositionState({
        duration,
        playbackRate: 1,
        position:     Math.min(playerStore.currentTime, duration),
      })
    } catch (_) {}
  }

  function buildMetadata() {
    const cur = playerStore.current
    const air = playerStore.onAir
    const md  = new MediaMetadata({
      title:   air.title,                                 // the game on air, else the chapter, else the episode
      artist:  air.title !== cur.episode ? cur.episode : '',
      album:   cur.podcast?.name || 'Ludothèque',
      artwork: currentArtwork(),
    })
    try {
      if (cur.chapters?.length) {
        md.chapterInformation = cur.chapters.map(c => ({
          title:     c.title,
          startTime: c.timestampSeconds,
          artwork:   imageArtwork(c.coverImageId, cur.episodeImageUrl),
        }))
      }
    } catch (_) {}
    return md
  }

  function syncMediaSessionMeta() {
    if (!hasMS || !playerStore.current) return
    navigator.mediaSession.metadata = buildMetadata()   // reassign → reliable repaint
  }

  function initMediaSession(cur) {
    if (!hasMS) return

    syncMediaSessionMeta()

    navigator.mediaSession.setActionHandler('play',  () => playerStore.resume())
    navigator.mediaSession.setActionHandler('pause', () => playerStore.pauseAudio())
    navigator.mediaSession.setActionHandler('seekto', details => {
      if (details.seekTime == null) return
      playerStore.seek(details.seekTime)
      updatePositionState()
    })

    // Track buttons jump between the episode's tests (or its chapters while
    // unread): the store's `skip` is the one rule, shared with the player.
    if (playerStore.marks.length) {
      navigator.mediaSession.setActionHandler('previoustrack', () => playerStore.skip(-1))
      navigator.mediaSession.setActionHandler('nexttrack',     () => playerStore.skip(1))
    } else {
      navigator.mediaSession.setActionHandler('previoustrack', null)
      navigator.mediaSession.setActionHandler('nexttrack', null)
    }
  }

  watch(() => playerStore.onAir && `${playerStore.onAir.coverImageId}|${playerStore.onAir.title}`, () => {
    if (!hasMS || !playerStore.current) return
    syncMediaSessionMeta()
  })

  watch(() => playerStore.current?.episodeImageUrl, url => {
    if (url && playerStore.current) syncMediaSessionMeta()
  })

  return { initMediaSession, syncMediaSessionMeta, setMSState, updatePositionState }
}
