<script setup>
import { ref } from 'vue'
import { useMarquee } from '../composables/useMarquee.js'

// Single-line text that horizontally scrolls only when it overflows its box.
// Overflow detection + the duplicated (aria-hidden) copy used for the seamless
// loop live here once, instead of being reimplemented per consumer.
const props = defineProps({
  text:       String,
  innerClass: { type: String, default: '' },   // context font/colour modifier
})

const el = ref(null)
const { needsScroll } = useMarquee(el, () => props.text)
</script>

<template>
  <div ref="el" class="marquee" :class="{ 'marquee--on': needsScroll }">
    <span class="marquee__inner" :class="innerClass">{{ text }}</span>
    <span v-if="needsScroll" class="marquee__inner" :class="innerClass" aria-hidden="true">{{ text }}</span>
  </div>
</template>
