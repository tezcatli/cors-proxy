<script setup>
import { AlertTriangle, CheckCircle2 } from 'lucide-vue-next'
defineProps({ errorMsg: String, infoMsg: String })
</script>

<template>
  <div
    v-if="errorMsg"
    role="alert"
    class="flex items-start gap-2 py-2 px-3 text-sm mb-3 rounded-lg border-l-4 border-error bg-error/10 text-error"
  >
    <AlertTriangle :size="16" :stroke-width="2.25" class="mt-0.5 flex-shrink-0" />
    <span class="flex-1">{{ errorMsg }}</span>
  </div>
  <div
    v-if="infoMsg"
    role="alert"
    class="flex items-start gap-2 py-2 px-3 text-sm mb-3 rounded-lg border-l-4 border-success bg-success/10 text-success"
  >
    <CheckCircle2 :size="16" :stroke-width="2.25" class="mt-0.5 flex-shrink-0" />
    <span class="flex-1">{{ infoMsg }}</span>
  </div>
</template>
