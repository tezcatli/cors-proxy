import { ref, watch, onUnmounted } from 'vue'

// A swipe on a touch screen: the element follows the finger along one axis and,
// released past `commitAt(dir)` pixels or flicked faster than FLICK, commits.
// Touch events, not pointer events: only they let a gesture be claimed after it
// started (`preventDefault` on the move), so a scrolled sheet still scrolls and
// is pulled down only from its top.
//
//   const { offset, dragging } = useSwipe(elRef, {
//     directions: ['down'],          // 'up' | 'down' | 'left' | 'right'
//     commitAt: dir => px,           // distance that commits
//     ignore: '.seek',               // a gesture starting inside it is not a swipe
//     scroller: () => el,            // 'down' only while it is scrolled to the top
//     onCommit: dir => {},
//   })
//
// `offset` is the signed distance along the chosen axis ({ x, y }); a tap stays
// a tap (SLOP), and the click a drag ends on is swallowed.
const SLOP = 10       // px before the axis is chosen
const FLICK = 0.5     // px/ms

export function useSwipe(elRef, { directions, commitAt, ignore = null, scroller = null, onCommit }) {
  const offset   = ref({ x: 0, y: 0 })
  const dragging = ref(false)

  let start = null       // { x, y }
  let dir = null         // chosen direction, null until SLOP
  let last = null        // { d, t } — the latest sample, for the flick speed
  let prev = null

  const along = (dx, dy) => (dir === 'left' || dir === 'right' ? dx : dy)

  function onStart(e) {
    if (e.touches.length !== 1 || (ignore && e.target.closest?.(ignore))) { start = null; return }
    start = { x: e.touches[0].clientX, y: e.touches[0].clientY }
    dir = null
    last = prev = null
  }

  function onMove(e) {
    if (!start) return
    const dx = e.touches[0].clientX - start.x
    const dy = e.touches[0].clientY - start.y
    if (!dir) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < SLOP) return
      const chosen = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up')
      const horizontal = chosen === 'left' || chosen === 'right'
      // Left and right are one axis: once horizontal, either way follows.
      const allowed = directions.includes(chosen)
        || (horizontal && directions.some(d => d === 'left' || d === 'right'))
      if (!allowed || (chosen === 'down' && scroller && scroller()?.scrollTop > 0)) { start = null; return }
      dir = chosen
      dragging.value = true
    }
    e.preventDefault()
    let d = along(dx, dy)
    if (dir === 'down') d = Math.max(0, d)
    if (dir === 'up') d = Math.min(0, d)
    if (dir === 'left' || dir === 'right') {
      const ways = directions.filter(w => w === 'left' || w === 'right')
      if (ways.length === 1) d = ways[0] === 'right' ? Math.max(0, d) : Math.min(0, d)
    }
    prev = last
    last = { d, t: e.timeStamp || performance.now() }
    offset.value = (dir === 'left' || dir === 'right') ? { x: d, y: 0 } : { x: 0, y: d }
  }

  function onEnd() {
    if (!start) return
    start = null
    if (!dragging.value) return
    dragging.value = false
    swallowClick()
    const d = along(offset.value.x, offset.value.y)
    const way = (dir === 'left' || dir === 'right') ? (d >= 0 ? 'right' : 'left') : dir
    const speed = prev && last && last.t > prev.t ? Math.abs(last.d - prev.d) / (last.t - prev.t) : 0
    const toward = prev && last ? Math.sign(last.d - prev.d) === Math.sign(d) : true
    if (d !== 0 && (Math.abs(d) >= commitAt(way) || (speed > FLICK && toward))) onCommit(way)
    else offset.value = { x: 0, y: 0 }
  }

  // The click a drag may end on (a button under the finger) is not a tap.
  // Browsers mostly send none after a moved touch: the guard lapses quickly.
  function swallowClick() {
    const stop = e => { e.stopPropagation(); e.preventDefault() }
    window.addEventListener('click', stop, { capture: true, once: true })
    setTimeout(() => window.removeEventListener('click', stop, { capture: true }), 350)
  }

  function reset() { offset.value = { x: 0, y: 0 } }

  watch(elRef, (el, _old, onCleanup) => {
    if (!el) return
    el.addEventListener('touchstart', onStart, { passive: true })
    el.addEventListener('touchmove', onMove, { passive: false })
    el.addEventListener('touchend', onEnd)
    el.addEventListener('touchcancel', onEnd)
    onCleanup(() => {
      el.removeEventListener('touchstart', onStart)
      el.removeEventListener('touchmove', onMove)
      el.removeEventListener('touchend', onEnd)
      el.removeEventListener('touchcancel', onEnd)
    })
  }, { immediate: true, flush: 'post' })
  onUnmounted(() => { start = null })

  return { offset, dragging, reset }
}
