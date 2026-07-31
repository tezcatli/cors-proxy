import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AdminUsersPage from '../../src/pages/AdminUsersPage.vue'

const USERS = [
  { id: 1, email: 'me@example.com',    is_admin: true,  created_at: '2026-01-02 10:00:00' },
  { id: 2, email: 'other@example.com', is_admin: false, created_at: '2026-03-04 10:00:00' },
]
const INVITATIONS = [
  { token: 'tok-1', email: 'waiting@example.com', is_admin: true,
    created_at: '2026-07-01 09:00:00', invite_url: 'http://x/silence/?invite=tok-1' },
]

const fetchUsers       = vi.fn(() => Promise.resolve(structuredClone(USERS)))
const fetchInvitations = vi.fn(() => Promise.resolve(structuredClone(INVITATIONS)))
const setUserAdmin     = vi.fn((id, isAdmin) => Promise.resolve({ id, is_admin: isAdmin }))
const deleteUser       = vi.fn(() => Promise.resolve())
const sendInvitation   = vi.fn(() => Promise.resolve({ invite_url: 'http://x/silence/?invite=new', is_admin: true }))
const revokeInvitation = vi.fn(() => Promise.resolve())

vi.mock('../../src/lib/admin.js', () => ({
  fetchUsers:       (...a) => fetchUsers(...a),
  fetchInvitations: (...a) => fetchInvitations(...a),
  setUserAdmin:     (...a) => setUserAdmin(...a),
  deleteUser:       (...a) => deleteUser(...a),
  sendInvitation:   (...a) => sendInvitation(...a),
  revokeInvitation: (...a) => revokeInvitation(...a),
}))
vi.mock('../../src/lib/auth.js', () => ({
  getUserEmail: () => 'me@example.com',
  refresh:      vi.fn(() => Promise.resolve()),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

async function mountPage() {
  const wrapper = mount(AdminUsersPage)
  await flushPromises()
  return wrapper
}

// Find a row (account or invitation) by the text it shows.
function rowFor(wrapper, text) {
  return wrapper.findAll('.row').find(r => r.text().includes(text))
}

beforeEach(() => {
  vi.clearAllMocks()
  fetchUsers.mockResolvedValue(structuredClone(USERS))
  fetchInvitations.mockResolvedValue(structuredClone(INVITATIONS))
})

describe('AdminUsersPage', () => {
  it('lists accounts and pending invitations', async () => {
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('other@example.com')
    expect(wrapper.text()).toContain('waiting@example.com')
    expect(wrapper.text()).toContain('2 comptes, 1 administrateur')
  })

  it('sends an invitation with the admin flag and shows the link', async () => {
    const wrapper = await mountPage()
    await wrapper.find('input[type="email"]').setValue('new@example.com')
    await wrapper.find('input[type="checkbox"]').setValue(true)
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(sendInvitation).toHaveBeenCalledWith('new@example.com', true)
    expect(wrapper.text()).toContain('http://x/silence/?invite=new')
    expect(wrapper.text()).toContain('(administrateur)')
    expect(fetchInvitations).toHaveBeenCalledTimes(2)   // list refreshed after sending
  })

  it('promotes another account', async () => {
    const wrapper = await mountPage()
    const row = rowFor(wrapper, 'other@example.com')
    await row.findAll('button').find(b => b.text().includes('Promouvoir')).trigger('click')
    await flushPromises()

    expect(setUserAdmin).toHaveBeenCalledWith(2, true)
    expect(rowFor(wrapper, 'other@example.com').text()).toContain('Administrateur')
  })

  // Locking yourself out is the one mistake with no in-app way back, so the UI
  // refuses before the server has to.
  it('locks the current admin out of demoting or deleting themselves', async () => {
    const wrapper = await mountPage()
    const row = rowFor(wrapper, 'me@example.com')
    expect(row.text()).toContain('vous')
    expect(row.findAll('button').some(b => b.text().includes('Supprimer'))).toBe(false)
    expect(row.findAll('button').find(b => b.text().includes('Administrateur')).attributes('disabled'))
      .toBeDefined()
  })

  it('requires a second tap before deleting, then removes the row', async () => {
    const wrapper = await mountPage()
    await rowFor(wrapper, 'other@example.com')
      .findAll('button').find(b => b.text().includes('Supprimer')).trigger('click')
    expect(deleteUser).not.toHaveBeenCalled()

    await rowFor(wrapper, 'other@example.com')
      .findAll('button').find(b => b.text().includes('Confirmer')).trigger('click')
    await flushPromises()

    expect(deleteUser).toHaveBeenCalledWith(2)
    expect(wrapper.text()).not.toContain('other@example.com')
  })

  it("shows the server's refusal on the row that caused it", async () => {
    deleteUser.mockRejectedValueOnce(new Error('Il doit rester au moins un administrateur'))
    const wrapper = await mountPage()
    await rowFor(wrapper, 'other@example.com')
      .findAll('button').find(b => b.text().includes('Supprimer')).trigger('click')
    await rowFor(wrapper, 'other@example.com')
      .findAll('button').find(b => b.text().includes('Confirmer')).trigger('click')
    await flushPromises()

    expect(rowFor(wrapper, 'other@example.com').text())
      .toContain('Il doit rester au moins un administrateur')
    expect(wrapper.text()).toContain('other@example.com')   // row kept
  })

  it('revokes a pending invitation after confirmation', async () => {
    const wrapper = await mountPage()
    await rowFor(wrapper, 'waiting@example.com')
      .findAll('button').find(b => b.text().includes('Révoquer')).trigger('click')
    await rowFor(wrapper, 'waiting@example.com')
      .findAll('button').find(b => b.text().includes('Confirmer')).trigger('click')
    await flushPromises()

    expect(revokeInvitation).toHaveBeenCalledWith('tok-1')
    expect(wrapper.text()).not.toContain('waiting@example.com')
  })

  it('surfaces a load failure instead of an empty page', async () => {
    fetchUsers.mockRejectedValueOnce(new Error('Accès réservé aux administrateurs'))
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('Accès réservé aux administrateurs')
  })
})
