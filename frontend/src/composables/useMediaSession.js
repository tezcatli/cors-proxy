import { watch } from 'vue'
import { igdbUrl } from '../lib/igdbCdn.js'

/**
 * Wires the browser MediaSession API (lock-screen / OS media controls) to the
 * player store and a backing <audio> element. All calls are feature-guarded so
 * this is inert where MediaSession is unavailable.
 *
 * @param playerStore  the Pinia player store.
 * @param audioEl      template ref to the <audio> element.
 * @param controls     `{ safePlay, safePause, resumePlayback }` — play/pause that
 *                     tolerate the in-flight play() promise (owned by the
 *                     component); resumePlayback also recovers a wedged element.
 * @returns `{ initMediaSession, syncMediaSessionMeta, setMSState, updatePositionState }`
 */
export function useMediaSession(playerStore, audioEl, { safePlay, safePause, resumePlayback }) {
  const hasMS = 'mediaSession' in navigator

  function imageArtwork(id, fallbackUrl) {
    if (id)          return [{ src: igdbUrl(id, 't_cover_big_2x'), sizes: '512x512', type: 'image/jpeg' }]
    if (fallbackUrl) return [{ src: fallbackUrl,                   sizes: '512x512', type: 'image/jpeg' }]
    return []
  }

  // In a chapter: chapter cover → episode image (matches AudioPlayer's playerCoverSrc).
  // No chapter:   launch game cover → episode image.
  function currentArtwork() {
    const cur = playerStore.current
    const ch  = playerStore.currentChapter
    return imageArtwork(ch ? ch.coverImageId : cur.coverImageId, cur.episodeImageUrl)
  }

  function setMSState(state) {
    if (hasMS) navigator.mediaSession.playbackState = state
  }

  function updatePositionState() {
    const el = audioEl.value
    if (!hasMS || !el || !isFinite(el.duration) || el.duration <= 0) return
    try {
      navigator.mediaSession.setPositionState({
        duration:     el.duration,
        playbackRate: el.playbackRate,
        position:     el.currentTime,
      })
    } catch (_) {}
  }

  function buildMetadata() {
    const cur = playerStore.current
    const ch  = playerStore.currentChapter
    const md  = new MediaMetadata({
      title:   ch?.title || cur.episode,   // chapter title whenever in a chapter, art or not
      artist:  ch ? cur.episode : '',      // episode shown as the subtitle under the chapter
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

    navigator.mediaSession.setActionHandler('play',  () => (resumePlayback ?? safePlay)())
    navigator.mediaSession.setActionHandler('pause', () => safePause())
    navigator.mediaSession.setActionHandler('seekto', details => {
      if (details.seekTime == null || !audioEl.value) return
      if (details.fastSeek && 'fastSeek' in audioEl.value) {
        audioEl.value.fastSeek(details.seekTime)
      } else {
        audioEl.value.currentTime = details.seekTime
      }
      updatePositionState()
    })

    if (cur.chapters?.length) {
      navigator.mediaSession.setActionHandler('previoustrack', () => {
        const chapters = playerStore.current?.chapters
        const t = audioEl.value?.currentTime ?? 0
        if (!chapters?.length) { if (audioEl.value) audioEl.value.currentTime = 0; return }
        let idx = -1
        for (let i = 0; i < chapters.length; i++) {
          if (chapters[i].timestampSeconds <= t) idx = i
          else break
        }
        if (idx >= 0 && t - chapters[idx].timestampSeconds > 3) {
          audioEl.value.currentTime = chapters[idx].timestampSeconds
        } else if (idx > 0) {
          audioEl.value.currentTime = chapters[idx - 1].timestampSeconds
        } else {
          audioEl.value.currentTime = 0
        }
      })
      navigator.mediaSession.setActionHandler('nexttrack', () => {
        const chapters = playerStore.current?.chapters
        const t = audioEl.value?.currentTime ?? 0
        if (!chapters?.length) return
        const next = chapters.find(ch => ch.timestampSeconds > t)
        if (next && audioEl.value) audioEl.value.currentTime = next.timestampSeconds
      })
    } else {
      navigator.mediaSession.setActionHandler('previoustrack', null)
      navigator.mediaSession.setActionHandler('nexttrack', null)
    }
  }

  watch(() => playerStore.currentChapter, () => {
    if (!hasMS || !playerStore.current) return
    syncMediaSessionMeta()
  })

  watch(() => playerStore.current?.episodeImageUrl, url => {
    if (url && playerStore.current) syncMediaSessionMeta()
  })

  return { initMediaSession, syncMediaSessionMeta, setMSState, updatePositionState }
}
