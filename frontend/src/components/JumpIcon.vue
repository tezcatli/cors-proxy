<script setup>
// A jump through time, told by its arrow and its seconds inside it (the « 60 »
// of the full player's ↺ and ↻): Lucide's RotateCcw / RotateCw, with a number.
defineProps({
  dir:  { type: Number, default: -1 },   // -1 back, +1 ahead
  n:    { type: Number, default: 60 },
  size: { type: Number, default: 28 },
})
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="dir < 0">
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
    </template>
    <template v-else>
      <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
    </template>
    <text x="12" y="15.2" text-anchor="middle" fill="currentColor" stroke="none" font-family="Sora, sans-serif" font-weight="700" font-size="7.5">{{ n }}</text>
  </svg>
</template>
