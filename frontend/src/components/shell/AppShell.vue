<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUiStore } from '@/stores/uiStore'
import { useChatStore } from '@/stores/chatStore'

const router = useRouter()
const route = useRoute()
const ui = useUiStore()
const chatStore = useChatStore()

const searchQuery = ref('')

const navItems = [
  { to: '/dashboard', label: '学习看板', icon: 'grid' },
  { to: '/profile', label: '记忆画像', icon: 'user' },
  { to: '/knowledge', label: '知识星球', icon: 'book' },
  { to: '/apply', label: '学以致用', icon: 'pencil' },
  { to: '/error-book', label: '错题复盘', icon: 'alert-circle' },
]

const filteredChats = computed(() => {
  if (!searchQuery.value) return chatStore.sortedChats
  const q = searchQuery.value.toLowerCase()
  return chatStore.sortedChats.filter(c =>
    c.title?.toLowerCase().includes(q)
  )
})

function isActive(to: string) {
  if (to === '/') return route.path === '/'
  return route.path === to || route.path.startsWith(to + '/')
}

function startNewChat() {
  chatStore.createNewChat()
  router.push('/')
}

function openChat(chatId: string) {
  chatStore.switchChat(chatId)
  router.push(`/chat/${chatId}`)
}

function deleteChat(e: MouseEvent, chatId: string) {
  e.stopPropagation()
  chatStore.deleteChat(chatId)
}
</script>

<template>
  <div class="app-shell">
    <!-- 跳过链接 -->
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <!-- 桌面侧栏 -->
    <aside
      class="sidebar"
      :class="{ 'sidebar--collapsed': ui.sidebarCollapsed }"
      aria-label="主导航"
    >
      <!-- 品牌标识 -->
      <div class="sidebar__brand">
        <div class="sidebar__logo" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <span v-if="!ui.sidebarCollapsed" class="sidebar__brand-name">知微</span>
      </div>

      <!-- 新对话按钮 -->
      <button class="sidebar__new-chat" @click="startNewChat">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        <span v-if="!ui.sidebarCollapsed">新对话</span>
      </button>

      <!-- 搜索 -->
      <div v-if="!ui.sidebarCollapsed" class="sidebar__search">
        <svg class="sidebar__search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <input
          v-model="searchQuery"
          class="sidebar__search-input"
          type="search"
          placeholder="搜索对话..."
          aria-label="搜索对话历史"
        />
      </div>

      <!-- 对话历史列表 -->
      <div v-if="!ui.sidebarCollapsed" class="sidebar__history">
        <div class="sidebar__section-label">对话历史</div>
        <div class="sidebar__chat-list">
          <button
            v-for="chat in filteredChats"
            :key="chat.id"
            class="sidebar__chat-item"
            :class="{ 'sidebar__chat-item--active': chat.id === chatStore.currentChatId }"
            @click="openChat(chat.id)"
          >
            <span class="sidebar__chat-title">{{ chat.title || '新对话' }}</span>
            <button
              class="sidebar__chat-delete"
              :aria-label="`删除 ${chat.title || '对话'}`"
              @click="(e) => deleteChat(e, chat.id)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </button>
          <p v-if="filteredChats.length === 0" class="sidebar__empty">
            {{ searchQuery ? '未找到匹配的对话' : '还没有对话记录' }}
          </p>
        </div>
      </div>

      <!-- 主导航（底部） -->
      <nav class="sidebar__nav" aria-label="页面导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="sidebar__nav-item"
          :class="{ 'sidebar__nav-item--active': isActive(item.to) }"
          :aria-current="isActive(item.to) ? 'page' : undefined"
        >
          <svg
            class="sidebar__nav-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            aria-hidden="true"
          >
            <template v-if="item.icon === 'grid'">
              <rect x="3" y="3" width="7" height="7" rx="1"/>
              <rect x="14" y="3" width="7" height="7" rx="1"/>
              <rect x="3" y="14" width="7" height="7" rx="1"/>
              <rect x="14" y="14" width="7" height="7" rx="1"/>
            </template>
            <template v-if="item.icon === 'user'">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </template>
            <template v-if="item.icon === 'book'">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
              <path d="M8 7h8M8 11h5"/>
            </template>
            <template v-if="item.icon === 'alert-circle'">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </template>
            <template v-if="item.icon === 'pencil'">
              <path d="m14 4 6 6M3 21l4.5-1 11-11a2.1 2.1 0 0 0-3-3l-11 11L3 21z"/>
            </template>
          </svg>
          <span v-if="!ui.sidebarCollapsed">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <!-- 底部辅助入口 -->
      <div class="sidebar__footer">
        <button
          class="sidebar__footer-btn"
          :aria-label="ui.sidebarCollapsed ? '展开侧栏' : '收起侧栏'"
          @click="ui.toggleSidebar()"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            aria-hidden="true"
          >
            <path :d="ui.sidebarCollapsed ? 'm9 18 6-6-6-6' : 'm15 18-6-6 6-6'"/>
          </svg>
          <span v-if="!ui.sidebarCollapsed">收起侧栏</span>
        </button>
        <button class="sidebar__footer-btn" aria-label="切换主题" @click="ui.toggleTheme()">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
          </svg>
          <span v-if="!ui.sidebarCollapsed">主题</span>
        </button>
      </div>
    </aside>

    <!-- 主工作区 -->
    <div class="shell-main">
      <!-- 顶部栏 -->
      <header class="shell-topbar">
        <button class="shell-menu-btn" aria-label="打开导航" @click="ui.mobileDrawerOpen = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
        </button>
        <div class="shell-topbar__title">
          <slot name="topbar-title" />
        </div>
        <div class="shell-topbar__actions">
          <slot name="topbar-actions" />
        </div>
      </header>

      <!-- 页面头部（可选插槽） -->
      <div v-if="$slots['page-header']" class="shell-page-header">
        <slot name="page-header" />
      </div>

      <!-- 主内容 -->
      <main id="main-content" class="shell-content" tabindex="-1">
        <slot />
      </main>
    </div>

    <!-- 右侧检查器（可选） -->
    <aside
      v-if="ui.inspectorOpen && $slots.inspector"
      class="shell-inspector"
      aria-label="上下文检查器"
    >
      <div class="shell-inspector__head">
        <span class="shell-inspector__title">检查器</span>
        <button class="shell-inspector__close" aria-label="关闭检查器" @click="ui.toggleInspector()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>
      <slot name="inspector" />
    </aside>

    <!-- 移动端抽屉 -->
    <Teleport to="body">
      <div
        v-if="ui.mobileDrawerOpen"
        class="mobile-drawer-backdrop"
        @click="ui.mobileDrawerOpen = false"
      >
        <aside class="mobile-drawer" aria-label="移动端导航" role="dialog" aria-modal="true" @click.stop>
          <div class="mobile-drawer__head">
            <strong>知微</strong>
            <button aria-label="关闭导航" @click="ui.mobileDrawerOpen = false">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </button>
          </div>
          <RouterLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="mobile-drawer__link"
            @click="ui.mobileDrawerOpen = false"
          >
            {{ item.label }}
          </RouterLink>
          <button class="mobile-drawer__link" @click="startNewChat(); ui.mobileDrawerOpen = false">
            新对话
          </button>
        </aside>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100dvh;
  display: flex;
  background: var(--canvas);
  color: var(--text-primary);
}

