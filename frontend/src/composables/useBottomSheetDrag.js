import { ref, computed } from 'vue'

const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0

/**
 * Bottom-sheet pointer gestures for the mobile audio player:
 *  - vertical drag expands / collapses the sheet,
 *  - horizontal drag dismisses it.
 * Desktop (≥900px) and non-touch devices are ignored.
 *
 * @param playerEl  template ref to the draggable sheet element.
 * @param collapsed ref<boolean> the sheet's collapsed state (read + written).
 * @param onDismiss callback invoked when a horizontal dismiss completes.
 * @returns drag state, `sheetStyle`, `reset()`, and the pointer handlers.
 */
export function useBottomSheetDrag(playerEl, collapsed, onDismiss) {
  const dragExpand = ref(null)   // null = idle; 0–1 fraction while dragging
  const isDragging = ref(false)  // true = suppress CSS transition during drag
  const dragX      = ref(0)      // horizontal offset for dismiss translateX

  let dragStartX = 0
  let dragStartY = 0
  let dragActive = false
  let dragAxis   = null          // null = undecided, 'x' = dismiss, 'y' = expand/collapse

  function endDrag() {
    isDragging.value = false       // frame N: CSS transition re-enabled, height still at Xpx
    requestAnimationFrame(() => {
      dragExpand.value = null       // frame N+1: height override removed → CSS transition fires
    })
  }

  function onPointerDown(e) {
    if (!isTouchDevice) return
    if (window.matchMedia('(min-width: 900px)').matches) return
    if (e.target.closest('button') || e.target.closest('input')) return
    dragStartX = e.clientX
    dragStartY = e.clientY
    dragAxis   = null
    dragActive = true
    isDragging.value = true
    try { playerEl.value?.setPointerCapture(e.pointerId) } catch (_) {}
  }

  function onPointerMove(e) {
    if (!dragActive) return
    const dx = e.clientX - dragStartX
    const dy = e.clientY - dragStartY

    if (dragAxis === null) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) > 8)
        dragAxis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
      return
    }

    if (dragAxis === 'y') {
      if (dy < 0 && collapsed.value) {
        dragExpand.value = Math.min(1, -dy / 60)
        if (dy < -60) { dragActive = false; collapsed.value = false; endDrag() }
        return
      }
      if (dy > 0 && !collapsed.value) {
        dragExpand.value = Math.max(0, 1 - dy / 100)
        if (dy > 100) { dragActive = false; collapsed.value = true; endDrag() }
        return
      }
      isDragging.value = false
      dragExpand.value = null
      return
    }

    // dragAxis === 'x': slide to dismiss
    isDragging.value = false
    dragExpand.value = null
    dragX.value = dx
    if (Math.abs(dx) > 150) { dragActive = false; dragX.value = 0; onDismiss?.() }
  }

  function onPointerUp(e) {
    if (!dragActive) return
    dragActive = false
    try { playerEl.value?.releasePointerCapture(e.pointerId) } catch (_) {}
    if (dragAxis === 'x') {
      dragX.value = 0
    } else if (dragExpand.value !== null) {
      endDrag()
    } else {
      isDragging.value = false
    }
    dragAxis = null
  }

  function onPointerCancel() {
    dragActive = false
    isDragging.value = false
    dragExpand.value = null
    dragX.value = 0
    dragAxis    = null
  }

  function reset() {
    dragExpand.value = null
    isDragging.value = false
    dragX.value      = 0
    dragAxis         = null
    dragActive       = false
  }

  const sheetStyle = computed(() => ({
    transform:  dragX.value !== 0 ? `translateX(${dragX.value}px)` : '',
    transition: dragX.value !== 0 ? 'none' : 'transform var(--dur-med) var(--ease-out-soft)',
  }))

  return {
    dragExpand, isDragging, dragX, sheetStyle, reset,
    onPointerDown, onPointerMove, onPointerUp, onPointerCancel,
  }
}
