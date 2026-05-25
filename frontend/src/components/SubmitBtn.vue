<script setup>
defineProps({ busy: Boolean, label: String })
</script>

<template>
  <button
    class="btn w-full mt-2 font-bold tracking-[-0.005em] text-white border-0 transition-all"
    type="submit"
    :disabled="busy"
    style="
      background: linear-gradient(135deg, #e94560, #ff8aa0 60%, #8b5cf6 120%);
      box-shadow: 0 6px 18px -4px rgba(233,69,96,0.5), inset 0 1px 0 rgba(255,255,255,0.25);
    "
  >
    <span v-if="busy" class="loading loading-spinner loading-sm"></span>
    {{ label }}
  </button>
</template>

<style scoped>
button:hover:not(:disabled) {
  filter: brightness(1.08) saturate(1.1);
  box-shadow: 0 10px 24px -4px rgba(233,69,96,0.6), inset 0 1px 0 rgba(255,255,255,0.3) !important;
}
button:active:not(:disabled) { transform: scale(0.98); }
</style>
