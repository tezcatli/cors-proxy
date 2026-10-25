import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// A router whose history sits at `position`, visiting `path` there.
function routerAt(position, path = '/') {
  return { options: { history: { state: { position } } }, currentRoute: { value: { path, query: {} } }, go: vi.fn(), push: vi.fn() }
}
function visit(home, router, path, position) {
  router.options.history.state.position = position
  home.noteVisit(router, { path })
}

let home
beforeEach(async () => {
  vi.resetModules()
  home = await import('../../src/lib/home.js')
})

describe('goHome', () => {
  it.each([
    ['pops the history back to the Ludothèque left behind',
      [['/', 0], ['/game/a', 1], ['/episode/b', 2], ['/podcast/c', 3]], { go: -3 }],
    ['pushes it when the page was opened directly',
      [['/game/a', 0]], { push: '/' }],
    ['pushes it when the Ludothèque’s entry was replaced (back past it, then a new page)',
      [['/', 2], ['/game/a', 3], ['/game/b', 1], ['/episode/c', 2], ['/game/d', 3]], { push: '/' }],
  ])('%s', (_, visits, expected) => {
    const router = routerAt(0)
    for (const [path, pos] of visits) visit(home, router, path, pos)
    home.goHome(router)
    if (expected.go) expect(router.go).toHaveBeenCalledWith(expected.go)
    else expect(router.push).toHaveBeenCalledWith(expected.push)
  })
})

// In the installed app, back stops at the Ludothèque: a guard entry under it,
// laid on the first touch (Chrome skips on back an entry added before one).
describe('guardHome', () => {
  const touch = () => window.dispatchEvent(new Event('pointerdown'))
  const installed = on => vi.stubGlobal('matchMedia', () => ({ matches: on }))
  let replace
  beforeEach(() => { replace = vi.spyOn(history, 'replaceState').mockImplementation(() => {}) })
  afterEach(() => { vi.unstubAllGlobals(); replace.mockRestore() })

  it('marks the first entry and pushes the Ludothèque on it, on the first touch', () => {
    installed(true)
    const router = routerAt(0)
    home.guardHome(router)
    expect(router.push).not.toHaveBeenCalled()
    touch(); touch()
    expect(replace).toHaveBeenCalledWith(expect.objectContaining({ ludoGuard: true }), '')
    expect(router.push).toHaveBeenCalledTimes(1)
    expect(router.push).toHaveBeenCalledWith(expect.objectContaining({ path: '/', force: true }))
  })

  it.each([
    ['in a browser tab', false, 0, '/'],
    ['above the first entry', true, 2, '/'],
    ['on a page opened directly', true, 0, '/game/a'],
  ])('lays no guard %s', (_, on, position, path) => {
    installed(on)
    const router = routerAt(position, path)
    home.guardHome(router)
    touch()
    expect(router.push).not.toHaveBeenCalled()
  })

  it('steps forward again when back reaches the guard, which is never home', () => {
    const router = routerAt(0)
    visit(home, router, '/', 1)
    router.options.history.state = { position: 0, ludoGuard: true }
    home.noteVisit(router, { path: '/' })
    expect(router.go).toHaveBeenCalledWith(1)
    visit(home, router, '/game/a', 2)
    home.goHome(router)
    expect(router.go).toHaveBeenLastCalledWith(-1)
  })
})
