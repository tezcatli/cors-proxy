// The way home (DECISIONS.md, « Interface »): LUDO// on a page's bar goes back
// to the Ludothèque by popping the history to it rather than pushing it again,
// so the browser's back from there doesn't return to the page just left, and
// the Ludothèque is found as it was left (scroll, search).
//
// `noteVisit` (router.afterEach) keeps the history position of the last visit
// of `/`. A page reached at or before that position, other than `/`, means the
// entry was left behind or replaced: forgotten, and home is pushed instead.

let homePos = null

const positionOf = router => router.options.history.state?.position ?? null

export function noteVisit(router, to) {
  const pos = positionOf(router)
  if (to.path === '/') homePos = pos
  else if (homePos !== null && (pos === null || pos <= homePos)) homePos = null
}

export function goHome(router) {
  const pos = positionOf(router)
  if (homePos !== null && pos !== null && homePos < pos) router.go(homePos - pos)
  else router.push('/')
}
