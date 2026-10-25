<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login, register, resetRequest, resetConfirm, apiFetch } from '../lib/auth.js'
import { useAuthForm } from '../composables/useAuthForm.js'
import FormAlerts from '../components/FormAlerts.vue'
import SubmitBtn  from '../components/SubmitBtn.vue'
import Wordmark   from '../components/Wordmark.vue'

const router = useRouter()
const route  = useRoute()

const { busy, errorMsg, infoMsg, clearMessages, run } = useAuthForm()

const view        = ref('login')
const resetToken  = ref('')
const inviteToken = ref('')

const loginEmail    = ref('')
const loginPassword = ref('')

const regEmail         = ref('')
const regPassword      = ref('')
const regPassword2     = ref('')
const regEmailReadOnly = ref(false)

const resetEmail  = ref('')
const newPassword  = ref('')
const newPassword2 = ref('')

function setView(v) { view.value = v; clearMessages() }

function passwordsMatch(a, b) {
  if (a !== b) { errorMsg.value = 'Les mots de passe ne correspondent pas'; return false }
  return true
}

async function submitLogin() {
  const ok = await run(() => login(loginEmail.value.trim(), loginPassword.value))
  if (ok) router.replace(route.query.redirect || '/')
}

async function submitRegister() {
  if (!passwordsMatch(regPassword.value, regPassword2.value)) return
  const ok = await run(() => register(regEmail.value.trim(), regPassword.value, inviteToken.value))
  if (ok) router.replace(route.query.redirect || '/')
}

async function submitResetRequest() {
  const ok = await run(() => resetRequest(resetEmail.value.trim()))
  if (ok) { infoMsg.value = 'Si ce compte existe, un e-mail a été envoyé.'; resetEmail.value = '' }
}

async function submitReset() {
  if (!passwordsMatch(newPassword.value, newPassword2.value)) return
  const ok = await run(() => resetConfirm(resetToken.value, newPassword.value))
  if (ok) { setView('login'); infoMsg.value = 'Mot de passe mis à jour. Connectez-vous.' }
}

onMounted(() => {
  const rt = route.query.reset
  const it = route.query.invite
  if (rt) {
    resetToken.value = rt
    setView('reset')
  } else if (it) {
    inviteToken.value      = it
    regEmail.value         = ''
    regEmailReadOnly.value = true
    setView('register')
    run(() => apiFetch(`/auth/invite-info/${encodeURIComponent(it)}`).then(r => r.json()).then(data => { regEmail.value = data.email }))
  }
})
</script>

<template>
  <div class="login">
    <!-- Outside any game: the mark's yellow is the page's light -->
    <div class="halo" aria-hidden="true"></div>
    <div class="login__col">
      <div class="login__brand">
        <span class="login__mark" role="img" aria-label="Ludo"><Wordmark /></span>
        <span class="lab">Les tests de jeux vidéo de vos podcasts</span>
      </div>

      <div class="login__box">
        <template v-if="view === 'login'">
          <h1 class="cond login__title">Connexion</h1>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form class="login__form" @submit.prevent="submitLogin">
            <label class="field"><span class="lab">E-mail</span>
              <input v-model="loginEmail" class="app-input" type="email" autocomplete="email" required />
            </label>
            <label class="field"><span class="field__row"><span class="lab">Mot de passe</span>
              <button type="button" class="login__link lab" @click.prevent="setView('reset-request')">Oublié ?</button></span>
              <input v-model="loginPassword" class="app-input" type="password" autocomplete="current-password" required />
            </label>
            <SubmitBtn :busy="busy" label="Se connecter" />
          </form>
        </template>

        <template v-else-if="view === 'register'">
          <h1 class="cond login__title">Créer un compte</h1>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form class="login__form" @submit.prevent="submitRegister">
            <label class="field"><span class="lab">E-mail</span>
              <input v-model="regEmail" class="app-input" type="email" :readonly="regEmailReadOnly" autocomplete="email" required />
            </label>
            <label class="field"><span class="lab">Mot de passe</span>
              <input v-model="regPassword" class="app-input" type="password" autocomplete="new-password" required />
            </label>
            <label class="field"><span class="lab">Confirmer</span>
              <input v-model="regPassword2" class="app-input" type="password" autocomplete="new-password" required />
            </label>
            <SubmitBtn :busy="busy" label="Créer le compte" />
          </form>
          <button type="button" class="login__link lab login__back" @click="setView('login')">Déjà un compte ?</button>
        </template>

        <template v-else-if="view === 'reset-request'">
          <h1 class="cond login__title">Mot de passe oublié</h1>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form class="login__form" @submit.prevent="submitResetRequest">
            <label class="field"><span class="lab">E-mail</span>
              <input v-model="resetEmail" class="app-input" type="email" autocomplete="email" required />
            </label>
            <SubmitBtn :busy="busy" label="Envoyer le lien" />
          </form>
          <button type="button" class="login__link lab login__back" @click="setView('login')">Retour à la connexion</button>
        </template>

        <template v-else-if="view === 'reset'">
          <h1 class="cond login__title">Nouveau mot de passe</h1>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form class="login__form" @submit.prevent="submitReset">
            <label class="field"><span class="lab">Nouveau mot de passe</span>
              <input v-model="newPassword" class="app-input" type="password" autocomplete="new-password" required />
            </label>
            <label class="field"><span class="lab">Confirmer</span>
              <input v-model="newPassword2" class="app-input" type="password" autocomplete="new-password" required />
            </label>
            <SubmitBtn :busy="busy" label="Enregistrer" />
          </form>
          <button type="button" class="login__link lab login__back" @click="setView('login')">Retour à la connexion</button>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--c-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px var(--gutter);
  overflow-y: auto;
  --game-glow:   rgba(255, 255, 0, 0.13);
  --game-glow-2: rgba(242, 242, 245, 0.06);
}
.login__col { width: 100%; max-width: 380px; display: flex; flex-direction: column; gap: 32px; }
.login__brand { display: flex; flex-direction: column; gap: 8px; }
.login__mark { font-size: 56px; }
.login__box { border-top: 1px solid var(--c-line); padding-top: 24px; display: flex; flex-direction: column; gap: 16px; }
.login__title { margin: 0; font-size: var(--text-2xl); }
.login__form { display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 8px; }
.field__row { display: flex; justify-content: space-between; align-items: center; }
.login__link { border: 0; background: transparent; padding: 0; min-height: 32px; cursor: pointer; color: var(--c-fg-2); text-decoration: underline; text-underline-offset: 3px; }
.login__link:hover { color: var(--c-fg); }
.login__back { align-self: flex-start; }
</style>
