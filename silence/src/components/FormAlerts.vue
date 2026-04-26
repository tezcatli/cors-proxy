<script setup>
defineProps({ errorMsg: String, infoMsg: String })
</script>

<template>
  <div v-if="errorMsg" role="alert" class="alert alert-error py-2 text-sm mb-3">
    <span>{{ errorMsg }}</span>
  </div>
  <div v-if="infoMsg" role="alert" class="alert alert-success py-2 text-sm mb-3">
    <span>{{ infoMsg }}</span>
  </div>
</template>
