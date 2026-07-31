<script setup>
// Admin console for accounts: who can get in, who is an administrator, and what
// invitations are still outstanding.
//
// Unlike the resolution console, this is a *small* list (tens of rows) where
// every action is consequential and two of them are irreversible — so the
// design bias is the opposite one: roomy rows, an explicit second tap before
// anything destructive, and the server's own refusal shown on the row that
// caused it rather than restated in our words.
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchUsers, setUserAdmin, deleteUser,
  fetchInvitations, sendInvitation, revokeInvitation,
} from '../lib/admin.js'
import { getUserEmail, refresh as refreshSession } from '../lib/auth.js'
import BackBar from '../components/BackBar.vue'
import {
  Loader2, Mail, Copy, Check, Trash2, ShieldCheck, Shield, UserPlus, AlertTriangle,
} from 'lucide-vue-next'

const router = useRouter()
const myEmail = getUserEmail()

const users       = ref([])
const invitations = ref([])
const loading     = ref(true)
const error       = ref(null)

// Per-row transient state, keyed by user id / invite token: `busy` disables the
// row's actions, `rowError` shows the server's refusal, `confirming` is the
// second tap a destructive action requires.
const busy       = ref({})
const rowError   = ref({})
const confirming = ref(null)
const copied     = ref(null)

const inviteEmail = ref('')
const inviteAdmin = ref(false)
const inviting    = ref(false)
const inviteError = ref(null)
const lastInvite  = ref(null)

const adminCount = computed(() => users.value.filter(u => u.is_admin).length)
const isMe       = u => !!myEmail && u.email.toLowerCase() === myEmail.toLowerCase()

// SQLite hands back "YYYY-MM-DD HH:MM:SS" in UTC with no zone marker; left as-is
// `new Date()` would read it as local time and shift the date.
function fmtDate(sqlDate) {
  if (!sqlDate) return ''
  const d = new Date(sqlDate.replace(' ', 'T') + 'Z')
  return isNaN(d) ? sqlDate : d.toLocaleDateString('fr-FR', { year: 'numeric', month: 'short', day: 'numeric' })
}

