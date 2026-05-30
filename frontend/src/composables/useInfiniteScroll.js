import { ref, computed, watch, nextTick, onUnmounted, toValue } from 'vue'

/**
 * Incremental "infinite scroll" rendering driven by an IntersectionObserver.
 *
 * @param items     a ref/getter returning the full list to page through.
 * @param pageSize  how many items to reveal per page (and the initial count).
 * @param resetKey  optional ref/getter; when its value changes the visible
 *                  count resets to `pageSize`. Defaults to `items` itself, so a
 *                  new list reference (e.g. a recomputed filter) resets paging.
 *
 * Returns `{ visibleItems, sentinel }` — bind `sentinel` to a trailing element
 * after the rendered list; observing it reveals the next page on scroll.
 */
export function useInfiniteScroll(items, { pageSize = 50, resetKey = null } = {}) {
  const visibleCount = ref(pageSize)
  const sentinel     = ref(null)
  let _observer      = null

  const visibleItems = computed(() => toValue(items).slice(0, visibleCount.value))

  watch(() => toValue(resetKey ?? items), () => {
    visibleCount.value = pageSize
    nextTick(() => {
      if (_observer && sentinel.value) {
        _observer.unobserve(sentinel.value)
        _observer.observe(sentinel.value)
      }
    })
  })

  watch(sentinel, el => {
    _observer?.disconnect()
    if (!el) return
    _observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting || visibleCount.value >= toValue(items).length) return
      _observer.unobserve(entry.target)
      visibleCount.value += pageSize
      nextTick(() => { if (sentinel.value) _observer.observe(sentinel.value) })
    })
    _observer.observe(el)
  })

  // The IntersectionObserver won't re-fire on its own if the sentinel was already
  // in view when the list was still short (e.g. armed during loading, or when the
  // reset key — not `items` — is what's being watched above). Re-observe when the
  // list grows so it re-evaluates and fills the viewport past the first page.
  watch(() => toValue(items).length, () => {
    if (_observer && sentinel.value) {
      _observer.unobserve(sentinel.value)
      nextTick(() => { if (_observer && sentinel.value) _observer.observe(sentinel.value) })
    }
  })

  onUnmounted(() => _observer?.disconnect())

  return { visibleItems, sentinel }
}
