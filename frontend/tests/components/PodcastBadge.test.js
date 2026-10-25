import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PodcastBadge from '../../src/components/PodcastBadge.vue'

describe('PodcastBadge', () => {
  it('names a podcast by its short label, and an unknown one not at all', () => {
    const w = mount(PodcastBadge, { props: { id: 'fin-du-game' } })
    expect([w.text(), w.attributes('title')]).toEqual(['FDG', 'Fin du Game'])
    expect(mount(PodcastBadge, { props: { id: 'nope' } }).text()).toBe('')
  })
})
