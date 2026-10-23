<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { isAdmin } from '../lib/auth.js'
import { X, LogOut, SlidersHorizontal, Users } from 'lucide-vue-next'

defineProps({ userEmail: String })
const emit = defineEmits(['close', 'logout'])

const router = useRouter()
const admin  = isAdmin()

function openAdmin(path) {
  emit('close')
  router.push(path)
}

function onKeydown(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="account-title">
    <div class="modal__scrim" @click="emit('close')" />
    <div class="modal__box panel">
      <div class="modal__head">
        <h2 id="account-title" class="cond modal__title">Mon compte</h2>
        <button type="button" class="icon-action" aria-label="Fermer" @click="emit('close')"><X :size="18" :stroke-width="2" /></button>
      </div>
      <p class="mono modal__email ellipsis">{{ userEmail }}</p>
      <div class="modal__actions">
        <button v-if="admin" type="button" class="btn-line" @click="openAdmin('/admin/resolution')">
          <SlidersHorizontal :size="14" :stroke-width="2" /> Résolution des noms
        </button>
        <button v-if="admin" type="button" class="btn-line" @click="openAdmin('/admin/users')">
          <Users :size="14" :stroke-width="2" /> Comptes
        </button>
        <button type="button" class="btn-line modal__logout" @click="emit('logout')">
          <LogOut :size="14" :stroke-width="2" /> Se déconnecter
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal { position: fixed; inset: 0; z-index: var(--z-modal); display: flex; align-items: flex-end; justify-content: center; }
.modal__scrim { position: absolute; inset: 0; background: rgba(0, 0, 0, 0.7); }
.modal__box { position: relative; width: 100%; max-width: 420px; padding: 16px var(--gutter) calc(24px + env(safe-area-inset-bottom, 0px)); animation: slideUpPlayer var(--dur-med) var(--ease-out-soft) both; }
.modal__head { display: flex; align-items: center; justify-content: space-between; }
.modal__title { margin: 0; font-size: var(--text-2xl); }
.modal__email { color: var(--c-fg-2); margin: 8px 0 20px; }
.modal__actions { display: flex; flex-direction: column; gap: 8px; }
.modal__actions .btn-line { justify-content: flex-start; }
.modal__logout { color: var(--c-danger); }
@media (min-width: 768px) {
  .modal { align-items: center; }
  .modal__box { padding: 20px 24px 24px; }
}
</style>
