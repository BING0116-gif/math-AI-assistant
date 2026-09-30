<script setup lang="ts">
import BaseButton from './BaseButton.vue'

defineProps<{
  title?: string
  description?: string
  action?: string
}>()

defineEmits<{
  action: []
}>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">
      <!-- 默认文档图标;各页可经 #icon 传 lucide 图标(§6.3) -->
      <slot name="icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
          <polyline points="13 2 13 9 20 9"/>
          <line x1="9" y1="13" x2="15" y2="13"/>
          <line x1="12" y1="10" x2="12" y2="16"/>
        </svg>
      </slot>
    </div>
    <h3 v-if="title" class="empty-state__title">{{ title }}</h3>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <BaseButton v-if="action" variant="primary" size="md" class="empty-state__action" @click="$emit('action')">
      {{ action }}
    </BaseButton>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
  gap: var(--space-3);
}
.empty-state__icon {
  color: var(--ink-3);
  opacity: 0.6;
  margin-bottom: var(--space-2);
}
.empty-state__title {
  font-size: var(--type-lg);
  font-weight: 600;
  color: var(--ink-1);
}
.empty-state__desc {
  font-size: var(--type-sm);
  color: var(--ink-2);
  max-width: 360px;
  line-height: var(--line-height-base);
}
.empty-state__action {
  margin-top: var(--space-2);
}
</style>