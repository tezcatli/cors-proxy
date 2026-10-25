<script setup>
// The mark, LUDO// (DECISIONS.md, « Interface »): LUDO on a block with sharp
// corners, like a cover's label, and // in the accent, slanted like fast
// forward. The // takes the colours of the subtree it sits in (a game's page,
// the newest test on the Ludothèque). It is sized by its parent's font-size;
// the link around it carries its name.
</script>

<template>
  <span class="wm" aria-hidden="true"><span class="wm__ludo">LUDO</span><span class="wm__sign">//</span></span>
</template>

<style scoped>
.wm {
  display: inline-flex;
  align-items: center;
  font-family: var(--font-display);
  font-weight: 700;
  letter-spacing: 0.02em;
  line-height: 1;
}
.wm__ludo { padding: 0.2em 0.42em 0.24em; background: var(--c-fg); color: var(--c-bg); }
.wm__sign {
  display: inline-block;
  padding-left: 0.16em;
  font-size: 1.18em;
  letter-spacing: -0.12em;
  color: var(--c-accent);
  transform: skewX(-12deg) scaleX(1.15);
}
</style>
