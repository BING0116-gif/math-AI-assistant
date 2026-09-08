<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  status: 'insufficient_data' | 'touched' | 'learning' | 'needs_review' | 'mastered' | 'unclassified' | string
  size?: 'sm' | 'md'
}>(), {
  size: 'md',
})

const statusMap: Record<string, { label: string; color: string }> = {
  insufficient_data: { label: '数据不足', color: 'var(--text-tertiary)' },
  touched: { label: '接触过', color: 'var(--text-tertiary)' },
  learning: { label: '学习中', color: 'var(--learning)' },
  needs_review: { label: '待巩固', color: 'var(--weak)' },
  mastered: { label: '已掌握', color: 'var(--mastered)' },
  unclassified: { label: '待分类', color: 'var(--text-tertiary)' },
}

const info = computed(() => statusMap[props.status] || { label: props.status, color: 'var(--text-tertiary)' })
</script>

<template>
  <span
    class="status-badge"
    :class="[`status-badge--${size}`, `status-badge--${status}`]"
    :style="{ '--badge-color': info.color }"
  >
    <span class="status-badge__dot" aria-hidden="true" />
    {{ info.label }}
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 500;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}
.status-badge--sm { padding: 2px 8px; font-size: var(--font-size-xs); }
.status-badge--md { padding: 4px 10px; font-size: var(--font-size-sm); }
.status-badge__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--badge-color);
  flex-shrink: 0;
}
</style>