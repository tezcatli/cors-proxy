// The hosts' verdict on a test (`llm.VERDICTS` on the backend), told by a glyph
// and a word, never by a colour alone (DECISIONS.md, « Interface »). `null`
// covers both an unread episode and a reading where nobody gave a verdict.
export const VERDICTS = {
  positive: { glyph: '▲', label: 'Positif' },
  mixed:    { glyph: '◆', label: 'Mitigé' },
  negative: { glyph: '▼', label: 'Négatif' },
}
export const NO_VERDICT = { glyph: '○', label: 'Non lu' }

export function verdictMeta(verdict) {
  return VERDICTS[verdict] ?? NO_VERDICT
}

/** Counts per verdict, in display order, for a game's tests. */
export function verdictCounts(verdicts = []) {
  const counts = { positive: 0, mixed: 0, negative: 0, none: 0 }
  for (const v of verdicts) counts[VERDICTS[v] ? v : 'none']++
  return counts
}
