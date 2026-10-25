// The way home (DECISIONS.md, « Interface »): LUDO// on a page's bar goes back
// to the Ludothèque by popping the history to it rather than pushing it again,
// so the browser's back from there doesn't return to the page just left, and
// the Ludothèque is found as it was left (scroll, search).
//
// `noteVisit` (router.afterEach) keeps the history position of the last visit
// of `/`. A page reached at or before that position, other than `/`, means the
// entry was left behind or replaced: forgotten, and home is pushed instead.
//
// In the installed app, back stops at the Ludothèque instead of closing it:
// `guardHome` leaves a guard entry under it — the first entry, marked, with the
// Ludothèque pushed again on top — and back onto the guard steps forward again.
// Chrome skips on back an entry added before any interaction, so the guard is
// laid on the first touch, not at load.

let homePos = null

const stateOf    = router => router.options.history.state ?? {}
const positionOf = router => stateOf(router).position ?? null

export function noteVisit(router, to) {
  if (stateOf(router).ludoGuard) { router.go(1); return }
  const pos = positionOf(router)
  if (to.path === '/') homePos = pos
  else if (homePos !== null && (pos === null || pos <= homePos)) homePos = null
}

export function goHome(router) {
  const pos = positionOf(router)
  if (homePos !== null && pos !== null && homePos < pos) router.go(homePos - pos)
  else router.push('/')
}

const installed = () =>
  window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true

export function guardHome(router) {
  if (!installed()) return
  const lay = () => {
    const route = router.currentRoute.value
    if (route.path !== '/' || positionOf(router) !== 0 || stateOf(router).ludoGuard) return
    window.removeEventListener('pointerdown', lay, true)
    history.replaceState({ ...history.state, ludoGuard: true }, '')
    router.push({ path: '/', query: route.query, force: true })
  }
  window.addEventListener('pointerdown', lay, true)
}
