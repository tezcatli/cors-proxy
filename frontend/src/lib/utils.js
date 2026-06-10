export function formatDate(ts) {
  if (!ts) return '';
  try { return new Date(ts * 1000).toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' }); }
  catch { return String(ts); }
}

export function timeAgo(iso) {
  if (!iso) return '';
  const mins = Math.floor((Date.now() - new Date(iso)) / 60000);
  if (mins < 2)  return 'à l\'instant';
  if (mins < 60) return `il y a ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `il y a ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `il y a ${days} jour${days > 1 ? 's' : ''}`;
}

export function getScoreClass(score) {
  return score >= 75 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';
}

export function formatEpisodeCount(n) {
  return `${n} épisode${n > 1 ? 's' : ''}`;
}

/**
 * Percentage (0–100) of a chapter that has been listened to.
 * Returns 0 when the span is non-positive. Shared by the player store's
 * live progress and the stored-progress readouts in the views.
 */
export function progressPct(currentTime, start, end) {
  const span = end - start;
  if (span <= 0) return 0;
  return Math.min(100, Math.max(0, ((currentTime - start) / span) * 100));
}

// Progress-bar thresholds (shared by useProgress + the views).
export const PROGRESS_MIN_PCT  = 2;    // below this we hide the bar (noise)
export const PROGRESS_DONE_PCT = 95;   // at/above this it reads as "listened"

/**
 * Seconds → `m:ss`, widening to `h:mm:ss` past an hour. Guards NaN/Infinity
 * (an unloaded <audio> reports those) → '0:00'.
 */
export function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const s = Math.floor(seconds % 60);
  const m = Math.floor(seconds / 60) % 60;
  const h = Math.floor(seconds / 3600);
  const pad = n => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}
