<script setup>
defineProps({
  aspect:  { type: String, default: '45/64' },   // CSS aspect-ratio
  rounded: { type: String, default: 'rounded-2xl' },
})
</script>

<template>
  <div
    :class="['skeleton-shimmer relative w-full overflow-hidden', rounded]"
    :style="{ aspectRatio: aspect }"
    aria-hidden="true"
  />
</template>
