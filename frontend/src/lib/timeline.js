// An episode's timeline (DECISIONS.md, « Interface »): its chapters in order,
// its tests among them, each once. A test starts in the chapter its start falls
// in — up to SNAP seconds before it counts, the transcript's clock running ahead
// of the feed's (`testAt` below, `serializers._chapter_resolutions`). A
// chapter that bears the test's name *is* the test: the test's row takes its
// place. A chapter on something else (« Le com des coms ») stays, the test right
// under it. A test with no known start closes the list.

const SNAP = 30

const norm = s => (s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '')
  .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

/** Whether a chapter's title names the test's game. */
function bears(chapter, test) {
  const title = norm(chapter.title)
  if (title.length < 3) return false
  return [test.name, test.resolvedName].map(norm).filter(Boolean)
    .some(n => title.includes(n) || n.includes(title))
}

/**
 * Rows: `{kind: 'chapter', chapter}` or `{kind: 'test', test, chapter}` — the
 * chapter a test starts in (null without chapters, or without a start).
 */
export function episodeTimeline(chapters = [], tests = []) {
  const timed   = tests.filter(t => t.timestamp != null).sort((a, b) => a.timestampSeconds - b.timestampSeconds)
  const untimed = tests.filter(t => t.timestamp == null).map(test => ({ kind: 'test', test, chapter: null }))
  if (!chapters.length) return [...timed.map(test => ({ kind: 'test', test, chapter: null })), ...untimed]

  const within = chapters.map(() => [])
  for (const t of timed) {
    let i = 0
    while (i + 1 < chapters.length && chapters[i + 1].timestampSeconds - SNAP <= t.timestampSeconds) i++
    within[i].push(t)
  }
  const rows = []
  chapters.forEach((chapter, i) => {
    const own = within[i].find(t => bears(chapter, t))
    if (!own) rows.push({ kind: 'chapter', chapter })
    for (const test of within[i]) rows.push({ kind: 'test', test, chapter })
  })
  return [...rows, ...untimed]
}

/**
 * The test on air at `time` in a track (`{tests, chapters}`) — the one rule the
 * player, the lock screen and « Reprendre » follow (DECISIONS.md, « Interface »):
 * the last test started within the chapter playing; else the test whose page
 * that chapter carries (the chapter a test starts in, the one it goes on in
 * after an ad); else none — a chapter on anything else is no test's. Without
 * chapters, the last test started. A test with no known start is never on air.
 */
export function testAt({ tests = [], chapters = [] }, time) {
  let ch = null
  for (const c of chapters) {
    if (c.timestampSeconds <= time) ch = c
    else break
  }
  const from = chapters.length ? (ch ? ch.timestampSeconds - SNAP : Infinity) : -Infinity
  let active = null
  for (const t of tests) {
    if (t.timestamp == null || t.timestampSeconds < from || t.timestampSeconds > time) continue
    if (!active || t.timestampSeconds >= active.timestampSeconds) active = t
  }
  if (active || !ch?.slug) return active
  return tests.find(t => t.slug === ch.slug)
    ?? { name: ch.title, resolvedName: ch.resolvedName, slug: ch.slug, coverImageId: ch.coverImageId, timestampSeconds: ch.timestampSeconds }
}
