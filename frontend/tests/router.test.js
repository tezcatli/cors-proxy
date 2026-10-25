import { describe, it, expect } from 'vitest'
import router from '../src/router.js'

describe('router', () => {
  it('leads the old games tab to the Ludothèque, its search kept', () => {
    const jeux = router.options.routes.find(r => r.path === '/jeux')
    expect(jeux.redirect({ query: { q: 'zelda' } })).toEqual({ path: '/', query: { q: 'zelda' } })
  })
})

describe('a podcast’s page', () => {
  const route = router.options.routes.find(r => r.path === '/podcast/:id')
  it('opens for a known podcast', () => {
    expect(route.beforeEnter({ params: { id: 'zqsd' } })).toBe(true)
  })
  it('leads an unknown one back to the Ludothèque', () => {
    expect(route.beforeEnter({ params: { id: 'nope' } })).toEqual({ path: '/' })
  })
})
