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
  position: relative;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-left: $sidebar-width;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 0;
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-left: 1px solid rgba(255, 255, 255, 0.3);

  &.expanded {
    margin-left: 0;
    box-shadow: -10px 0 40px rgba(0, 0, 0, 0.05);
  }
}

.top-bar {
  height: $header-height;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(226, 232, 240, 0.5);
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 20px;
  z-index: 10;
  flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.menu-trigger {
  width: 42px;
  height: 42px;
  border: none;
  background: rgba(241, 245, 249, 0.8);
  backdrop-filter: blur(8px);
  border-radius: $radius-md;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  
  &:hover {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(129, 140, 248, 0.15) 100%);
    transform: scale(1.05);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
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
    background: linear-gradient(90deg, $primary 0%, $primary-light 100%);
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

.content-view {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}

@media (max-width: 768px) {
  .main-area {
    margin-left: 0;
    background: rgba(255, 255, 255, 0.75);
  }
  
  .top-bar {
    padding: 0 16px;
  }
}
</style>