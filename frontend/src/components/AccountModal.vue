<script setup>
import { onMounted, onUnmounted } from 'vue'

defineProps({ userEmail: String })
const emit = defineEmits(['close', 'logout'])

function onKeydown(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="fixed inset-0 z-[200] flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/50" @click="emit('close')" />
    <div class="relative rounded-2xl bg-base-200 shadow-xl p-6 w-full max-w-xs">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-bold">Mon compte</h2>
        <button class="btn btn-circle btn-ghost !size-8 !min-h-8 text-sm" aria-label="Fermer" @click="emit('close')">✕</button>
      </div>
      <p class="text-sm text-base-content/50 mb-5 truncate">{{ userEmail }}</p>
      <button class="btn btn-outline btn-error w-full" @click="emit('logout')">Se déconnecter</button>
    </div>
  </div>
</template>
