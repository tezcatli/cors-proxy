<script setup>
defineProps({ errorMsg: String, infoMsg: String })
</script>

<template>
  <div v-if="errorMsg" role="alert" class="alert alert--error">
    <span class="lab">Erreur</span><span>{{ errorMsg }}</span>
  </div>
  <div v-if="infoMsg" role="status" class="alert">
    <span class="lab">Info</span><span>{{ infoMsg }}</span>
  </div>
</template>

<style scoped>
.alert { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; box-shadow: inset 3px 0 0 var(--c-accent); background: var(--c-surface); color: var(--c-fg); }
.alert--error { box-shadow: inset 3px 0 0 var(--c-danger); }
.alert--error .lab { color: var(--c-danger); }
</style>