async function load() {
  loading.value = true
  error.value   = null
  try {
    const [u, i] = await Promise.all([fetchUsers(), fetchInvitations()])
    users.value       = u
    invitations.value = i
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function onInvite() {
  const email = inviteEmail.value.trim()
  if (!email || inviting.value) return
  inviting.value    = true
  inviteError.value = null
  try {
    lastInvite.value  = await sendInvitation(email, inviteAdmin.value)
    inviteEmail.value = ''
    inviteAdmin.value = false
    invitations.value = await fetchInvitations()
  } catch (e) {
    inviteError.value = e.message
  } finally {
    inviting.value = false
  }
}

async function copyLink(url) {
  try {
    await navigator.clipboard.writeText(url)
    copied.value = url
    setTimeout(() => { if (copied.value === url) copied.value = null }, 2000)
  } catch (_) { /* clipboard denied — the link is selectable on screen anyway */ }
}

// One wrapper for every row action: it owns the busy flag, clears the previous
// refusal, and parks the server's message on the row when there is one.
async function rowAction(key, fn) {
  busy.value     = { ...busy.value, [key]: true }
  rowError.value = { ...rowError.value, [key]: null }
  confirming.value = null
  try {
    await fn()
  } catch (e) {
    rowError.value = { ...rowError.value, [key]: e.message }
  } finally {
    busy.value = { ...busy.value, [key]: false }
  }
}

function toggleAdmin(user) {
  rowAction(user.id, async () => {
    const res = await setUserAdmin(user.id, !user.is_admin)
    user.is_admin = res.is_admin
    // Our own JWT carries a cosmetic `admin` claim that decides whether the SPA
    // shows admin UI; re-issue it so a self-change doesn't need a re-login.
    if (isMe(user)) await refreshSession().catch(() => {})
  })
}

function removeUser(user) {
  rowAction(user.id, async () => {
    await deleteUser(user.id)
    users.value = users.value.filter(u => u.id !== user.id)
  })
}

function revoke(inv) {
  rowAction(inv.token, async () => {
    await revokeInvitation(inv.token)
    invitations.value = invitations.value.filter(i => i.token !== inv.token)
  })
}

function askConfirm(key) { confirming.value = confirming.value === key ? null : key }
</script>

<template>
  <!-- Fixed shell + inner scroller, like the resolution console: the back pill
       is positioned absolute, so a page scrolling its own root scrolls it away. -->
  <div class="fixed inset-0 z-[var(--z-detail)] bg-base-100 flex flex-col">
    <BackBar label="Retour" @back="router.push('/')" />

    <div class="flex-1 min-h-0 overflow-y-auto">
      <div class="console">
        <header class="console__head">
          <h1 class="console__title">Comptes</h1>
          <p class="console__sub">
            L'accès est sur invitation. {{ users.length }} compte<span v-if="users.length > 1">s</span>,
            {{ adminCount }} administrateur<span v-if="adminCount > 1">s</span>.
          </p>
        </header>

        <p v-if="error" class="banner banner--error">
          <AlertTriangle :size="14" :stroke-width="2" /> {{ error }}
        </p>

        <!-- ── Inviter ──────────────────────────────────────────────────── -->
        <section class="card">
          <h2 class="card__title"><UserPlus :size="15" :stroke-width="2.25" /> Inviter</h2>
          <form class="invite-form" @submit.prevent="onInvite">
            <input
              v-model="inviteEmail"
              type="email"
              required
              class="field"
              placeholder="adresse@exemple.com"
              aria-label="Adresse e-mail à inviter"
            />
            <label class="check">
              <input type="checkbox" v-model="inviteAdmin" />
              <span>Administrateur</span>
            </label>
            <button type="submit" class="btn-primary-sm" :disabled="inviting || !inviteEmail.trim()">
              <Loader2 v-if="inviting" :size="14" :stroke-width="2.25" class="spin" />
              <Mail v-else :size="14" :stroke-width="2.25" />
              Envoyer
            </button>
          </form>

          <p v-if="inviteError" class="row-error">{{ inviteError }}</p>

          <!-- The link is shown, not just mailed: SMTP is optional here, and
               without it this is the only copy of the invitation. -->
          <div v-if="lastInvite" class="invite-result">
            <span class="invite-result__label">
              Lien d'invitation<template v-if="lastInvite.is_admin"> (administrateur)</template>
            </span>
            <code class="invite-result__url">{{ lastInvite.invite_url }}</code>
            <button class="btn-ghost-sm" @click="copyLink(lastInvite.invite_url)">
              <component :is="copied === lastInvite.invite_url ? Check : Copy" :size="13" :stroke-width="2.25" />
              {{ copied === lastInvite.invite_url ? 'Copié' : 'Copier' }}
            </button>
          </div>
        </section>

        <!-- ── Invitations en attente ───────────────────────────────────── -->
        <section v-if="invitations.length" class="card">
          <h2 class="card__title"><Mail :size="15" :stroke-width="2.25" /> Invitations en attente</h2>
          <ul class="rows">
            <li v-for="inv in invitations" :key="inv.token" class="row">
              <div class="row__main">
                <span class="row__name">{{ inv.email }}</span>
                <span v-if="inv.is_admin" class="tag tag--admin">admin</span>
                <span class="row__meta">envoyée le {{ fmtDate(inv.created_at) }}</span>
                <p v-if="rowError[inv.token]" class="row-error">{{ rowError[inv.token] }}</p>
              </div>
              <div class="row__actions">
                <button class="btn-ghost-sm" @click="copyLink(inv.invite_url)">
                  <component :is="copied === inv.invite_url ? Check : Copy" :size="13" :stroke-width="2.25" />
                  {{ copied === inv.invite_url ? 'Copié' : 'Lien' }}
                </button>
                <button
                  v-if="confirming !== inv.token"
                  class="btn-ghost-sm btn-ghost-sm--danger"
                  :disabled="busy[inv.token]"
                  @click="askConfirm(inv.token)"
                ><Trash2 :size="13" :stroke-width="2.25" /> Révoquer</button>
                <button v-else class="btn-danger-sm" :disabled="busy[inv.token]" @click="revoke(inv)">
                  <Loader2 v-if="busy[inv.token]" :size="13" :stroke-width="2.25" class="spin" />
                  Confirmer
                </button>
              </div>
            </li>
          </ul>
        </section>

        <!-- ── Comptes ──────────────────────────────────────────────────── -->
        <section class="card">
          <h2 class="card__title"><ShieldCheck :size="15" :stroke-width="2.25" /> Comptes</h2>

          <p v-if="loading" class="row__meta"><Loader2 :size="14" :stroke-width="2.25" class="spin" /> Chargement…</p>

          <ul v-else class="rows">
            <li v-for="user in users" :key="user.id" class="row">
              <div class="row__main">
                <span class="row__name">{{ user.email }}</span>
                <span v-if="isMe(user)" class="tag">vous</span>
                <span v-if="user.is_admin" class="tag tag--admin">admin</span>
                <span class="row__meta">inscrit le {{ fmtDate(user.created_at) }}</span>
                <p v-if="rowError[user.id]" class="row-error">{{ rowError[user.id] }}</p>
              </div>
              <div class="row__actions">
                <!-- Self-actions are disabled here *and* refused server-side:
                     an admin locking themselves out is the one mistake with no
                     in-app way back. -->
                <button
                  class="btn-ghost-sm"
                  :class="{ 'btn-ghost-sm--on': user.is_admin }"
                  :disabled="busy[user.id] || (isMe(user) && user.is_admin)"
                  :title="isMe(user) && user.is_admin ? 'Vous ne pouvez pas retirer votre propre rôle' : null"
                  @click="toggleAdmin(user)"
                >
                  <component :is="user.is_admin ? ShieldCheck : Shield" :size="13" :stroke-width="2.25" />
                  {{ user.is_admin ? 'Administrateur' : 'Promouvoir' }}
                </button>

                <template v-if="!isMe(user)">
                  <button
                    v-if="confirming !== user.id"
                    class="btn-ghost-sm btn-ghost-sm--danger"
                    :disabled="busy[user.id]"
                    @click="askConfirm(user.id)"
                  ><Trash2 :size="13" :stroke-width="2.25" /> Supprimer</button>
                  <button v-else class="btn-danger-sm" :disabled="busy[user.id]" @click="removeUser(user)">
                    <Loader2 v-if="busy[user.id]" :size="13" :stroke-width="2.25" class="spin" />
                    Confirmer
                  </button>
                </template>
              </div>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Scoped so this CSS code-splits with the lazy admin chunk. */
.console {
  max-width: 860px;
  margin: 0 auto;
  padding: var(--back-clear) var(--gutter) 40px;
}
.console__head  { margin-bottom: 14px; }
.console__title { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; }
.console__sub   { font-size: 0.8rem; color: rgba(var(--rgb-line), 0.45); margin-top: 2px; }

.banner {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 11px; margin-bottom: 10px;
  border-radius: var(--radius-md);
  font-size: 0.76rem;
}
.banner--error {
  background: color-mix(in srgb, var(--col-low-text) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--col-low-text) 35%, transparent);
  color: var(--col-low-text);
}

.card {
  padding: 14px;
  margin-bottom: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--panel-bg);
}
.card__title {
  display: flex; align-items: center; gap: 7px;
  font-size: 0.82rem; font-weight: 700; letter-spacing: 0.01em;
  color: rgba(var(--rgb-line), 0.75);
  margin-bottom: 12px;
}

