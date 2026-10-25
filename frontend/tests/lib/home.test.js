import { describe, it, expect, vi, beforeEach } from 'vitest'

// A router whose history sits at `position`, visiting `path` there.
function routerAt(position) {
  return { options: { history: { state: { position } } }, go: vi.fn(), push: vi.fn() }
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
