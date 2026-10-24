// The hosts' verdict on a test (`llm.VERDICTS` on the backend), told by its word
// alone, never by a colour or a glyph (DECISIONS.md, « Interface »). `null`
// covers both an unread episode and a reading where nobody gave a verdict, and
// shows nothing.
export const VERDICTS = {
  positive: { label: 'Positif' },
  mixed:    { label: 'Mitigé' },
  negative: { label: 'Négatif' },
}

export function verdictMeta(verdict) {
  return VERDICTS[verdict] ?? null
}

/** Counts per verdict, in display order, for a game's tests. */
export function verdictCounts(verdicts = []) {
  const counts = { positive: 0, mixed: 0, negative: 0, none: 0 }
  for (const v of verdicts) counts[VERDICTS[v] ? v : 'none']++
  return counts
}
