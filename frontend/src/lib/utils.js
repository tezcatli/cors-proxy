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
