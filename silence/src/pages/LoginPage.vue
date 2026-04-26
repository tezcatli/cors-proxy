<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login, register, resetRequest, resetConfirm, apiFetch } from '../lib/auth.js'
import { useAuthForm } from '../composables/useAuthForm.js'
import FormAlerts from '../components/FormAlerts.vue'
import SubmitBtn  from '../components/SubmitBtn.vue'

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
    run(() => apiFetch(`/auth/invite-info/${encodeURIComponent(it)}`).then(r => r.json()).then(data => { regEmail.value = data.email }))
  }
})
</script>

<template>
  <div class="fixed inset-0 z-[200] bg-base-100 flex items-center justify-center p-4">
    <div class="w-full max-w-sm">

      <div class="text-center mb-6">
        <div class="text-4xl mb-1">🎮</div>
        <h1 class="text-xl font-bold">Silence on Joue</h1>
      </div>

      <div class="rounded-2xl bg-base-200 shadow-xl p-8">

        <div v-if="view === 'login'">
          <h2 class="text-xl font-bold mb-4">Connexion</h2>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form @submit.prevent="submitLogin" class="flex flex-col gap-3">
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-base-content/70">E-mail</label>
              <input v-model="loginEmail" class="login-input" type="email" placeholder="vous@exemple.com" autocomplete="email" required />
            </div>
            <div class="flex flex-col gap-1">
              <div class="flex items-center justify-between">
                <label class="text-sm font-medium text-base-content/70">Mot de passe</label>
                <a href="#" class="text-xs text-base-content/50 link link-hover" @click.prevent="setView('reset-request')">Oublié ?</a>
              </div>
              <input v-model="loginPassword" class="login-input" type="password" placeholder="••••••••" autocomplete="current-password" required />
            </div>
            <SubmitBtn :busy="busy" label="Se connecter" />
          </form>
        </div>

        <div v-else-if="view === 'register'">
          <h2 class="text-xl font-bold mb-4">Créer un compte</h2>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form @submit.prevent="submitRegister" class="flex flex-col gap-3">
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-base-content/70">E-mail</label>
              <input v-model="regEmail" class="login-input" type="email" placeholder="vous@exemple.com" :readonly="regEmailReadOnly" autocomplete="email" required />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-base-content/70">Mot de passe</label>
              <input v-model="regPassword" class="login-input" type="password" placeholder="••••••••" autocomplete="new-password" required />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-base-content/70">Confirmer</label>
              <input v-model="regPassword2" class="login-input" type="password" placeholder="••••••••" autocomplete="new-password" required />
            </div>
            <SubmitBtn :busy="busy" label="Créer le compte" />
          </form>
          <p class="text-center text-sm mt-4">
            <a href="#" class="link link-primary" @click.prevent="setView('login')">Déjà un compte ?</a>
          </p>
        </div>

        <div v-else-if="view === 'reset-request'">
          <h2 class="text-xl font-bold mb-4">Mot de passe oublié</h2>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form @submit.prevent="submitResetRequest" class="flex flex-col gap-3">
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-base-content/70">E-mail</label>
              <input v-model="resetEmail" class="login-input" type="email" placeholder="vous@exemple.com" autocomplete="email" required />
            </div>
            <SubmitBtn :busy="busy" label="Envoyer le lien" />
          </form>
          <p class="text-center text-sm mt-4">
            <a href="#" class="link link-primary" @click.prevent="setView('login')">Retour à la connexion</a>
          </p>
        </div>

        <div v-else-if="view === 'reset'">
          <h2 class="text-xl font-bold mb-4">Nouveau mot de passe</h2>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form @submit.prevent="submitReset" class="flex flex-col gap-3">
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-base-content/70">Nouveau mot de passe</label>
              <input v-model="newPassword" class="login-input" type="password" placeholder="••••••••" autocomplete="new-password" required />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-base-content/70">Confirmer</label>
              <input v-model="newPassword2" class="login-input" type="password" placeholder="••••••••" autocomplete="new-password" required />
            </div>
            <SubmitBtn :busy="busy" label="Enregistrer" />
          </form>
          <p class="text-center text-sm mt-4">
            <a href="#" class="link link-primary" @click.prevent="setView('login')">Retour à la connexion</a>
          </p>
        </div>

      </div>

    </div>
  </div>
</template>
