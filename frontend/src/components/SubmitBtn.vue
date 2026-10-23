<script setup>
defineProps({ busy: Boolean, label: String })
</script>

<template>
  <button class="btn-play submit" type="submit" :disabled="busy">
    <span v-if="busy" class="lab submit__busy" aria-hidden="true">…</span>
    {{ label }}
  </button>
</template>

<style scoped>
.submit { width: 100%; margin-top: 8px; }
.submit__busy { color: inherit; }
</style>
