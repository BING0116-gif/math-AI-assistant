<script setup>
defineProps({
  message: { type: String, default: '' },
})
</script>

<template>
  <p v-if="message" class="mode-guard-notice" role="alert">{{ message }}</p>
</template>

<style scoped>
.mode-guard-notice {
  max-width: 820px;
  margin: 0 auto var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--warning);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
}
</style>
