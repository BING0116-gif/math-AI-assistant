<template>
  <div class="layout-default">
    <Sidebar :collapsed="sidebarCollapsed" @toggle="toggleSidebar" />
    <main class="main-area" :class="{ expanded: sidebarCollapsed }">
      <header class="top-bar">
        <button class="menu-trigger" @click="toggleSidebar" :title="sidebarCollapsed ? '展开菜单' : '收起菜单'">
          <span class="menu-icon" :class="{ open: !sidebarCollapsed }">
            <i></i><i></i><i></i>
          </span>
        </button>
        <slot name="header" />
      </header>
      <div class="content-view">
        <slot />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Sidebar from './Sidebar.vue'

const sidebarCollapsed = ref(false)

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.layout-default {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-left: $sidebar-width;
  transition: margin-left $transition-slow;
  min-width: 0;
  background: $bg-primary;

  &.expanded {
    margin-left: 0;
  }
}

.top-bar {
  height: $header-height;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid $border-color;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 16px;
  z-index: 10;
  flex-shrink: 0;
}

.menu-trigger {
  width: 40px;
  height: 40px;
  border: none;
  background: $bg-tertiary;
  border-radius: $radius-md;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all $transition-fast;

  &:hover {
    background: $primary-bg;
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
    height: 2px;
    background: $text-primary;
    border-radius: 1px;
    transition: all $transition-base;

    &:nth-child(2) {
      width: 70%;
    }
    &:nth-child(3) {
      width: 50%;
    }
  }

  &.open {
    i:nth-child(1) { transform: rotate(45deg) translate(2px, 3px); width: 100%; }
    i:nth-child(2) { opacity: 0; }
    i:nth-child(3) { transform: rotate(-45deg) translate(2px, -3px); width: 100%; }
  }
}

.content-view {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

@media (max-width: 768px) {
  .main-area {
    margin-left: 0;
  }
}
</style>
