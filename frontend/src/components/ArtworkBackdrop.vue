<script setup>
import { computed } from 'vue'
import { igdbUrl } from '../lib/igdbCdn.js'

const props = defineProps({
  coverImageId: { type: String, default: null },
  fallbackUrl:  { type: String, default: null },
  intensity:    { type: String, default: 'hero' },  // 'hero' | 'card' | 'player'
})

const src = computed(() => {
  if (props.coverImageId) return igdbUrl(props.coverImageId, 't_cover_big_2x')
  return props.fallbackUrl
})

const config = computed(() => {
  switch (props.intensity) {
    case 'card':   return { blur: 36, saturate: 1.5, scale: 1.4, scrimTop: 0.30, scrimBot: 0.75, washOpacity: 0.6 }
    case 'player': return { blur: 48, saturate: 1.4, scale: 1.6, scrimTop: 0.30, scrimBot: 0.75, washOpacity: 0.6 }
    case 'hero':
    default:       return { blur: 80, saturate: 1.7, scale: 1.8, scrimTop: 0.15, scrimBot: 0.55, washOpacity: 0.9 }
  }
})
</script>

<template>
  <div class="hero-backdrop" aria-hidden="true">
    <img
      v-if="src"
      :src="src"
      class="hero-backdrop__img"
      :style="{
        filter:    `blur(${config.blur}px) saturate(${config.saturate})`,
        transform: `scale(${config.scale})`,
      }"
      alt=""
      loading="lazy"
      decoding="async"
    />
    <!-- Accent wash (above artwork, below scrim) — picks up the extracted accent + darker base -->
    <div class="hero-backdrop__wash" :style="{ opacity: config.washOpacity }" />
    <!-- Final scrim — lighter at top so artwork + wash can show through -->
    <div
      class="hero-backdrop__scrim"
      :style="{ background: `linear-gradient(180deg, rgba(8,8,15,${config.scrimTop}) 0%, rgba(8,8,15,${(config.scrimTop+config.scrimBot)/2}) 55%, rgba(8,8,15,${config.scrimBot}) 100%)` }"
    />
  </div>
</template>
