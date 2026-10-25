export function formatDate(ts) {
  if (!ts) return '';
  try { return new Date(ts * 1000).toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' }); }
  catch { return String(ts); }
}

/** Unix seconds → `02.10.2026`, the mono date of rows and tables. */
export function formatShortDate(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

/** « 22 oct. »: a date within a year already said (an intertitle, a row). */
export function formatDayMonth(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
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

/**
 * A length in seconds → `18 min`, `1 h 05` past an hour; '' when unknown.
 */
export function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const minutes = Math.max(1, Math.round(seconds / 60));
  const h = Math.floor(minutes / 60);
  return h > 0 ? `${h} h ${String(minutes % 60).padStart(2, '0')}` : `${minutes} min`;
}

/**
 * Where a test ({ep, test}) leads: its game's page, its tests folded, else — a
 * game without a page — its episode.
 */
export function testHref({ ep, test }) {
  return test.slug
    ? `/game/${encodeURIComponent(test.slug)}`
    : `/episode/${encodeURIComponent(ep.urlSlug)}`;
}

/**
 * The track `playerStore.play` takes for an episode — a list's or a detail's
 * payload — entered at `ts`: its test's start, a saved position, or 0 for the
 * whole episode. One shape, whatever starts the listening (DECISIONS.md,
 * « Interface » : une seule écoute). A list's episode has no chapters: the
 * player loads them.
 */
export function episodeTrack(ep, { test = null, ts = 0 } = {}) {
  return {
    game:            test ? (test.resolvedName ?? test.name) : ep.title,
    slug:            test?.slug ?? null,
    episode:         ep.title,
    url:             ep.audioUrl,
    ts,
    timestamp:       test?.timestamp ?? null,
    episodeImageUrl: ep.imageUrl ?? null,
    pubTs:           ep.pubTs ?? null,
    episodeSlug:     ep.slug,
    episodeUrlSlug:  ep.urlSlug ?? null,
    coverImageId:    test?.coverImageId ?? null,
    chapters:        ep.chapters ?? [],
    podcast:         ep.podcast ?? null,
    tests:           ep.games ?? [],
  };
}
