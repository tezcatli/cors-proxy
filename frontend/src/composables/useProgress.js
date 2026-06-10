import { usePlayerStore } from '../stores/player.js'
import { progressPct, PROGRESS_DONE_PCT } from '../lib/utils.js'

// One live-aware progress reader for every consumer (game tiles, episode rows,
// chapter rows). Each helper checks the store's reactive `liveProgress` for the
// currently-playing target first, then falls back to the stored map. Returns
// `{ pct, done }`; both helpers read `liveProgress` internally, so they stay
// reactive whether called inside a `computed` or directly in a `v-for` template.
export function useProgress() {
  const player = usePlayerStore()

  const result = (pct) => ({ pct, done: pct >= PROGRESS_DONE_PCT })

  function episodeProgress(episodeSlug, chapterTs = 0) {
    const live = player.liveProgress
    if (live?.episodeSlug === episodeSlug && live.chapterTs === chapterTs) return result(live.pct)
    const p = player.getEpisodeProgress(episodeSlug, chapterTs)
    if (!p?.chapterEnd) return result(0)
    return result(progressPct(p.currentTime, p.ts ?? 0, p.chapterEnd))
  }

  function gameProgress(gameSlug) {
    const live = player.liveProgress
    if (live && (live.chapterSlug === gameSlug || live.gameSlug === gameSlug)) return result(live.pct)
    const p = player.getGameProgress(gameSlug)
    if (!p?.chapterEnd) return result(0)
    return result(progressPct(p.currentTime, p.ts ?? 0, p.chapterEnd))
  }

  return { episodeProgress, gameProgress }
}
