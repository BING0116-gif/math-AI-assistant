<template>
  <header class="top-bar">
    <button class="menu-trigger" @click="$emit('toggleSidebar')" :title="sidebarCollapsed ? '展开菜单' : '收起菜单'">
      <span class="menu-icon" :class="{ open: !sidebarCollapsed }">
        <i></i><i></i><i></i>
      </span>
    </button>
    <div class="top-bar-content">
      <slot name="header" />
    </div>
    <div class="top-bar-actions">
      <ThemeToggle />
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
import ThemeToggle from '@/components/common/ThemeToggle.vue'

defineProps({
  sidebarCollapsed: Boolean
})

defineEmits(['toggleSidebar'])
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.top-bar {
  height: $header-height;
  background: var(--bg-topbar);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 20px;
  z-index: 10;
  flex-shrink: 0;
  color: var(--text-primary);
}

.top-bar-content {
  flex: 1;
  min-width: 0;
}

.top-bar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.menu-trigger {
  width: 42px;
  height: 42px;
  border: none;
  background: var(--bg-card);
  backdrop-filter: blur(8px);
  border-radius: $radius-md;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid var(--border-light);
  flex-shrink: 0;

  &:hover {
    background: var(--primary-ghost);
    transform: scale(1.05);
    box-shadow: var(--shadow-md);
    border-color: var(--primary);
  }

  &:active {
    transform: scale(0.95);
  }
}

.menu-icon {
  display: flex;
  flex-direction: column;
  gap: 5px;
  width: 18px;

  i {
    display: block;
    width: 100%;
    height: 2.5px;
    background: var(--primary);
    border-radius: 2px;
    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);

    &:nth-child(2) {
      width: 70%;
      margin-left: auto;
    }
    &:nth-child(3) {
      width: 50%;
      margin-left: auto;
    }
  }

  &.open {
    i:nth-child(1) {
      transform: rotate(45deg) translate(3px, 4px);
      width: 100%;
    }
    i:nth-child(2) {
      opacity: 0;
      transform: translateX(-10px);
    }
    i:nth-child(3) {
      transform: rotate(-45deg) translate(3px, -4px);
      width: 100%;
    }
  }
}

@media (max-width: 768px) {
  .top-bar {
    padding: 0 16px;
  }
}
</style>