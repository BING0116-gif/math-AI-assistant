<script setup lang="ts">
import { watch, onMounted, onUnmounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  width?: string
}>(), {
  width: '480px',
})

const emit = defineEmits<{
  close: []
}>()

const dialogRef = ref<HTMLElement | null>(null)
const previousFocus = ref<HTMLElement | null>(null)

watch(() => props.open, (val) => {
  if (val) {
    previousFocus.value = document.activeElement as HTMLElement
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
    previousFocus.value?.focus()
  }
})

function onBackdropClick() {
  emit('close')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="dialog-backdrop"
      @click.self="onBackdropClick"
      role="dialog"
      :aria-modal="true"
      :aria-label="title"
    >
      <div ref="dialogRef" class="dialog-panel" :style="{ maxWidth: width }">
        <div v-if="title" class="dialog-header">
          <h3 class="dialog-title">{{ title }}</h3>
          <button class="dialog-close" aria-label="关闭" @click="emit('close')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="dialog-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="dialog-footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  animation: fadeIn 180ms ease-out;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.dialog-panel {
  width: 90%;
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  animation: slideUp 200ms ease-out;
}
@keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--border-subtle);
}
.dialog-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
}
.dialog-close {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  transition: background var(--transition-fast);
}
.dialog-close:hover { background: var(--surface-hover); }
.dialog-body {
  padding: var(--space-6);
  overflow-y: auto;
  flex: 1;
}
.dialog-footer {
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--border-subtle);
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}
</style>