<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  status: 'insufficient_data' | 'touched' | 'learning' | 'needs_review' | 'mastered' | 'unclassified' | string
  size?: 'sm' | 'md'
}>(), {
  size: 'md',
})

const statusMap: Record<string, { label: string; color: string }> = {
  insufficient_data: { label: '数据不足', color: 'var(--ink-3)' },
  touched: { label: '接触过', color: 'var(--ink-3)' },
  learning: { label: '学习中', color: 'var(--amber)' },
  needs_review: { label: '待巩固', color: 'var(--accent-text)' },
  mastered: { label: '已掌握', color: 'var(--green)' },
  unclassified: { label: '待分类', color: 'var(--ink-3)' },
}

const info = computed(() => statusMap[props.status] || { label: props.status, color: 'var(--ink-3)' })
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
/* 形状对齐原型 tag(§6.3:radius 7 / 11.5px / 600) */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.01em;
  border-radius: 7px;
  white-space: nowrap;
}
.status-badge--sm { padding: 2px 8px; }
.status-badge--md { padding: 3px 10px; font-size: 12.5px; }
.status-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ink-1);
  flex-shrink: 0;
}
</style>
