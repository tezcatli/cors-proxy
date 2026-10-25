import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { progressPct, PROGRESS_MIN_PCT, PROGRESS_DONE_PCT } from '../lib/utils.js'
import { createAudioEngine } from '../lib/audioEngine.js'
import { fetchEpisodeDetail } from '../lib/games.js'
import { testAt } from '../lib/timeline.js'

// Track metadata, listening progress, and the only driver of `lib/audioEngine.js`:
// components issue commands (play, resume, pauseAudio, togglePlayback, seek, retry,
// setVolume, close) and never touch the element. Two localStorage keys:
// `soj-player`, the resumable snapshot restored *paused* on load (`restore`, which
// sets `restored` for the player's resume cue), and `soj-progress`, per
// `${episodeSlug}|${chapterTs}`, written on a 5 s debounce, on chapter change, on
// play and on close, pruned to 180 days and the newest 500. `resumeTimeFor` is the
// one tap-resume rule: partway through a chapter → its saved time, else its start.

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
  const rate   = ref(1)

  const engine = createAudioEngine({
    onState(s) {
      status.value        = s.status
      intent.value        = s.intent
      currentTime.value   = s.position
      audioDuration.value = s.duration
      volume.value        = s.volume
      rate.value          = s.rate
      if (s.status === 'playing') restored.value = false
    },
  })

  // `paused` follows *intent*, so a tap flips the icon immediately; `buffering`
  // is the gap between intent and reality, and `failed` is where that gap stops
  // being temporary (see lib/audioEngine.js).
  // The listener's speed outlives tracks and reloads (`soj-rate`).
  try { engine.setRate(parseFloat(localStorage.getItem('soj-rate')) || 1) } catch (_) {}
  function setRate(r) {
    engine.setRate(r)
    try { localStorage.setItem('soj-rate', String(rate.value)) } catch (_) {}
  }

  const paused    = computed(() => intent.value !== 'play')
  const buffering = computed(() => intent.value === 'play' && status.value !== 'playing')
  const failed    = computed(() => status.value === 'failed')

  function play({ game, slug, episode, url, ts = 0, timestamp = null, episodeImageUrl = null, pubTs = null, episodeSlug = null, episodeUrlSlug = null, coverImageId = null, chapters = null, podcast = null, tests = null }) {
    clearTimeout(_progressTimer)
    _updateProgress()
    restored.value = false
    current.value = { game, slug: slug ?? game, episode, url, ts, timestamp, episodeImageUrl, pubTs, episodeSlug, episodeUrlSlug, coverImageId, podcast, chapters: chapters ?? [], tests: tests ?? [] }
    visible.value = true
    engine.load({ url, at: ts }, { autoplay: true })
    if (!chapters?.length) _loadChapters(url, episodeUrlSlug ?? episodeSlug)
  }

  // A track started from a list (which carries no chapters) gets them from the
  // episode's detail: what is on air, and progress, go by chapter.
  async function _loadChapters(url, slug) {
    if (!slug) return
    try {
      const ep = await fetchEpisodeDetail(slug)
      if (current.value?.url !== url || !ep?.chapters?.length) return
      current.value = { ...current.value, chapters: ep.chapters, tests: ep.games ?? current.value.tests }
    } catch (_) {}
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

  // The episode's tests in order — its review starts — or, for an unread
  // episode, its chapters: what « test suivant / précédent » jumps between.
  const marks = computed(() => {
    const cur = current.value
    const tests = (cur?.tests ?? []).filter(t => t.timestampSeconds != null)
    const list  = tests.length ? tests : (cur?.chapters ?? [])
    return [...list].sort((a, b) => a.timestampSeconds - b.timestampSeconds)
  })

  // The test on air, by position (`testAt`, lib/timeline.js).
  const currentTest = computed(() => (current.value ? testAt(current.value, currentTime.value) : null))

  // What is on air — the one rule the player and the lock screen follow
  // (DECISIONS.md, « Interface »): the test's cover and game, else the
  // podcast's image and the chapter (or the episode). Never the game the track
  // was started for.
  const onAir = computed(() => {
    const cur = current.value
    if (!cur) return null
    const test = currentTest.value
    return {
      test,
      coverImageId: test?.coverImageId ?? null,
      imageUrl:     cur.episodeImageUrl ?? null,
      title:        test ? (test.resolvedName ?? test.name) : (currentChapter.value?.title || cur.episode || ''),
    }
  })

  // Back within the first seconds of a mark goes to the one before, as on a CD.
  const BACK_GRACE = 4
  function skip(dir) {
    const t = currentTime.value
    const list = marks.value
    if (dir > 0) {
      const next = list.find(m => m.timestampSeconds > t + 1)
      if (next) seek(next.timestampSeconds)
    } else {
      const prev = [...list].reverse().find(m => m.timestampSeconds < t - BACK_GRACE)
      seek(prev ? prev.timestampSeconds : 0)
    }
  }

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

  // Where an episode is to resume: its latest saved position, while partway
  // through its chapter; null when untouched or that chapter is done.
  function resumeEntryFor(episodeSlug) {
    const e = getEpisodeLatestProgress(episodeSlug)
    if (!e?.chapterEnd) return null
    const pct = progressPct(e.currentTime, e.ts ?? 0, e.chapterEnd)
    return (pct >= PROGRESS_MIN_PCT && pct < PROGRESS_DONE_PCT) ? e : null
  }

  // Episodes started and not finished, most recent first (one entry each): the
  // home's « Reprendre » shelf.
  const inProgress = computed(() => {
    const seen = new Set()
    return Object.entries(progressMap.value)
      .map(([k, v]) => ({ ...v, episodeSlug: k.slice(0, k.lastIndexOf('|')) }))
      .filter(e => {
        if (!e.chapterEnd) return false
        const pct = progressPct(e.currentTime, e.ts ?? 0, e.chapterEnd)
        return pct >= PROGRESS_MIN_PCT && pct < PROGRESS_DONE_PCT
      })
      .sort((a, b) => (b.savedAt ?? 0) - (a.savedAt ?? 0))
      .filter(e => !seen.has(e.episodeSlug) && seen.add(e.episodeSlug))
  })

  // Forget where an episode was left (« Reprendre »'s ×): it is no longer in
  // progress anywhere, and its next listening starts at its test.
  function forgetEpisode(episodeSlug) {
    const prefix = `${episodeSlug}|`
    progressMap.value = Object.fromEntries(Object.entries(progressMap.value).filter(([k]) => !k.startsWith(prefix)))
    _saveProgressMap()
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
    status, paused, buffering, failed, volume, rate, marks, currentTest, onAir,
    play, close, restore, setEpisodeImageUrl,
    resume, pauseAudio, togglePlayback, seek, retry, setVolume, setRate, skip,
    liveProgress, getEpisodeProgress, getGameProgress,
    resumeTimeFor, getEpisodeLatestProgress, resumeEntryFor, inProgress, forgetEpisode,
  }
})
