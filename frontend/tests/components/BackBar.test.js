import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import BackBar from '../../src/components/BackBar.vue'
import { links } from '../helpers/find.js'

const router = { options: { history: { state: { position: 0 } } }, go: vi.fn(), push: vi.fn() }
vi.mock('vue-router', () => ({ useRouter: () => router }))

// Every page over the Ludothèque leads home in one step, whatever its depth.
describe('BackBar', () => {
  it('leads home in one step, as a real link', async () => {
    const w = mount(BackBar, { props: { label: 'Épisode' } })
    const home = links(w, 'Ludothèque, accueil')[0]
    expect(home.attributes('href')).toBe('/')
    await home.trigger('click', { button: 0 })
    expect(router.push).toHaveBeenCalledWith('/')
  })
})
