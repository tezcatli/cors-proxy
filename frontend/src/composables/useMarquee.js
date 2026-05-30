import { ref, watch, nextTick, onUnmounted } from 'vue'

/**
 * Detects whether the inner content of a marquee element overflows its box and
 * therefore needs to scroll. Re-checks on element resize and whenever
 * `watchSource` changes (e.g. the displayed label).
 *
 * @param elRef        template ref to the marquee container (its first child is
 *                     the measured inner element).
 * @param watchSource  optional ref/getter that re-triggers the overflow check.
 * @returns `{ needsScroll, check }`
 */
export function useMarquee(elRef, watchSource = null) {
  const needsScroll = ref(false)
  let resizeObs = null

  async function check() {
    await nextTick()
    const el = elRef.value
    if (!el) { needsScroll.value = false; return }
    const inner = el.firstElementChild
    needsScroll.value = inner ? inner.offsetWidth > el.clientWidth : false
  }

  watch(elRef, el => {
    resizeObs?.disconnect()
    resizeObs = null
    if (el) {
      resizeObs = new ResizeObserver(check)
      resizeObs.observe(el)
      check()
    }
  })

  if (watchSource) watch(watchSource, check)

  onUnmounted(() => resizeObs?.disconnect())

  return { needsScroll, check }
}
