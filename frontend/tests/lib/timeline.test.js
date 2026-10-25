import { describe, it, expect } from 'vitest'
import { episodeTimeline } from '../../src/lib/timeline.js'

// SoJ S20E07, as served in dev: the feed's chapters, the tests at their critique.
const ch = (timestamp, timestampSeconds, title) => ({ timestamp, timestampSeconds, title })
const CHAPTERS = [
  ch('0:00', 0, 'Intro'),
  ch('33:19', 1999, 'Le com des coms'),
  ch('45:19', 2719, 'Warhammer 40,000: Boltgun 2'),
  ch('1:07:42', 4062, 'Star Wars Galactic Racer'),
  ch('1:37:00', 5820, 'La minute culturelle'),
]
const t = (name, timestamp, timestampSeconds, resolvedName) => ({ name, timestamp, timestampSeconds, resolvedName })
const DAWN   = t('The Blood of Dawnwalker', '39:23', 2363)
const BOLT   = t('Warhammer 40,000: Boltgun 2', '00:45:44', 2744)
const RACER  = t('Star Wars Galactic Racer', '01:08:21', 4101, 'Star Wars: Galactic Racer')
const shape = rows => rows.map(r => (r.kind === 'test' ? `T ${r.test.name}` : `C ${r.chapter.title}`))

describe('episodeTimeline', () => {
  it('puts each test once, in time, replacing the chapter that bears its name', () => {
    expect(shape(episodeTimeline(CHAPTERS, [RACER, BOLT, DAWN]))).toEqual([
      'C Intro',
      'C Le com des coms', 'T The Blood of Dawnwalker',   // a chapter on something else stays
      'T Warhammer 40,000: Boltgun 2',
      'T Star Wars Galactic Racer',
      'C La minute culturelle',
    ])
  })

  it('counts a start a few seconds before a chapter as that chapter’s', () => {
    const early = t('Star Wars Galactic Racer', '01:07:30', 4050)
    expect(shape(episodeTimeline(CHAPTERS, [early]))).toContain('T Star Wars Galactic Racer')
    expect(shape(episodeTimeline(CHAPTERS, [early]))).not.toContain('C Star Wars Galactic Racer')
  })

  it('closes the list with a test of no known start', () => {
    const rows = shape(episodeTimeline(CHAPTERS, [t('Planet Zoo 2', null, 0)]))
    expect(rows.at(-1)).toBe('T Planet Zoo 2')
    expect(rows).toHaveLength(CHAPTERS.length + 1)
  })

  it('lists the tests alone in an episode without chapters', () => {
    expect(shape(episodeTimeline([], [RACER, DAWN]))).toEqual(['T The Blood of Dawnwalker', 'T Star Wars Galactic Racer'])
  })
})
