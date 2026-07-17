import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import IgdbPickerModal from '../../src/components/IgdbPickerModal.vue'

const setCorrection = vi.fn(() => Promise.resolve({ slug: 'x', episodes: [], nameSlugs: ['x'] }))
const deleteCorrection = vi.fn(() => Promise.resolve({ slug: 'x', episodes: [], nameSlugs: ['x'] }))
vi.mock('../../src/lib/games.js', () => ({
  searchIgdb: vi.fn(() => Promise.resolve([
    { id: 7, name: 'Chrono Trigger', slug: 'chrono-trigger', released: '1995', coverImageId: null },
  ])),
  setCorrection:    (...a) => setCorrection(...a),
  deleteCorrection: (...a) => deleteCorrection(...a),
}))

const GAME = {
  name: 'Chrono Trigger', nameSlug: 'chrono-trigger', nameSlugs: ['chrono-trigger'],
  podcasts: ['fin-du-game'], igdbName: 'Chrono Trigger', igdbSlug: 'chrono-trigger--3',
  displayName: null,
}

const mountPicker = (props = {}) =>
  mount(IgdbPickerModal, { props: { game: GAME, ...props }, attachTo: document.body })

beforeEach(() => { setCorrection.mockClear(); deleteCorrection.mockClear() })

const nameField = w => w.find('.picker-field__input')

describe('IgdbPickerModal display name', () => {
  it('prefills from the current correction', async () => {
    const w = mountPicker({ game: { ...GAME, displayName: 'Chrono Trigger (SNES)' } })
    expect(nameField(w).element.value).toBe('Chrono Trigger (SNES)')
  })

  it('offers no save until the name actually changes', async () => {
    const w = mountPicker()
    expect(w.find('.picker-save').exists()).toBe(false)
    await nameField(w).setValue('Chrono Trigger (SNES)')
    expect(w.find('.picker-save').exists()).toBe(true)
  })

  it('saves the name alone — no pin, so the server need not re-resolve', async () => {
    const w = mountPicker()
    await nameField(w).setValue('Chrono Trigger (SNES)')
    await w.find('.picker-save button').trigger('click')
    await flushPromises()
    expect(setCorrection).toHaveBeenCalledWith({
      nameSlug: 'chrono-trigger', podcastId: '', igdbId: undefined,
      displayName: 'Chrono Trigger (SNES)',
    })
    expect(w.emitted('saved')).toBeTruthy()
  })

  it('sends an empty name to drop the override', async () => {
    const w = mountPicker({ game: { ...GAME, displayName: 'X' } })
    await nameField(w).setValue('')
    await w.find('.picker-save button').trigger('click')
    await flushPromises()
    expect(setCorrection.mock.calls[0][0].displayName).toBe('')
  })

  it('pinning a game leaves an unchanged name out of the request', async () => {
    const w = mountPicker({ game: { ...GAME, displayName: 'Keep me' } })
    await flushPromises()                       // let the IGDB search resolve
    await w.find('.igdb-result').trigger('click')
    await flushPromises()
    const body = setCorrection.mock.calls[0][0]
    expect(body.igdbId).toBe(7)
    expect('displayName' in body).toBe(false)   // untouched ⇒ the server keeps it
  })

  it('goes read-only where corrections.json ships in the image', async () => {
    const w = mountPicker({ writable: false, hasCorrection: true })
    await flushPromises()
    expect(w.find('.picker-warn').text()).toContain('Lecture seule')
    expect(nameField(w).attributes('disabled')).toBeDefined()
    expect(w.find('.igdb-result').attributes('disabled')).toBeDefined()
  })
})
