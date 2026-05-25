<script setup>
import { onMounted, onUnmounted } from 'vue'
import { X, LogOut } from 'lucide-vue-next'

defineProps({ userEmail: String })
const emit = defineEmits(['close', 'logout'])

function onKeydown(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="fixed inset-0 z-[200] flex items-center justify-center p-4">
    <Transition name="modal-pop" appear>
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="emit('close')" />
    </Transition>
    <Transition name="modal-pop" appear>
      <div class="panel relative p-6 w-full max-w-xs shadow-e4">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-extrabold tracking-[-0.01em]">Mon compte</h2>
          <button
            class="btn btn-circle btn-ghost !size-8 !min-h-8 hover:bg-white/10"
            aria-label="Fermer"
            @click="emit('close')"
          ><X :size="16" :stroke-width="2.25" /></button>
        </div>
        <div class="flex items-center gap-3 mb-5 p-3 bg-white/4 rounded-xl border border-white/5">
          <div class="size-10 rounded-full flex items-center justify-center text-base font-bold flex-shrink-0"
               style="background: color-mix(in srgb, var(--game-accent) 22%, transparent); color: var(--game-accent);">
            {{ userEmail?.[0]?.toUpperCase() || '?' }}
          </div>
          <p class="text-sm text-white/75 truncate flex-1 min-w-0">{{ userEmail }}</p>
        </div>
        <button class="btn btn-outline btn-error w-full font-semibold gap-2" @click="emit('logout')">
          <LogOut :size="16" :stroke-width="2.25" />
          Se déconnecter
        </button>
      </div>
    </Transition>
  </div>
</template>
