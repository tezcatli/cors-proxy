import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import LabPanel from '../../src/components/LabPanel.vue'
import { fetchLabEpisode, setLabJudgment } from '../../src/lib/games.js'

const VIEW = {
  episode: 'bes-control', title: 'Control Resonant Rewards Your Patience', podcast: 'the-besties', read: true,
  games: [
    { game: 'Control Resonant', attached: true, source: 'lecture', kind: 'review', minutes: 27, start: 240,
      verdict: 'positive', igdb: { slug: 'control-resonant', name: 'Control Resonant', released: '2026-09-01' },
      judgment: null },
    { game: 'A Normal Golf Game', attached: false, source: 'lecture', kind: 'mention', minutes: 1.5,
      start: 2750, igdb: null, judgment: 'évoqué' },
  ],
}

vi.mock('../../src/lib/games.js', () => ({
  fetchLabEpisode: vi.fn(),
  setLabJudgment: vi.fn(),
}))

beforeEach(() => {
  fetchLabEpisode.mockReset().mockResolvedValue(VIEW)
  setLabJudgment.mockReset().mockImplementation((ep, game, verdict) => Promise.resolve({
    ...VIEW, games: VIEW.games.map(g => g.game === game ? { ...g, judgment: verdict } : g),
  }))
})

describe('LabPanel', () => {
  it('lists what the pipeline sees, attached first, with what decided it', async () => {
    const w = mount(LabPanel, { props: { episodeSlug: 'bes-control' } })
    await flushPromises()
    const rows = w.findAll('.lab__row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('rattaché')
    expect(rows[0].text()).toContain('critique')
    expect(rows[1].text()).toContain('non rattaché')
    expect(w.text()).toContain('1/2 jugés')
  })

  it('records a judgment, and a second click on it withdraws it', async () => {
    const w = mount(LabPanel, { props: { episodeSlug: 'bes-control' } })
    await flushPromises()
    await w.findAll('.lab__row')[0].findAll('.lab__verdict')[0].trigger('click')   // Consacré
    await flushPromises()
    expect(setLabJudgment).toHaveBeenCalledWith('bes-control', 'Control Resonant', 'consacré', 'control-resonant')
    await w.findAll('.lab__row')[1].findAll('.lab__verdict')[1].trigger('click')   // Évoqué, already on
    expect(setLabJudgment).toHaveBeenLastCalledWith('bes-control', 'A Normal Golf Game', null, undefined)
  })

  it('renders nothing where the lab is not there', async () => {
    fetchLabEpisode.mockRejectedValue(new Error('404'))
    const w = mount(LabPanel, { props: { episodeSlug: 'x' } })
    await flushPromises()
    expect(w.find('.lab').exists()).toBe(false)
  })

  it('plays from the section start', async () => {
    const w = mount(LabPanel, { props: { episodeSlug: 'bes-control' } })
    await flushPromises()
    await w.find('.lab__play').trigger('click')
    expect(w.emitted('play')[0]).toEqual([240])
  })
})
