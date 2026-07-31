import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { progressPct, PROGRESS_MIN_PCT, PROGRESS_DONE_PCT } from '../lib/utils.js'
import { createAudioEngine } from '../lib/audioEngine.js'

export const usePlayerStore = defineStore('player', () => {
  const current     = ref(null)
  const visible     = ref(false)
  const currentTime = ref(0)
  const audioDuration = ref(0)
  const restored    = ref(false)   // true while a reload-restored track sits paused, awaiting resume

  // Mirrored from the engine — the element's truth, read-only from here out.
  const status = ref('idle')
  const intent = ref('pause')
  const volume = ref(1)

  const engine = createAudioEngine({
    onState(s) {
      status.value        = s.status
      intent.value        = s.intent
      currentTime.value   = s.position
      audioDuration.value = s.duration
      volume.value        = s.volume
      if (s.status === 'playing') restored.value = false
    },
  })

  // `paused` follows *intent*, so a tap flips the icon immediately; `buffering`
  // is the gap between intent and reality, and `failed` is where that gap stops
  // being temporary (see lib/audioEngine.js).
  const paused    = computed(() => intent.value !== 'play')
  const buffering = computed(() => intent.value === 'play' && status.value !== 'playing')
  const failed    = computed(() => status.value === 'failed')

  function play({ game, slug, episode, url, ts = 0, timestamp = null, episodeImageUrl = null, pubTs = null, episodeSlug = null, episodeUrlSlug = null, coverImageId = null, chapters = null, podcast = null }) {
    clearTimeout(_progressTimer)
    _updateProgress()
    restored.value = false
    current.value = { game, slug: slug ?? game, episode, url, ts, timestamp, episodeImageUrl, pubTs, episodeSlug, episodeUrlSlug, coverImageId, podcast, chapters: chapters ?? [] }
    visible.value = true
    engine.load({ url, at: ts }, { autoplay: true })
  }

  function close() {
    clearTimeout(_progressTimer)
    _updateProgress()           // save final position before clearing
    engine.stop()
    current.value       = null
    visible.value       = false
    currentTime.value   = 0
    audioDuration.value = 0
  }

  // ── Playback commands (the only way components touch the audio) ─────────────
  function resume()         { restored.value = false; engine.play() }
  function pauseAudio()     { engine.pause() }
  function togglePlayback() { paused.value ? resume() : pauseAudio() }
  function seek(t)          { engine.seek(t) }
  function retry()          { restored.value = false; engine.retry() }
  function setVolume(v)     { engine.setVolume(v) }

  const currentChapter = computed(() => {
    const chs = current.value?.chapters
    if (!chs?.length) return null
    let active = null
    for (const ch of chs) {
      if (ch.timestampSeconds <= currentTime.value) active = ch
      else break
    }
    return active
  })

  function setEpisodeImageUrl(url) {
    if (current.value) current.value = { ...current.value, episodeImageUrl: url }
  }

  // Reload resume: bring the track back *paused*, with the cue, so the user's
  // tap is the gesture that starts playback.
  function restore(savedState) {
    const t           = savedState.currentTime ?? 0
    current.value     = { ...savedState.current, ts: t }
    visible.value     = true
    restored.value    = true
    engine.load({ url: current.value.url, at: t }, { autoplay: false })
    currentTime.value = t
  }

  // ── Progress tracking ────────────────────────────────────────────────────────
  const PROGRESS_KEY      = 'soj-progress'
  const PROGRESS_MAX_AGE  = 180 * 24 * 3600 * 1000   // 180 days
  const PROGRESS_MAX_KEYS = 500                       // newest-N cap

  // Keep the map bounded: drop stale entries (by savedAt), then cap to the
  // newest PROGRESS_MAX_KEYS so localStorage and getGameProgress's scan stay small.
  function _pruneProgressMap(map) {
    const now     = Date.now()
    const entries = Object.entries(map)
      .filter(([, v]) => !v.savedAt || now - v.savedAt < PROGRESS_MAX_AGE)
    if (entries.length > PROGRESS_MAX_KEYS) {
      entries.sort((a, b) => (b[1].savedAt ?? 0) - (a[1].savedAt ?? 0))
      entries.length = PROGRESS_MAX_KEYS
    }
    return Object.fromEntries(entries)
  }

  function _loadProgressMap() {
    try { return _pruneProgressMap(JSON.parse(localStorage.getItem(PROGRESS_KEY) || '{}')) }
    catch { return {} }
  }
  const progressMap = ref(_loadProgressMap())

  function _saveProgressMap() {
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(progressMap.value))
  }

  function _updateProgress(overrideChapterTs, overrideCurrentTime) {
    const cur = current.value
    if (!cur || audioDuration.value <= 0) return
    const chapterTs  = overrideChapterTs  ?? (currentChapter.value?.timestampSeconds ?? 0)
    const ct         = overrideCurrentTime ?? currentTime.value
    const key        = `${cur.episodeSlug}|${chapterTs}`
    const chapters   = cur.chapters ?? []
    const chIdx      = chapters.findIndex(ch => ch.timestampSeconds === chapterTs)
    const nextCh     = chIdx >= 0 ? chapters[chIdx + 1] : null
    const chapterEnd = nextCh ? nextCh.timestampSeconds : audioDuration.value
    progressMap.value = _pruneProgressMap({
      ...progressMap.value,
      [key]: {
        currentTime: ct,
        chapterEnd,
        gameSlug: cur.slug,
        ts:       chapterTs,
        savedAt:  Date.now(),
      },
    })
    _saveProgressMap()
  }

  let _progressTimer = null
  watch(currentTime, () => {
    clearTimeout(_progressTimer)
    _progressTimer = setTimeout(_updateProgress, 5000)
  })

  watch(currentChapter, (newCh, oldCh) => {
    if (!oldCh || !current.value) return
    // When play() swapped tracks, this firing's oldCh belongs to the *previous*
    // track — writing it would mix the new episode's slug with the old chapter's
    // timestamp. Only a chapter of the current track may be finalized here.
    if (!current.value.chapters?.includes(oldCh)) return
    _updateProgress(oldCh.timestampSeconds, currentTime.value)
  })

  function updateGameSlug(oldSlug, newSlug) {
    if (current.value?.slug === oldSlug)
      current.value = { ...current.value, slug: newSlug }
    const stale = Object.entries(progressMap.value).filter(([, v]) => v.gameSlug === oldSlug)
    if (stale.length) {
      progressMap.value = {
        ...progressMap.value,
        ...Object.fromEntries(stale.map(([k, v]) => [k, { ...v, gameSlug: newSlug }])),
      }
      _saveProgressMap()
    }
  }

  // Always-current live snapshot — Pinia computed, so guaranteed reactive.
  const liveProgress = computed(() => {
    if (!current.value || audioDuration.value <= 0) return null
    const chapterTs  = currentChapter.value?.timestampSeconds ?? 0
    const chapters   = current.value.chapters ?? []
    const chIdx      = chapters.findIndex(ch => ch.timestampSeconds === chapterTs)
    const nextCh     = chIdx >= 0 ? chapters[chIdx + 1] : null
    const chapterEnd = nextCh ? nextCh.timestampSeconds : audioDuration.value
    return {
      gameSlug:    current.value.slug,
      chapterSlug: currentChapter.value?.slug ?? null,
      episodeSlug: current.value.episodeSlug,
      chapterTs,
      chapterEnd,
      pct: progressPct(currentTime.value, chapterTs, chapterEnd),
    }
  })

  function getEpisodeProgress(episodeSlug, ts) {
    return progressMap.value[`${episodeSlug}|${ts ?? 0}`] ?? null
  }

  function getGameProgress(gameSlug) {
    const entries = Object.values(progressMap.value).filter(e => e.gameSlug === gameSlug)
    if (!entries.length) return null
    return entries.sort((a, b) => b.savedAt - a.savedAt)[0]
  }

  // The time to start playback at for a given chapter/episode start: the saved
  // position when partway through (>= MIN, < DONE), else the start (restart).
  function resumeTimeFor(episodeSlug, startTs = 0) {
    const saved = getEpisodeProgress(episodeSlug, startTs)
    if (saved?.chapterEnd) {
      const pct = progressPct(saved.currentTime, startTs, saved.chapterEnd)
      if (pct >= PROGRESS_MIN_PCT && pct < PROGRESS_DONE_PCT) return saved.currentTime
    }
    return startTs
  }

  // The most-recently-saved progress entry for this episode (any chapter), or null.
  function getEpisodeLatestProgress(episodeSlug) {
    const prefix  = `${episodeSlug}|`
    const entries = Object.entries(progressMap.value)
      .filter(([k]) => k.startsWith(prefix)).map(([, v]) => v)
    if (!entries.length) return null
    return entries.sort((a, b) => (b.savedAt ?? 0) - (a.savedAt ?? 0))[0]
  }

  // ── Persistence ─────────────────────────────────────────────────────────────
  const STORAGE_KEY = 'soj-player'

  function _save() {
    if (!current.value) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, JSON.stringify({
      current:     current.value,
      currentTime: currentTime.value,
    }))
  }

  let _saveTimer = null
  watch(current, () => { clearTimeout(_saveTimer); _save() })
  watch(currentTime, () => {
    clearTimeout(_saveTimer)
    _saveTimer = setTimeout(_save, 5000)
  })
  function _saveNow() { clearTimeout(_saveTimer); _save() }
  window.addEventListener('pagehide', _saveNow)
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') _saveNow()
  })

  return {
    current, visible, currentTime, currentChapter, audioDuration, restored,
    status, paused, buffering, failed, volume,
    play, close, restore, setEpisodeImageUrl,
    resume, pauseAudio, togglePlayback, seek, retry, setVolume,
    updateGameSlug, liveProgress, getEpisodeProgress, getGameProgress,
    resumeTimeFor, getEpisodeLatestProgress,
  }
})