.skip-link {
  position: fixed;
  top: var(--space-2);
  left: var(--space-2);
  z-index: 2000;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  transform: translateY(-160%);
  transition: transform var(--transition-fast);
}
.skip-link:focus {
  transform: translateY(0);
}

/* ============ 侧栏 ============ */
.sidebar {
  width: var(--sidebar-width);
  flex: 0 0 var(--sidebar-width);
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  padding: var(--space-3) var(--space-3) var(--space-3);
  background: var(--surface);
  border-right: 1px solid var(--border-subtle);
  transition: width var(--transition-base), flex-basis var(--transition-base), padding var(--transition-base);
  overflow: hidden;
}
.sidebar--collapsed {
  width: var(--sidebar-collapsed);
  flex-basis: var(--sidebar-collapsed);
  padding-inline: var(--space-2);
}

/* ---- Logo ---- */
.sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 2px 4px;
  min-height: 40px;
  margin-bottom: var(--space-2);
}
.sidebar__logo {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  flex-shrink: 0;
}
.sidebar__logo svg { width: 18px; }
.sidebar__brand-name {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-primary);
}

/* ---- 新对话按钮 ---- */
.sidebar__new-chat {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-pill);
  background: var(--accent);
  color: #fff;
  font-weight: 600;
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
  margin-bottom: var(--space-2);
}
.sidebar__new-chat:hover {
  background: var(--accent-hover);
}
.sidebar__new-chat svg { width: 16px; }

/* ---- 搜索 ---- */
.sidebar__search {
  position: relative;
  margin-bottom: var(--space-2);
}
.sidebar__search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 15px;
  height: 15px;
  color: var(--text-tertiary);
}
.sidebar__search-input {
  width: 100%;
  height: 34px;
  padding: 0 10px 0 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  outline: none;
  transition: border-color var(--transition-fast), background var(--transition-fast);
}
.sidebar__search-input:focus {
  border-color: var(--accent);
  background: var(--surface);
}
.sidebar__search-input::placeholder {
  color: var(--text-tertiary);
}

/* ---- 对话历史 ---- */
.sidebar__history {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar__section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  letter-spacing: 0.06em;
  padding: 0 var(--space-1);
  margin-bottom: var(--space-1);
}
.sidebar__chat-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.sidebar__chat-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 10px;
  border-radius: var(--radius-xs);
  cursor: pointer;
  text-align: left;
  width: 100%;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  transition: background var(--transition-fast), color var(--transition-fast);
  gap: var(--space-1);
}
.sidebar__chat-item:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}
.sidebar__chat-item--active {
  background: var(--accent-soft);
  color: var(--text-primary);
  font-weight: 500;
}
.sidebar__chat-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.sidebar__chat-delete {
  opacity: 0;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-xs);
  color: var(--text-tertiary);
  flex-shrink: 0;
  transition: opacity var(--transition-fast), background var(--transition-fast);
  background: none;
  border: none;
  cursor: pointer;
}
.sidebar__chat-item:hover .sidebar__chat-delete {
  opacity: 1;
}
.sidebar__chat-delete:hover {
  background: var(--danger);
  color: #fff;
}
.sidebar__chat-delete svg { width: 12px; }
.sidebar__empty {
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
  padding: var(--space-2) var(--space-1);
}

