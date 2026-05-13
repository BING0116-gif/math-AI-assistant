<template>
  <div class="layout-default">
    <Sidebar :collapsed="sidebarCollapsed" @toggle="toggleSidebar" />
    <main class="main-area" :class="{ expanded: sidebarCollapsed }">
      <TopBar
        :sidebarCollapsed="sidebarCollapsed"
        @toggleSidebar="toggleSidebar"
      >
        <template #header>
          <slot name="header" />
        </template>
        <template #actions>
          <slot name="actions" />
        </template>
      </TopBar>
      <div class="content-view">
        <slot />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'

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
  background: var(--bg-main);
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-left: $sidebar-width;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 0;
  background: var(--bg-main);

  &.expanded {
    margin-left: 0;
    box-shadow: var(--shadow-lg);
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
  }
}
</style>