import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PodcastBadge from '../../src/components/PodcastBadge.vue'

describe('PodcastBadge', () => {
  it('renders the short label by default', () => {
    const w = mount(PodcastBadge, { props: { id: 'fin-du-game' } })
    expect(w.text()).toBe('FDG')
    expect(w.attributes('title')).toBe('Fin du Game')
  })

  it('renders the full name when `full` is set', () => {
    const w = mount(PodcastBadge, { props: { id: 'silence-on-joue', full: true } })
    expect(w.text()).toBe('Silence on Joue')
  })

  it('renders nothing for an unknown podcast id', () => {
    const w = mount(PodcastBadge, { props: { id: 'nope' } })
    expect(w.find('.podcast-badge').exists()).toBe(false)
  })
})
