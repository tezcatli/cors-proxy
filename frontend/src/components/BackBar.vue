<script setup>
import { ArrowLeft } from 'lucide-vue-next'

// Floating glass back pill shared by DetailView and EpisodeView (loading +
// loaded states). Pins itself top-left over the hero; consumers don't position it.
defineProps({ label: String })
const emit = defineEmits(['back'])
</script>

<template>
  <button class="back-pill glass-chrome" @click="emit('back')">
    <ArrowLeft :size="16" :stroke-width="2.25" />
    <span class="back-pill__label">{{ label }}</span>
  </button>
</template>
