<template>
  <button
    class="theme-toggle"
    @click="ui.toggleTheme()"
    :title="ui.theme === 'light' ? '切换至暗色模式' : '切换至亮色模式'"
    :aria-label="ui.theme === 'light' ? '切换至暗色模式' : '切换至亮色模式'"
    :aria-pressed="ui.theme === 'dark'"
  >
    <svg v-if="ui.theme === 'light'" class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/>
      <line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
    <svg v-else class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
    </svg>
  </button>
</template>

<script setup>
import { useUiStore } from '@/stores/uiStore'

const ui = useUiStore()
</script>

<style lang="scss" scoped>
.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1.5px solid var(--border-light);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  padding: 0;

  &:hover {
    color: var(--primary);
    border-color: var(--primary);
    background: var(--primary-ghost);
    transform: scale(1.08);
  }

  &:active {
    transform: scale(0.95);
  }
}

.theme-icon {
  width: 18px;
  height: 18px;
}
</style>