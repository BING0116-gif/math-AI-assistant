<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'soft' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean
  icon?: boolean
}>(), {
  variant: 'secondary',
  size: 'md',
  disabled: false,
  loading: false,
  icon: false,
})

const emit = defineEmits<{
  click: [e: MouseEvent]
}>()

const classes = computed(() => [
  'base-btn',
  `base-btn--${props.variant}`,
  `base-btn--${props.size}`,
  { 'base-btn--loading': props.loading },
  { 'base-btn--icon': props.icon },
])

function handleClick(e: MouseEvent) {
  if (!props.disabled && !props.loading) {
    emit('click', e)
  }
}
</script>

<template>
  <button
    :class="classes"
    :disabled="disabled || loading"
    :aria-busy="loading"
    @click="handleClick"
  >
    <span v-if="loading" class="base-btn__spinner" aria-hidden="true" />
    <slot />
  </button>
</template>

<style scoped>
.base-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-family: var(--font-ui);
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: 0.01em;
  border-radius: 10px;
  transition: background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard);
  cursor: pointer;
  border: 1px solid transparent;
  white-space: nowrap;
  user-select: none;
}
.base-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.base-btn:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}

/* Sizes(§6.3:sm 30 / md 36 / lg 42) */
.base-btn--sm { min-height: 30px; padding: 0 11px; font-size: 12.5px; border-radius: 8px; }
.base-btn--md { min-height: 36px; padding: 0 14px; }
.base-btn--lg { min-height: 42px; padding: 0 18px; }
.base-btn--icon { padding: 8px; min-width: 36px; min-height: 36px; }

/* Variants(§6.3:primary 橙底白字 / secondary 白底描边 / ghost 无底 / soft 品牌软底) */
.base-btn--primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  box-shadow: var(--glow);
}
.base-btn--primary:hover:not(:disabled) {
  background: var(--accent-strong);
  border-color: var(--accent-strong);
}

.base-btn--secondary {
  background: var(--surface);
  color: var(--ink-1);
  border-color: var(--border-strong);
  box-shadow: var(--shadow-1);
}
.base-btn--secondary:hover:not(:disabled) {
  border-color: var(--ink-4);
  color: var(--ink-1);
}

.base-btn--ghost {
  background: transparent;
  color: var(--ink-2);
  border-color: transparent;
}
.base-btn--ghost:hover:not(:disabled) {
  background: var(--surface-2);
  color: var(--ink-1);
}

.base-btn--soft {
  background: var(--brand-soft);
  color: var(--brand-text);
  border-color: transparent;
}
.base-btn--soft:hover:not(:disabled) {
  background: var(--brand-soft-2);
}

.base-btn--danger {
  background: var(--rose);
  color: #fff;
  border-color: var(--rose);
}
.base-btn--danger:hover:not(:disabled) {
  background: var(--rose);
  filter: brightness(1.08);
}

/* Loading */
.base-btn--loading { position: relative; }
.base-btn__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