/* ---- 主导航（底部区域） ---- */
.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 1px;
  border-top: 1px solid var(--border-subtle);
  padding-top: var(--space-2);
  margin-top: var(--space-2);
}
.sidebar__nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 7px 10px;
  border-radius: var(--radius-xs);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 500;
  text-decoration: none;
  transition: color var(--transition-fast), background var(--transition-fast);
  min-height: 36px;
}
.sidebar__nav-item:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}
.sidebar__nav-item--active {
  color: var(--text-primary);
  background: var(--accent-soft);
  font-weight: 600;
}
.sidebar__nav-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* ---- 底部辅助入口 ---- */
.sidebar__footer {
  display: flex;
  flex-direction: column;
  gap: 1px;
  border-top: 1px solid var(--border-subtle);
  padding-top: var(--space-2);
  margin-top: var(--space-2);
}
.sidebar__footer-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px 10px;
  border-radius: var(--radius-xs);
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
  min-height: 34px;
  background: none;
  border: none;
  cursor: pointer;
  width: 100%;
  text-align: left;
}
.sidebar__footer-btn:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}
.sidebar__footer-btn svg { width: 18px; height: 18px; }

/* ============ 主工作区 ============ */
.shell-main {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: var(--canvas);
}

.shell-topbar {
  min-height: var(--topbar-height);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--content-padding);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface);
}
.shell-menu-btn {
  display: none;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: none;
  cursor: pointer;
  color: var(--text-primary);
}
.shell-menu-btn svg { width: 18px; }
.shell-topbar__title {
  flex: 1;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  min-width: 0;
}
.shell-topbar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.shell-page-header {
  padding: var(--space-4) var(--content-padding);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface);
}

.shell-content {
  flex: 1;
  overflow: hidden;
  outline: none;
  display: flex;
  flex-direction: column;
  background: var(--canvas);
}

/* ============ 检查器 ============ */
.shell-inspector {
  width: var(--inspector-width);
  flex: 0 0 var(--inspector-width);
  border-left: 1px solid var(--border-subtle);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.shell-inspector__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-subtle);
}
.shell-inspector__title {
  font-size: var(--font-size-sm);
  font-weight: 600;
}
.shell-inspector__close {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-xs);
  color: var(--text-secondary);
  background: none;
  border: none;
  cursor: pointer;
}
.shell-inspector__close:hover {
  background: var(--surface-hover);
}

/* ============ 移动端抽屉 ============ */
.mobile-drawer-backdrop {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 500;
  background: rgba(0, 0, 0, 0.4);
}
.mobile-drawer {
  width: min(320px, 86vw);
  height: 100%;
  padding: var(--space-5) var(--space-4);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  box-shadow: var(--shadow-lg);
}
.mobile-drawer__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
  font-size: var(--font-size-lg);
  font-weight: 700;
}
.mobile-drawer__head button {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
}
.mobile-drawer__link {
  display: block;
  padding: var(--space-3) var(--space-2);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--font-size-base);
  text-decoration: none;
  transition: background var(--transition-fast);
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  width: 100%;
}
.mobile-drawer__link:hover {
  background: var(--surface-hover);
}

/* ============ 响应式 ============ */
@media (max-width: 1279px) and (min-width: 769px) {
  .sidebar {
    width: var(--sidebar-collapsed);
    flex-basis: var(--sidebar-collapsed);
    padding-inline: var(--space-2);
  }
  .sidebar__brand-name,
  .sidebar__new-chat span,
  .sidebar__search,
  .sidebar__history,
  .sidebar__nav-item span,
  .sidebar__footer-btn span {
    display: none;
  }
  .sidebar--collapsed .sidebar__brand-name,
  .sidebar--collapsed .sidebar__new-chat span,
  .sidebar--collapsed .sidebar__search,
  .sidebar--collapsed .sidebar__history,
  .sidebar--collapsed .sidebar__nav-item span,
  .sidebar--collapsed .sidebar__footer-btn span {
    display: none;
  }
}

@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
  .shell-menu-btn {
    display: grid;
  }
  .shell-topbar {
    padding: 0 var(--space-4);
    min-height: 52px;
  }
  .shell-page-header {
    padding: var(--space-3) var(--space-4);
  }
  .mobile-drawer-backdrop {
    display: block;
  }
  .shell-inspector {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar, .sidebar__nav-item, .sidebar__chat-item, .sidebar__footer-btn {
    transition: none;
  }
}
</style>
