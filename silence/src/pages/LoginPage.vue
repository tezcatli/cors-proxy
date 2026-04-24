<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login, register, resetRequest, resetConfirm } from '../lib/auth.js'
import { useAuthForm } from '../composables/useAuthForm.js'

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

async function submitLogin() {
  const ok = await run(() => login(loginEmail.value.trim(), loginPassword.value))
  if (ok) router.replace(route.query.redirect || '/')
}

async function submitRegister() {
  if (regPassword.value !== regPassword2.value) {
    errorMsg.value = 'Les mots de passe ne correspondent pas'; return
  }
  const ok = await run(() => register(regEmail.value.trim(), regPassword.value, inviteToken.value))
  if (ok) router.replace(route.query.redirect || '/')
}

async function submitResetRequest() {
  const ok = await run(() => resetRequest(resetEmail.value.trim()))
  if (ok) { infoMsg.value = 'Si ce compte existe, un e-mail a été envoyé.'; resetEmail.value = '' }
}

async function submitReset() {
  if (newPassword.value !== newPassword2.value) {
    errorMsg.value = 'Les mots de passe ne correspondent pas'; return
  }
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
    busy.value = true
    fetch(`/auth/invite-info/${encodeURIComponent(it)}`)
      .then(r => r.ok ? r.json() : r.json().then(j => Promise.reject(new Error(j.error || 'Invitation invalide'))))
      .then(data => { regEmail.value = data.email })
      .catch(err => { errorMsg.value = err.message })
      .finally(() => { busy.value = false })
  }
})
</script>

<template>
  <div class="login-overlay">
    <div class="login-card">

      <div v-if="view === 'login'">
        <div class="auth-title">Connexion</div>
        <p v-if="errorMsg" class="auth-error">{{ errorMsg }}</p>
        <p v-if="infoMsg"  class="auth-info">{{ infoMsg }}</p>
        <form @submit.prevent="submitLogin">
          <input v-model="loginEmail"    class="auth-input" type="email"    placeholder="E-mail" autocomplete="email" required />
          <input v-model="loginPassword" class="auth-input" type="password" placeholder="Mot de passe" autocomplete="current-password" required />
          <button class="auth-btn" type="submit" :disabled="busy">Se connecter</button>
        </form>
        <div class="auth-links">
          <a href="#" @click.prevent="setView('reset-request')">Mot de passe oublié ?</a>
        </div>
      </div>

      <div v-else-if="view === 'register'">
        <div class="auth-title">Créer un compte</div>
        <p v-if="errorMsg" class="auth-error">{{ errorMsg }}</p>
        <form @submit.prevent="submitRegister">
          <input v-model="regEmail"     class="auth-input" type="email"    placeholder="E-mail" :readonly="regEmailReadOnly" autocomplete="email" required />
          <input v-model="regPassword"  class="auth-input" type="password" placeholder="Mot de passe" autocomplete="new-password" required />
          <input v-model="regPassword2" class="auth-input" type="password" placeholder="Confirmer le mot de passe" autocomplete="new-password" required />
          <button class="auth-btn" type="submit" :disabled="busy">Créer le compte</button>
        </form>
        <div class="auth-links">
          <a href="#" @click.prevent="setView('login')">Déjà un compte ?</a>
        </div>
      </div>

      <div v-else-if="view === 'reset-request'">
        <div class="auth-title">Mot de passe oublié</div>
        <p v-if="errorMsg" class="auth-error">{{ errorMsg }}</p>
        <p v-if="infoMsg"  class="auth-info">{{ infoMsg }}</p>
        <form @submit.prevent="submitResetRequest">
          <input v-model="resetEmail" class="auth-input" type="email" placeholder="Votre e-mail" autocomplete="email" required />
          <button class="auth-btn" type="submit" :disabled="busy">Envoyer le lien</button>
        </form>
        <div class="auth-links">
          <a href="#" @click.prevent="setView('login')">Retour à la connexion</a>
        </div>
      </div>

      <div v-else-if="view === 'reset'">
        <div class="auth-title">Nouveau mot de passe</div>
        <p v-if="errorMsg" class="auth-error">{{ errorMsg }}</p>
        <form @submit.prevent="submitReset">
          <input v-model="newPassword"  class="auth-input" type="password" placeholder="Nouveau mot de passe" autocomplete="new-password" required />
          <input v-model="newPassword2" class="auth-input" type="password" placeholder="Confirmer" autocomplete="new-password" required />
          <button class="auth-btn" type="submit" :disabled="busy">Enregistrer</button>
        </form>
        <div class="auth-links">
          <a href="#" @click.prevent="setView('login')">Retour à la connexion</a>
        </div>
      </div>

    </div>
  </div>
</template>
