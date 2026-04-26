<script setup>
defineProps({ busy: Boolean, label: String })
</script>

<template>
  <button class="btn btn-primary w-full mt-1" type="submit" :disabled="busy">
    <span v-if="busy" class="loading loading-spinner loading-sm"></span>
    {{ label }}
  </button>
</template>