/* ── Invite form ─────────────────────────────────────────────────────── */
.invite-form { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.field {
  flex: 1 1 220px;
  min-width: 0;
  padding: 7px 10px;
  font-size: 0.82rem;
  color: rgba(var(--rgb-line), 0.9);
  background: rgba(var(--rgb-line), 0.05);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}
.field:focus { outline: none; border-color: var(--border-accent); }
.check {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.78rem; color: rgba(var(--rgb-line), 0.7);
  cursor: pointer;
}
.check input { accent-color: var(--game-accent); }

.invite-result {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  margin-top: 10px; padding: 8px 10px;
  border: 1px solid var(--border-accent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--game-accent) 8%, transparent);
}
.invite-result__label { font-size: 0.72rem; color: rgba(var(--rgb-line), 0.6); }
.invite-result__url {
  flex: 1 1 260px;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: rgba(var(--rgb-line), 0.85);
  overflow-wrap: anywhere;
}

/* ── Rows ────────────────────────────────────────────────────────────── */
.rows { display: flex; flex-direction: column; gap: 2px; }
.row {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: 8px;
  padding: 9px 4px;
  border-top: 1px solid var(--border-subtle);
}
.row:first-child { border-top: 0; }
.row__main    { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.row__name    { font-size: 0.86rem; font-weight: 600; overflow-wrap: anywhere; }
.row__meta    { display: inline-flex; align-items: center; gap: 5px; font-size: 0.7rem; color: rgba(var(--rgb-line), 0.42); }
.row__actions { display: flex; align-items: center; gap: 6px; }
.row-error {
  flex-basis: 100%;
  font-size: 0.72rem;
  color: var(--col-low-text);
}

.tag {
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
  background: rgba(var(--rgb-line), 0.08);
  color: rgba(var(--rgb-line), 0.55);
}
.tag--admin {
  background: color-mix(in srgb, var(--game-accent) 20%, transparent);
  color: var(--game-accent);
}

/* ── Buttons ─────────────────────────────────────────────────────────── */
.btn-primary-sm, .btn-ghost-sm, .btn-danger-sm {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 10px;
  border-radius: var(--radius-md);
  font-size: 0.75rem; font-weight: 600;
  border: 1px solid var(--border-subtle);
  background: rgba(var(--rgb-line), 0.05);
  color: rgba(var(--rgb-line), 0.75);
  transition: background var(--dur-fast) var(--ease-std), color var(--dur-fast) var(--ease-std);
}
.btn-primary-sm {
  background: var(--game-accent);
  border-color: var(--game-accent);
  color: var(--game-accent-fg);
}
.btn-ghost-sm:hover:not(:disabled)   { background: rgba(var(--rgb-line), 0.1); color: rgba(var(--rgb-line), 0.95); }
.btn-ghost-sm--on {
  background: color-mix(in srgb, var(--game-accent) 18%, transparent);
  border-color: var(--border-accent);
  color: var(--game-accent);
}
.btn-ghost-sm--danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--col-low-text) 16%, transparent);
  color: var(--col-low-text);
}
.btn-danger-sm {
  background: color-mix(in srgb, var(--col-low-text) 22%, transparent);
  border-color: color-mix(in srgb, var(--col-low-text) 45%, transparent);
  color: var(--col-low-text);
}
.btn-primary-sm:disabled, .btn-ghost-sm:disabled, .btn-danger-sm:disabled { opacity: 0.45; cursor: default; }

.spin { animation: admin-spin 0.8s linear infinite; }
@keyframes admin-spin { to { transform: rotate(360deg); } }
</style>
