import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import MediaViewer from '../../src/components/MediaViewer.vue'

// The cover, the trailer, then eight screenshots: ten media.
const ITEMS = [
  { kind: 'image', id: 'cover' },
  { kind: 'video', id: 'yt123' },
  ...Array.from({ length: 8 }, (_, i) => ({ kind: 'image', id: `shot${i}` })),
]

let w
const open = props => (w = mount(MediaViewer, { props: { items: ITEMS, ...props }, attachTo: document.body }))
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

const q     = sel => document.querySelector(sel)
const count = () => q('.viewer__count').textContent.trim()
const key   = k => { document.dispatchEvent(new KeyboardEvent('keydown', { key: k })); return nextTick() }

describe('MediaViewer', () => {
  it('opens on the medium touched', () => {
    open({ start: 3 })
    expect(count()).toBe('4 / 10')
  })

  it('passes to the next and the previous, and stops at the ends', async () => {
    open({ start: 8 })
    await key('ArrowRight')
    expect(count()).toBe('10 / 10')
    await key('ArrowRight')
    expect(count()).toBe('10 / 10')              // no wrapping round: a swipe stops at the end
    expect(q('.viewer__next')).toBeNull()
    q('.viewer__prev').click()
    await nextTick()
    expect(count()).toBe('9 / 10')
  })

  it('loads the image shown and its neighbours only', () => {
    open({ start: 5 })
    const srcs = [...document.querySelectorAll('.viewer__img')].map(i => i.getAttribute('src'))
    expect(srcs).toHaveLength(3)
    expect(srcs.join()).toContain('shot2')
    expect(srcs.join()).toContain('shot4')
  })

  it('plays the trailer once asked, and stops it when left', async () => {
    open({ start: 1 })
    expect(q('iframe')).toBeNull()
    q('.viewer__poster').click()
    await nextTick()
    expect(q('iframe').getAttribute('src')).toContain('yt123')
    await key('ArrowRight')
    expect(q('iframe')).toBeNull()
  })

  it('plays the trailer at once when opened from it', () => {
    open({ start: 1, autoplay: true })
    expect(q('iframe')).not.toBeNull()
  })

  it('closes on Escape', async () => {
    open({ start: 0 })
    await key('Escape')
    expect(w.emitted('close')).toHaveLength(1)
  })
})
