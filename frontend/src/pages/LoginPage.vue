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
    run(() => apiFetch(`/silence/auth/invite-info/${encodeURIComponent(it)}`).then(r => r.json()).then(data => { regEmail.value = data.email }))
  }
})
</script>

<template>
  <div class="fixed inset-0 z-[200] bg-base-100 flex items-center justify-center p-4 overflow-hidden">
    <!-- Animated gradient backdrop -->
    <div
      class="hero-drift absolute inset-0 -z-10 pointer-events-none"
      style="background-image:
        radial-gradient(80% 60% at 15% 0%,   rgba(139,92,246,0.30), transparent 60%),
        radial-gradient(70% 50% at 90% 100%, rgba(233,69,96,0.28),  transparent 60%),
        radial-gradient(60% 50% at 50% 50%,  rgba(34,211,238,0.10), transparent 60%);"
    />
    <div class="hero-drift absolute inset-0 -z-10 opacity-40 pointer-events-none"
         style="background-image:
           radial-gradient(40% 30% at 30% 80%, rgba(255,138,160,0.20), transparent 60%);" />

    <div class="w-full max-w-sm">

      <div class="text-center mb-7">
        <div class="text-5xl mb-2 drop-shadow-[0_4px_16px_rgba(233,69,96,0.5)]">🎮</div>
        <h1 class="text-2xl font-extrabold tracking-[-0.02em]">Silence on Joue</h1>
        <p class="text-xs text-white/45 mt-1 font-medium">Catalogue des jeux du podcast</p>
      </div>

      <div class="panel p-7 shadow-e4">

        <div v-if="view === 'login'">
          <h2 class="text-xl font-extrabold mb-4 tracking-[-0.01em]">Connexion</h2>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form @submit.prevent="submitLogin" class="flex flex-col gap-3">
            <div class="flex flex-col gap-1.5">
              <label class="text-xs font-semibold text-white/55 uppercase tracking-wider">E-mail</label>
              <input v-model="loginEmail" class="app-input" type="email" placeholder="vous@exemple.com" autocomplete="email" required />
            </div>
            <div class="flex flex-col gap-1.5">
              <div class="flex items-center justify-between">
                <label class="text-xs font-semibold text-white/55 uppercase tracking-wider">Mot de passe</label>
                <button type="button" class="text-xs text-white/55 hover:text-white transition-colors bg-transparent border-0 p-0 cursor-pointer" @click="setView('reset-request')">Oublié ?</button>
              </div>
              <input v-model="loginPassword" class="app-input" type="password" placeholder="••••••••" autocomplete="current-password" required />
            </div>
            <SubmitBtn :busy="busy" label="Se connecter" />
          </form>
        </div>

        <div v-else-if="view === 'register'">
          <h2 class="text-xl font-extrabold mb-4 tracking-[-0.01em]">Créer un compte</h2>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form @submit.prevent="submitRegister" class="flex flex-col gap-3">
            <div class="flex flex-col gap-1.5">
              <label class="text-xs font-semibold text-white/55 uppercase tracking-wider">E-mail</label>
              <input v-model="regEmail" class="app-input" type="email" placeholder="vous@exemple.com" :readonly="regEmailReadOnly" autocomplete="email" required />
            </div>
            <div class="flex flex-col gap-1.5">
              <label class="text-xs font-semibold text-white/55 uppercase tracking-wider">Mot de passe</label>
              <input v-model="regPassword" class="app-input" type="password" placeholder="••••••••" autocomplete="new-password" required />
            </div>
            <div class="flex flex-col gap-1.5">
              <label class="text-xs font-semibold text-white/55 uppercase tracking-wider">Confirmer</label>
              <input v-model="regPassword2" class="app-input" type="password" placeholder="••••••••" autocomplete="new-password" required />
            </div>
            <SubmitBtn :busy="busy" label="Créer le compte" />
          </form>
          <p class="text-center text-sm mt-4">
            <button type="button" class="text-white/70 hover:text-white font-medium transition-colors bg-transparent border-0 p-0 cursor-pointer" @click="setView('login')">Déjà un compte ?</button>
          </p>
        </div>

        <div v-else-if="view === 'reset-request'">
          <h2 class="text-xl font-extrabold mb-4 tracking-[-0.01em]">Mot de passe oublié</h2>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form @submit.prevent="submitResetRequest" class="flex flex-col gap-3">
            <div class="flex flex-col gap-1.5">
              <label class="text-xs font-semibold text-white/55 uppercase tracking-wider">E-mail</label>
              <input v-model="resetEmail" class="app-input" type="email" placeholder="vous@exemple.com" autocomplete="email" required />
            </div>
            <SubmitBtn :busy="busy" label="Envoyer le lien" />
          </form>
          <p class="text-center text-sm mt-4">
            <button type="button" class="text-white/70 hover:text-white font-medium transition-colors bg-transparent border-0 p-0 cursor-pointer" @click="setView('login')">Retour à la connexion</button>
          </p>
        </div>

        <div v-else-if="view === 'reset'">
          <h2 class="text-xl font-extrabold mb-4 tracking-[-0.01em]">Nouveau mot de passe</h2>
          <FormAlerts :error-msg="errorMsg" :info-msg="infoMsg" />
          <form @submit.prevent="submitReset" class="flex flex-col gap-3">
            <div class="flex flex-col gap-1.5">
              <label class="text-xs font-semibold text-white/55 uppercase tracking-wider">Nouveau mot de passe</label>
              <input v-model="newPassword" class="app-input" type="password" placeholder="••••••••" autocomplete="new-password" required />
            </div>
            <div class="flex flex-col gap-1.5">
              <label class="text-xs font-semibold text-white/55 uppercase tracking-wider">Confirmer</label>
              <input v-model="newPassword2" class="app-input" type="password" placeholder="••••••••" autocomplete="new-password" required />
            </div>
            <SubmitBtn :busy="busy" label="Enregistrer" />
          </form>
          <p class="text-center text-sm mt-4">
            <button type="button" class="text-white/70 hover:text-white font-medium transition-colors bg-transparent border-0 p-0 cursor-pointer" @click="setView('login')">Retour à la connexion</button>
          </p>
        </div>

      </div>
    </div>
  </div>
</template>
