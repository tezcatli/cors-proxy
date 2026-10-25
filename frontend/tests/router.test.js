import { describe, it, expect } from 'vitest'
import router from '../src/router.js'

describe('router', () => {
  it('leads the old games tab to the Ludothèque, its search kept', () => {
    const jeux = router.options.routes.find(r => r.path === '/jeux')
    expect(jeux.redirect({ query: { q: 'zelda' } })).toEqual({ path: '/', query: { q: 'zelda' } })
  })
})
