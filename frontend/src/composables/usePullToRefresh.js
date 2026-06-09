import { ref, onMounted, onUnmounted } from 'vue'

export function usePullToRefresh(onTrigger, { threshold = 80 } = {}) {
  const pullY     = ref(0)
  const isPulling = ref(false)
  let _startY = 0, _active = false, _scrollEl = null

  function setScrollEl(el) { _scrollEl = el }

  function onTouchStart(e) {
    // Only engage when the gesture begins inside the tracked scroll container.
    // Overlay routes (game/episode/login) live outside .grid-area, so this keeps
    // pull-to-refresh from hijacking (and blocking) their own scrolling.
    if (!_scrollEl || !_scrollEl.contains(e.target)) return
    if (_scrollEl.scrollTop > 0) return
    _startY = e.touches[0].clientY
    _active = true
  }

  function onTouchMove(e) {
    if (!_active) return
    const dy = e.touches[0].clientY - _startY
    if (dy <= 0 || (_scrollEl?.scrollTop > 0)) { _active = false; return }
    e.preventDefault()
    pullY.value     = Math.min(dy, threshold * 1.5)
    isPulling.value = true
  }

  function onTouchEnd() {
    if (!_active) return
    const triggered = pullY.value >= threshold
    _active         = false
    isPulling.value = false
    pullY.value     = 0
    if (triggered) onTrigger()
  }

  onMounted(() => {
    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchmove',  onTouchMove,  { passive: false })
    window.addEventListener('touchend',   onTouchEnd,   { passive: true })
  })
  onUnmounted(() => {
    window.removeEventListener('touchstart', onTouchStart)
    window.removeEventListener('touchmove',  onTouchMove)
    window.removeEventListener('touchend',   onTouchEnd)
  })

  return { pullY, isPulling, setScrollEl }
}
