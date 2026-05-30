import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick, h } from 'vue'
import { useInfiniteScroll } from '../../src/composables/useInfiniteScroll.js'

// Minimal IntersectionObserver fake that lets tests trigger intersection.
let observers
class FakeIO {
  constructor(cb) { this.cb = cb; this.elements = new Set(); observers.push(this) }
  observe(el)     { this.elements.add(el) }
  unobserve(el)   { this.elements.delete(el) }
  disconnect()    { this.elements.clear() }
  trigger(isIntersecting = true) {
    this.cb([{ isIntersecting, target: [...this.elements][0] }])
  }
}

beforeEach(() => {
  observers = []
  vi.stubGlobal('IntersectionObserver', FakeIO)
})
afterEach(() => { vi.unstubAllGlobals() })

const range = n => Array.from({ length: n }, (_, i) => i)

function mountWith(items, opts) {
  let api
  const wrapper = mount({
    setup() {
      api = useInfiniteScroll(items, opts)
      return () => h('div', [
        ...api.visibleItems.value.map(i => h('span', String(i))),
        h('div', { ref: api.sentinel }),
      ])
    },
  })
  return { wrapper, api }
}

const lastObserver = () => observers[observers.length - 1]

describe('useInfiniteScroll', () => {
  it('shows only the first page initially', () => {
    const { api } = mountWith(ref(range(25)), { pageSize: 10 })
    expect(api.visibleItems.value).toHaveLength(10)
  })

  it('reveals the next page when the sentinel intersects', async () => {
    const { api } = mountWith(ref(range(25)), { pageSize: 10 })
    await nextTick()
    lastObserver().trigger(true)
    await nextTick()
    expect(api.visibleItems.value).toHaveLength(20)
  })

  it('never reveals more items than exist', async () => {
    const { api } = mountWith(ref(range(15)), { pageSize: 10 })
    await nextTick()
    lastObserver().trigger(true)   // 10 → 20, but only 15 items
    await nextTick()
    expect(api.visibleItems.value).toHaveLength(15)
  })

  it('resets to the first page when the list reference changes', async () => {
    const items = ref(range(25))
    const { api } = mountWith(items, { pageSize: 10 })
    await nextTick()
    lastObserver().trigger(true)
    await nextTick()
    expect(api.visibleItems.value).toHaveLength(20)

    items.value = range(30)        // new reference → reset
    await nextTick()
    expect(api.visibleItems.value).toHaveLength(10)
  })

  it('resets on an explicit resetKey change, not the list itself', async () => {
    const items    = ref(range(25))
    const resetKey = ref('a')
    const { api } = mountWith(items, { pageSize: 10, resetKey: () => resetKey.value })
    await nextTick()
    lastObserver().trigger(true)
    await nextTick()
    expect(api.visibleItems.value).toHaveLength(20)

    resetKey.value = 'b'
    await nextTick()
    expect(api.visibleItems.value).toHaveLength(10)
  })
})
