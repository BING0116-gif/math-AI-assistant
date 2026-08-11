<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
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
  font-family: var(--font-sans);
  font-weight: 500;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast), color var(--transition-fast), box-shadow var(--transition-fast);
  cursor: pointer;
  border: 1.5px solid transparent;
  white-space: nowrap;
  user-select: none;
}
.base-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.base-btn:focus-visible {
  outline: 2.5px solid var(--accent);
  outline-offset: 2px;
}

/* Sizes */
.base-btn--sm { padding: 6px 12px; font-size: var(--font-size-sm); }
.base-btn--md { padding: 8px 16px; font-size: var(--font-size-sm); }
.base-btn--lg { padding: 10px 20px; font-size: var(--font-size-base); }
.base-btn--icon { padding: 8px; min-width: 36px; min-height: 36px; }

/* Variants */
.base-btn--primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.base-btn--primary:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

.base-btn--secondary {
  background: var(--surface);
  color: var(--text-primary);
  border-color: var(--border-strong);
}
.base-btn--secondary:hover:not(:disabled) {
  background: var(--surface-hover);
}

.base-btn--ghost {
  background: transparent;
  color: var(--text-secondary);
  border-color: transparent;
}
.base-btn--ghost:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.base-btn--danger {
  background: var(--danger);
  color: #fff;
  border-color: var(--danger);
}
.base-btn--danger:hover:not(:disabled) {
  filter: brightness(1.1);
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