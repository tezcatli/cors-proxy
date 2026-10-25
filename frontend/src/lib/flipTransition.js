/**
 * Tiny FLIP helper for shared-element transitions.
 *
 * Usage:
 *   1. Before navigating, call `captureSource(key, el)` with the source element
 *      (e.g. a GameCard's cover img). The bounding rect is stored.
 *   2. On the target view, after mount, call `playInto(key, targetEl)`.
 *      The target is animated from the source's position+size to its own.
 *   3. Both calls are no-ops if the matching entry isn't present, so it
 *      degrades silently when the user navigates from elsewhere.
 *
 * Entries auto-expire after 1s so stale captures don't hijack later mounts.
 *
 * Only a source seen whole flies: one partly scrolled out of its container
 * (under the header) would start the flight over whatever hides it.
 */

const captures = new Map()

const CLIPS = /auto|scroll|hidden|clip/

// Whether `rect` lies wholly inside the viewport and every scrolling ancestor of `el`.
function seenWhole(el, rect) {
  const inside = box => rect.top >= box.top - 1 && rect.bottom <= box.bottom + 1
    && rect.left >= box.left - 1 && rect.right <= box.right + 1
  if (!inside({ top: 0, left: 0, bottom: window.innerHeight, right: window.innerWidth })) return false
  for (let a = el.parentElement; a; a = a.parentElement) {
    const { overflow, overflowX, overflowY } = getComputedStyle(a)
    if (CLIPS.test(`${overflow} ${overflowX} ${overflowY}`) && !inside(a.getBoundingClientRect())) return false
  }
  return true
}

export function captureSource(key, el) {
  if (!key || !el) return
  const rect = el.getBoundingClientRect()
  if (!seenWhole(el, rect)) return
  const radius = getComputedStyle(el).borderRadius
  captures.set(key, { rect, radius, ts: performance.now() })
  setTimeout(() => {
    const e = captures.get(key)
    if (e && performance.now() - e.ts > 950) captures.delete(key)
  }, 1000)
}

export function playInto(key, targetEl, opts = {}) {
  if (!key || !targetEl) return
  const cap = captures.get(key)
  if (!cap) return
  captures.delete(key)

  const targetRect = targetEl.getBoundingClientRect()
  const dx = cap.rect.left - targetRect.left
  const dy = cap.rect.top  - targetRect.top
  const sx = cap.rect.width  / targetRect.width
  const sy = cap.rect.height / targetRect.height

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduced) return

  const duration = opts.duration ?? 480
  const easing   = opts.easing   ?? 'cubic-bezier(0.22, 1, 0.36, 1)'

  targetEl.animate(
    [
      { transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`, borderRadius: cap.radius, opacity: 0.85 },
      { transform: 'translate(0, 0) scale(1, 1)', borderRadius: getComputedStyle(targetEl).borderRadius, opacity: 1 },
    ],
    { duration, easing, fill: 'both' },
  )
}
